from flask import Flask, jsonify, request
import os
import logging
import json
import inspect

# Imports for Google API
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import time

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(module)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Service Account Configuration ---
# Define the necessary scopes for the Google Sheets API
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']
# Define the custom header for passing service account credentials
SERVICE_ACCOUNT_HEADER = 'X-Goog-Service-Account-Info'

# --- NEW: Service Account Authentication Helper ---
def get_sheets_service_from_header():
    """
    Creates a Google Sheets API service object from service account info
    passed in a request header.
    """
    service_account_json_str = request.headers.get(SERVICE_ACCOUNT_HEADER)
    if not service_account_json_str:
        raise ValueError(f"Required header '{SERVICE_ACCOUNT_HEADER}' is missing.")
    
    try:
        # Load the service account info from the JSON string in the header
        service_account_info = json.loads(service_account_json_str)
        if 'private_key' not in service_account_info:
             raise ValueError("The service account info is missing the 'private_key'.")

        # Create credentials from the service account info
        credentials = service_account.Credentials.from_service_account_info(
            service_account_info,
            scopes=SCOPES
        )
        logger.info(f"Successfully created credentials for service account: {credentials.service_account_email}")
        
        # Build the Google Sheets API service
        return build("sheets", "v4", credentials=credentials, cache_discovery=False)
    
    except json.JSONDecodeError:
        raise ValueError(f"The value of the '{SERVICE_ACCOUNT_HEADER}' header is not valid JSON.")
    except Exception as e:
        # Catch other potential errors from the credentials library
        logger.error(f"Failed to create credentials from service account info: {e}", exc_info=True)
        raise ValueError(f"The provided service account JSON is invalid. Error: {e}")


# --- Google Sheets API Wrapper Functions (Unchanged) ---
# These functions now receive the 'service' object created by the helper above.

def api_update_cell(service, spreadsheet_id, cell_range, new_value, value_input_option="USER_ENTERED"):
    logger.info(f"API: Updating cell '{cell_range}' in sheet '{spreadsheet_id}' to '{new_value}' with option '{value_input_option}'.")
    body = {"values": [[new_value]]}
    result = service.spreadsheets().values().update(
        spreadsheetId=spreadsheet_id, range=cell_range, valueInputOption=value_input_option, body=body
    ).execute()
    logger.info(f"API: Cell update successful. Result: {result}"); return result

def api_append_rows(service, spreadsheet_id, range_name, values_data, value_input_option="USER_ENTERED"):
    logger.info(f"API: Appending {len(values_data)} rows to sheet '{spreadsheet_id}', range '{range_name}'.")
    body = {"values": values_data}
    result = service.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id, range=range_name, valueInputOption=value_input_option, insertDataOption="INSERT_ROWS", body=body
    ).execute()
    logger.info(f"API: Row append successful. Updates: {result.get('updates')}"); return result

def api_delete_rows(service, spreadsheet_id, sheet_id, start_row_index, end_row_index):
    logger.info(f"API: Deleting rows from sheet '{spreadsheet_id}', sheetId {sheet_id}, from index {start_row_index} to {end_row_index-1}.")
    requests_body = [{"deleteDimension": {"range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": start_row_index, "endIndex": end_row_index}}}]
    body = {"requests": requests_body}
    result = service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()
    logger.info(f"API: Row deletion successful. Result: {result}"); return result

def api_create_new_tab(service, spreadsheet_id, new_sheet_title):
    logger.info(f"API: Creating new tab named '{new_sheet_title}' in spreadsheet '{spreadsheet_id}'.")
    requests_body = [{"addSheet": {"properties": {"title": new_sheet_title}}}]
    body = {"requests": requests_body}
    result = service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()
    logger.info(f"API: New tab creation successful. Result: {result}"); return result

def api_clear_values(service, spreadsheet_id, range_name):
    logger.info(f"API: Clearing values from sheet '{spreadsheet_id}', range '{range_name}'.")
    result = service.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=range_name, body={}).execute()
    logger.info(f"API: Values clear successful. Cleared range: {result.get('clearedRange')}"); return result

def api_get_spreadsheet_metadata(service, spreadsheet_id):
    logger.info(f"API: Getting metadata for spreadsheet '{spreadsheet_id}'.")
    fields_to_get = "properties(title),sheets(properties(sheetId,title,index))"
    result = service.spreadsheets().get(spreadsheetId=spreadsheet_id, fields=fields_to_get).execute()
    logger.info("API: Metadata retrieval successful."); return result

def api_get_values(service, spreadsheet_id, range_name):
    logger.info(f"API: Getting values from sheet '{spreadsheet_id}', range '{range_name}'.")
    result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_name).execute()
    values = result.get('values', [])
    logger.info(f"API: Values retrieval successful. Got {len(values)} rows.")
    return values

def get_sheet_id_by_name(service, spreadsheet_id, sheet_name):
    logger.info(f"Attempting to find sheetId for sheet name '{sheet_name}' in spreadsheet '{spreadsheet_id}'.")
    metadata = api_get_spreadsheet_metadata(service, spreadsheet_id)
    for sheet_prop in metadata.get('sheets', []):
        properties = sheet_prop.get('properties', {})
        if properties.get('title') == sheet_name:
            sheet_id = properties.get('sheetId')
            if sheet_id is not None:
                logger.info(f"Found sheetId {sheet_id} for sheet name '{sheet_name}'.")
                return sheet_id
    logger.warning(f"Sheet name '{sheet_name}' not found in spreadsheet '{spreadsheet_id}'.")
    return None

def api_deduplicate_sheet_rows(service, spreadsheet_id, key_columns, sheet_name=None, sheet_id=None, header_rows=1, keep='first'):
    logger.info(f"Deduplication started for sheet in '{spreadsheet_id}'. Key columns: {key_columns}")
    
    # Input validation
    if sheet_name is None and sheet_id is None:
        raise ValueError("Either 'sheet_name' or 'sheet_id' must be provided.")
    if not isinstance(key_columns, list) or not all(isinstance(i, int) and i >= 0 for i in key_columns):
        raise ValueError("'key_columns' must be a list of non-negative integers.")
    if not key_columns: raise ValueError("'key_columns' cannot be empty.")
    if keep.lower() not in ['first', 'last']: raise ValueError("Invalid 'keep' option. Must be 'first' or 'last'.")
    
    numeric_sheet_id, sheet_identifier_for_get_api = None, None
    if sheet_id is not None:
        numeric_sheet_id = int(sheet_id)
        metadata = api_get_spreadsheet_metadata(service, spreadsheet_id)
        found_sheet = next((s['properties'] for s in metadata.get('sheets', []) if s['properties']['sheetId'] == numeric_sheet_id), None)
        if not found_sheet: raise ValueError(f"Sheet with ID {numeric_sheet_id} not found.")
        sheet_identifier_for_get_api = found_sheet['title']
    elif sheet_name:
        numeric_sheet_id = get_sheet_id_by_name(service, spreadsheet_id, sheet_name)
        if numeric_sheet_id is None: raise ValueError(f"Sheet name '{sheet_name}' not found.")
        sheet_identifier_for_get_api = sheet_name

    all_rows = api_get_values(service, spreadsheet_id, f"'{sheet_identifier_for_get_api}'")
    if not all_rows: return {"message": "Sheet is empty, no duplicates to remove.", "rows_deleted_count": 0}

    header_rows_count = int(header_rows)
    data_rows = all_rows[header_rows_count:]
    seen_keys, indices_to_delete_0_based = {}, []
    max_key_col_index = max(key_columns)

    for i, row_data in enumerate(data_rows):
        original_index_in_sheet = i + header_rows_count
        if len(row_data) <= max_key_col_index:
            continue # Skip rows too short to have the key, they can't be duplicates
        composite_key = tuple(row_data[k_idx] for k_idx in key_columns)
        
        if composite_key in seen_keys:
            if keep.lower() == 'first': indices_to_delete_0_based.append(original_index_in_sheet)
            else: # keep == 'last'
                indices_to_delete_0_based.append(seen_keys[composite_key])
                seen_keys[composite_key] = original_index_in_sheet
        else:
            seen_keys[composite_key] = original_index_in_sheet
    
    if not indices_to_delete_0_based:
        return {"message": "No duplicate rows found.", "rows_deleted_count": 0}

    # Sort indices in descending order to avoid shifting issues during deletion
    indices_to_delete_0_based = sorted(list(set(indices_to_delete_0_based)), reverse=True)
    delete_requests = [{"deleteDimension": {"range": {"sheetId": numeric_sheet_id, "dimension": "ROWS", "startIndex": idx, "endIndex": idx + 1}}} for idx in indices_to_delete_0_based]
    
    service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body={"requests": delete_requests}).execute()
    
    return {
        "message": f"Deduplication complete. {len(indices_to_delete_0_based)} row(s) removed.",
        "rows_deleted_count": len(indices_to_delete_0_based),
        "deleted_row_indices_0_based": indices_to_delete_0_based
    }

# --- NEW: Generic Request Handler ---
def _handle_sheets_request(required_fields, api_function):
    """
    A generic handler to process requests. It handles authentication,
    parameter validation, and execution for any Sheets API function.
    """
    endpoint_name = request.path
    try:
        # Step 1: Authenticate and get the service object
        service = get_sheets_service_from_header()
        
        # Step 2: Get JSON body and validate required fields
        data = request.json or {}
        if not all(k in data for k in required_fields):
            missing = [k for k in required_fields if k not in data]
            return jsonify({"success": False, "error": f"Missing required fields in JSON body: {', '.join(missing)}"}), 400
        
        # Step 3: Execute the corresponding API function with arguments from the body
        result = api_function(service, **data)
        
        # Step 4: Return a successful response
        return jsonify({"success": True, "details": result})

    except (ValueError, TypeError) as ve:
        # Handles bad input like missing headers, invalid JSON, or missing body fields
        logger.error(f"ENDPOINT {endpoint_name}: Input validation error: {ve}", exc_info=True)
        return jsonify({"success": False, "error": "Input or Authentication Error", "details": str(ve)}), 400
    except HttpError as e:
        error_content = json.loads(e.content.decode('utf-8')) if e.content else str(e)
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: An unexpected error occurred: {e}", exc_info=True)
        return jsonify({"success": False, "error": "An unexpected server error occurred", "details": str(e)}), 500


# --- Refactored Flask Endpoints ---
# All endpoints are now simplified to use the generic handler.

@app.route('/sheets/cell/update', methods=['POST'])
def update_cell_endpoint():
    return _handle_sheets_request(['spreadsheet_id', 'cell_range', 'new_value'], api_update_cell)

@app.route('/sheets/rows/append', methods=['POST'])
def append_rows_endpoint():
    return _handle_sheets_request(['spreadsheet_id', 'range_name', 'values_data'], api_append_rows)

@app.route('/sheets/values/get', methods=['POST'])
def get_values_endpoint():
    return _handle_sheets_request(['spreadsheet_id', 'range_name'], api_get_values)

@app.route('/sheets/rows/delete', methods=['POST'])
def delete_rows_endpoint():
    return _handle_sheets_request(['spreadsheet_id', 'sheet_id', 'start_row_index', 'end_row_index'], api_delete_rows)

@app.route('/sheets/tabs/create', methods=['POST'])
def create_tab_endpoint():
    return _handle_sheets_request(['spreadsheet_id', 'new_sheet_title'], api_create_new_tab)

@app.route('/sheets/values/clear', methods=['POST'])
def clear_values_endpoint():
    return _handle_sheets_request(['spreadsheet_id', 'range_name'], api_clear_values)

@app.route('/sheets/metadata', methods=['POST'])
def get_metadata_endpoint():
    return _handle_sheets_request(['spreadsheet_id'], api_get_spreadsheet_metadata)

@app.route('/sheets/sheet/read_all', methods=['POST'])
def read_entire_sheet_endpoint():
    # This API function expects 'sheet_name', not 'range_name'
    return _handle_sheets_request(['spreadsheet_id', 'sheet_name'], lambda service, **kwargs: api_get_values(service, spreadsheet_id=kwargs['spreadsheet_id'], range_name=kwargs['sheet_name']))

@app.route('/sheets/deduplicate', methods=['POST'])
def deduplicate_sheet_rows_endpoint():
    # This function has optional params, so we list only the strictly required ones.
    # The api_function will handle the optionals.
    return _handle_sheets_request(['spreadsheet_id', 'key_columns'], api_deduplicate_sheet_rows)

# --- Main Execution ---
if __name__ == "__main__":
    logger.info("Starting Flask application with Service Account authentication model...")
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
