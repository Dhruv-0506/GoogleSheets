from flask import Flask, jsonify, request
import os
import requests
import logging
import time

# Imports for Google API
from google.oauth2.credentials import Credentials as OAuthCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- Logging Configuration ---
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(name)s - %(module)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Configuration (Main App) ---
CLIENT_ID = "279113184789-n4u9s08ttu3kvk2qsr9cu8dpt08o1l9q.apps.googleusercontent.com"
CLIENT_SECRET = "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" # Ensure this is the correct secret for CLIENT_ID
TOKEN_URL = "https://oauth2.googleapis.com/token"
REDIRECT_URI = "https://serverless.on-demand.io/apps/googlesheets/auth/callback"
REQUEST_TIMEOUT_SECONDS = 30

# --- OAuth and Token Helper Functions (Main App) ---
def exchange_code_for_tokens(authorization_code):
    logger.info(f"Attempting to exchange authorization code for tokens. Code starts with: {authorization_code[:10]}...")
    start_time = time.time()
    if not CLIENT_SECRET:
        logger.error("CRITICAL: CLIENT_SECRET not set for token exchange.") # Simplified error message
        raise ValueError("CLIENT_SECRET not set.")
    payload = {
        "code": authorization_code, "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI, "grant_type": "authorization_code"
    }
    logger.debug(f"Token exchange payload (secrets redacted): { {k: (v if k not in ['client_secret', 'code'] else '...') for k,v in payload.items()} }")
    try:
        response = requests.post(TOKEN_URL, data=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        token_data = response.json()
        duration = time.time() - start_time
        if token_data.get("access_token"): # Refresh token is optional for some flows but good to have
            logger.info(f"Successfully exchanged code for tokens in {duration:.2f} seconds.")
            return token_data
        else:
            logger.error(f"Token exchange response missing access_token after {duration:.2f}s. Response: {token_data}")
            raise ValueError("Access token not found in response.")
    except requests.exceptions.Timeout:
        duration = time.time() - start_time
        logger.error(f"Timeout ({REQUEST_TIMEOUT_SECONDS}s) during token exchange after {duration:.2f} seconds.")
        raise
    except requests.exceptions.HTTPError as e:
        duration = time.time() - start_time
        logger.error(f"HTTPError ({e.response.status_code}) during token exchange after {duration:.2f} seconds: {e.response.text if e.response else str(e)}")
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Generic exception during token exchange after {duration:.2f} seconds: {str(e)}", exc_info=True)
        raise

def get_access_token(refresh_token):
    logger.info(f"Attempting to get new access token using refresh token (starts with: {refresh_token[:10]}...).")
    start_time = time.time()
    if not CLIENT_SECRET:
        logger.error("CRITICAL: CLIENT_SECRET not set for token refresh.") # Simplified error message
        raise ValueError("CLIENT_SECRET not set.")
    payload = {
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET, # Uses main CLIENT_ID and CLIENT_SECRET
        "refresh_token": refresh_token, "grant_type": "refresh_token"
    }
    logger.debug(f"Token refresh payload (secrets redacted): { {k: (v if k not in ['client_secret', 'refresh_token'] else '...') for k,v in payload.items()} }")
    try:
        response = requests.post(TOKEN_URL, data=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get("access_token")
        duration = time.time() - start_time
        if access_token:
            logger.info(f"Successfully obtained new access token via refresh in {duration:.2f} seconds. Expires in: {token_data.get('expires_in')}s")
            return access_token
        else:
            logger.error(f"Token refresh response missing access_token after {duration:.2f}s. Response: {token_data}")
            raise ValueError("Access token not found in refresh response.")
    except requests.exceptions.Timeout:
        duration = time.time() - start_time
        logger.error(f"Timeout ({REQUEST_TIMEOUT_SECONDS}s) during token refresh after {duration:.2f} seconds.")
        raise
    except requests.exceptions.HTTPError as e:
        duration = time.time() - start_time
        error_text = e.response.text if e.response else str(e)
        logger.error(f"HTTPError ({e.response.status_code}) during token refresh after {duration:.2f} seconds: {error_text}")
        if "invalid_grant" in error_text:
            logger.warning("Token refresh failed with 'invalid_grant'. Refresh token may be expired or revoked OR CLIENT_ID/CLIENT_SECRET mismatch for this token.")
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Generic exception during token refresh after {duration:.2f} seconds: {str(e)}", exc_info=True)
        raise

def get_sheets_service(access_token):
    logger.info("Building Google Sheets API service object...")
    if not access_token:
        logger.error("Cannot build sheets service: access_token is missing.")
        raise ValueError("Access token is required to build sheets service.")
    try:
        creds = OAuthCredentials(token=access_token)
        service = build("sheets", "v4", credentials=creds, cache_discovery=False) # Added cache_discovery=False for serverless envs
        logger.info("Google Sheets API service object built successfully.")
        return service
    except Exception as e:
        logger.error(f"Failed to build Google Sheets API service object: {str(e)}", exc_info=True)
        raise

# --- Google Sheets API Wrapper Functions (Main App) ---
def api_update_cell(service, spreadsheet_id, cell_range, new_value, value_input_option="USER_ENTERED"):
    logger.info(f"API: Updating cell '{cell_range}' in sheet '{spreadsheet_id}' to '{new_value}' with option '{value_input_option}'.")
    start_time = time.time()
    try:
        body = {"values": [[new_value]]}
        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id, range=cell_range, valueInputOption=value_input_option, body=body
        ).execute()
        duration = time.time() - start_time; logger.info(f"API: Cell update successful in {duration:.2f}s. Result: {result}"); return result
    except HttpError as e: duration = time.time() - start_time; error_content = e.content.decode('utf-8', 'ignore') if e.content else str(e); logger.error(f"API: HttpError updating cell after {duration:.2f}s: {error_content}", exc_info=True); raise
    except Exception as e: duration = time.time() - start_time; logger.error(f"API: Generic error updating cell after {duration:.2f}s: {str(e)}", exc_info=True); raise

def api_append_rows(service, spreadsheet_id, range_name, values_data, value_input_option="USER_ENTERED"):
    logger.info(f"API: Appending rows to sheet '{spreadsheet_id}', range '{range_name}', option '{value_input_option}'. Rows: {len(values_data)}")
    logger.debug(f"API: Values to append: {values_data}")
    start_time = time.time()
    try:
        body = {"values": values_data}
        result = service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id, range=range_name, valueInputOption=value_input_option, insertDataOption="INSERT_ROWS", body=body
        ).execute()
        duration = time.time() - start_time; logger.info(f"API: Row append successful in {duration:.2f}s. Updates: {result.get('updates')}"); return result
    except HttpError as e: duration = time.time() - start_time; error_content = e.content.decode('utf-8', 'ignore') if e.content else str(e); logger.error(f"API: HttpError appending rows after {duration:.2f}s: {error_content}", exc_info=True); raise
    except Exception as e: duration = time.time() - start_time; logger.error(f"API: Generic error appending rows after {duration:.2f}s: {str(e)}", exc_info=True); raise

def api_delete_rows(service, spreadsheet_id, sheet_id, start_row_index, end_row_index):
    logger.info(f"API: Deleting rows from sheet '{spreadsheet_id}', sheetId {sheet_id}, from index {start_row_index} to {end_row_index-1}.")
    start_time = time.time()
    try:
        requests_body = [{"deleteDimension": {"range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": start_row_index, "endIndex": end_row_index}}}]
        body = {"requests": requests_body}
        result = service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()
        duration = time.time() - start_time; logger.info(f"API: Row deletion successful in {duration:.2f}s. Result: {result}"); return result
    except HttpError as e: duration = time.time() - start_time; error_content = e.content.decode('utf-8', 'ignore') if e.content else str(e); logger.error(f"API: HttpError deleting rows after {duration:.2f}s: {error_content}", exc_info=True); raise
    except Exception as e: duration = time.time() - start_time; logger.error(f"API: Generic error deleting rows after {duration:.2f}s: {str(e)}", exc_info=True); raise

def api_create_new_tab(service, spreadsheet_id, new_sheet_title):
    logger.info(f"API: Creating new tab/sheet named '{new_sheet_title}' in spreadsheet '{spreadsheet_id}'.")
    start_time = time.time()
    try:
        requests_body = [{"addSheet": {"properties": {"title": new_sheet_title}}}]
        body = {"requests": requests_body}
        result = service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()
        duration = time.time() - start_time
        new_sheet_props = result.get('replies', [{}])[0].get('addSheet', {}).get('properties', {})
        logger.info(f"API: New tab creation successful in {duration:.2f}s. New sheet ID: {new_sheet_props.get('sheetId')}, Title: {new_sheet_props.get('title')}")
        return result
    except HttpError as e: duration = time.time() - start_time; error_content = e.content.decode('utf-8', 'ignore') if e.content else str(e); logger.error(f"API: HttpError creating new tab after {duration:.2f}s: {error_content}", exc_info=True); raise
    except Exception as e: duration = time.time() - start_time; logger.error(f"API: Generic error creating new tab after {duration:.2f}s: {str(e)}", exc_info=True); raise

def api_clear_values(service, spreadsheet_id, range_name):
    logger.info(f"API: Clearing values from sheet '{spreadsheet_id}', range '{range_name}'.")
    start_time = time.time()
    try:
        result = service.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=range_name, body={}).execute()
        duration = time.time() - start_time; logger.info(f"API: Values clear successful in {duration:.2f}s. Cleared range: {result.get('clearedRange')}"); return result
    except HttpError as e: duration = time.time() - start_time; error_content = e.content.decode('utf-8', 'ignore') if e.content else str(e); logger.error(f"API: HttpError clearing values after {duration:.2f}s: {error_content}", exc_info=True); raise
    except Exception as e: duration = time.time() - start_time; logger.error(f"API: Generic error clearing values after {duration:.2f}s: {str(e)}", exc_info=True); raise

def api_get_spreadsheet_metadata(service, spreadsheet_id):
    logger.info(f"API: Getting metadata for spreadsheet '{spreadsheet_id}'.")
    start_time = time.time()
    try:
        # Request specific fields to reduce response size and processing
        fields_to_get = "properties(title),sheets(properties(sheetId,title,index))"
        result = service.spreadsheets().get(spreadsheetId=spreadsheet_id, fields=fields_to_get).execute()
        duration = time.time() - start_time; logger.info(f"API: Metadata retrieval successful in {duration:.2f}s."); return result
    except HttpError as e: duration = time.time() - start_time; error_content = e.content.decode('utf-8', 'ignore') if e.content else str(e); logger.error(f"API: HttpError getting metadata after {duration:.2f}s: {error_content}", exc_info=True); raise
    except Exception as e: duration = time.time() - start_time; logger.error(f"API: Generic error getting metadata after {duration:.2f}s: {str(e)}", exc_info=True); raise

# --- NEW: API Wrapper function to get values ---


# --- Helper function for the /token endpoint (uses specific hardcoded values) ---
def get_specific_user_access_token():
    logger.info("Attempting to get access token for a specific pre-configured user.")
    specific_client_id = "26763482887-q9lcln5nmb0setr60gkohdjrt2msl6o5.apps.googleusercontent.com"
    specific_refresh_token = "1//09qu30gV5_1hZCgYIARAAGAkSNwF-L9IrEOR20gZnhzmvcFcU46oN89TXt-Sf7ET2SAUwx7d9wo0E2E2ISkXw4CxCDDNxouGAVo4"
    
    # IMPORTANT: Ensure THIS CLIENT_SECRET matches the one used when specific_refresh_token was generated with specific_client_id
    # If specific_client_id has its own secret, you should use that.
    # For this example, we are still using the global CLIENT_SECRET. This could be a point of error if mismatched.
    if not CLIENT_SECRET: # Assuming CLIENT_SECRET is for the main CLIENT_ID
        logger.error("CRITICAL: Main CLIENT_SECRET not set for specific user token refresh (used in payload).")
        raise ValueError("Main CLIENT_SECRET not set.")
        
    payload = {
        "client_id": specific_client_id, 
        "client_secret": CLIENT_SECRET, # This must be the secret for specific_client_id
        "refresh_token": specific_refresh_token, 
        "grant_type": "refresh_token"
    }
    logger.debug(f"Specific user token refresh payload (secrets redacted): { {k: (v if k not in ['client_secret', 'refresh_token'] else '...') for k,v in payload.items()} }")
    start_time = time.time()
    try:
        response = requests.post(TOKEN_URL, data=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get("access_token")
        duration = time.time() - start_time
        if access_token:
            logger.info(f"Successfully obtained access token for specific user in {duration:.2f}s. Expires in: {token_data.get('expires_in')}s")
            return access_token
        else:
            logger.error(f"Specific user token refresh response missing access_token after {duration:.2f}s. Response: {token_data}")
            raise ValueError("Access token not found in specific user refresh response.")
    except requests.exceptions.Timeout:
        duration = time.time() - start_time
        logger.error(f"Timeout ({REQUEST_TIMEOUT_SECONDS}s) during specific user token refresh after {duration:.2f} seconds.")
        raise
    except requests.exceptions.HTTPError as e:
        duration = time.time() - start_time
        error_text = e.response.text if e.response else str(e)
        logger.error(f"HTTPError ({e.response.status_code}) during specific user token refresh after {duration:.2f} seconds: {error_text}")
        if "invalid_grant" in error_text:
            logger.warning("Specific user token refresh failed with 'invalid_grant'. Refresh token may be expired/revoked OR client_id/client_secret mismatch.")
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Generic exception during specific user token refresh after {duration:.2f} seconds: {str(e)}", exc_info=True)
        raise

# --- NEW: API Wrapper function to get values ---
def api_get_values(service, spreadsheet_id, range_name):
    logger.info(f"API: Getting values from sheet '{spreadsheet_id}', range '{range_name}'.")
    start_time = time.time()
    try:
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()
        values = result.get('values', []) # Default to empty list if 'values' key is not present
        duration = time.time() - start_time
        logger.info(f"API: Values retrieval successful in {duration:.2f}s. Got {len(values)} rows.")
        # Limit logging for very large data, only if DEBUG is enabled
        if logger.isEnabledFor(logging.DEBUG):
            log_value_preview = values if len(values) < 5 else str(values[:5]) + f"... ({len(values) - 5} more rows)"
            logger.debug(f"API: Retrieved values: {log_value_preview}")
        return values
    except HttpError as e:
        duration = time.time() - start_time
        error_content = e.content.decode('utf-8', 'ignore') if e.content else str(e)
        logger.error(f"API: HttpError getting values after {duration:.2f}s from range '{range_name}': {error_content}", exc_info=True)
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"API: Generic error getting values after {duration:.2f}s from range '{range_name}': {str(e)}", exc_info=True)
        raise
# --- END NEW ---


# --- Flask Endpoints (Main App) ---
@app.route('/auth/callback', methods=['GET'])
def oauth2callback_endpoint():
    endpoint_name = "/auth/callback"; logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    authorization_code = request.args.get('code')
    if authorization_code:
        try:
            token_data = exchange_code_for_tokens(authorization_code)
            logger.info(f"ENDPOINT {endpoint_name}: Authorization successful, tokens obtained.")
            # It's good practice to list what's in token_data for clarity, redacting sensitive parts.
            redacted_tokens = {k: (v if k not in ['access_token', 'refresh_token', 'id_token'] else '***') for k,v in token_data.items()}
            return jsonify({"message": "Authorization successful. IMPORTANT: Securely store the refresh_token if present.", "tokens_info": redacted_tokens})
        except Exception as e:
            logger.error(f"ENDPOINT {endpoint_name}: Error during token exchange: {str(e)}", exc_info=True)
            return jsonify({"error": f"Failed to exchange authorization code for tokens: {str(e)}"}), 500
    else:
        logger.warning(f"ENDPOINT {endpoint_name}: Authorization code missing in request.")
        return jsonify({"error": "Authorization code missing"}), 400

@app.route('/sheets/cell/update', methods=['POST'])
def update_cell_endpoint():
    
    try:
        data = request.json; logger.debug(f"ENDPOINT : Request body: {data}")
        if not data or not all(k in data for k in ('cell_range', 'new_value', 'refresh_token')): # Check if data is None
            logger.warning(f"ENDPOINT : Missing required fields in JSON body.")
            return jsonify({"success": False, "error": "Missing 'cell_range', 'new_value', or 'refresh_token' in JSON body"}), 400
        spreadsheet_id = data['spreadsheet_id']
        endpoint_name = f"/sheets/{spreadsheet_id}/cell/update"; logger.info(f"ENDPOINT {endpoint_name}: Request received.")
        cell_range = data['cell_range']; new_value = data['new_value']; refresh_token = data['refresh_token']
        value_input_option = data.get('value_input_option', "USER_ENTERED")
        access_token = get_access_token(refresh_token); service = get_sheets_service(access_token)
        result = api_update_cell(service, spreadsheet_id, cell_range, new_value, value_input_option)
        logger.info(f"ENDPOINT {endpoint_name}: Cell update successful.")
        return jsonify({"success": True, "message": "Cell updated successfully.", "details": result})
    except HttpError as e: error_content = e.content.decode('utf-8', 'ignore') if e.content else str(e); logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True); return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status if hasattr(e, 'resp') and e.resp else 500
    except ValueError as ve: logger.error(f"ENDPOINT {endpoint_name}: Value error: {str(ve)}", exc_info=True); return jsonify({"success": False, "error": f"Input or authentication error: {str(ve)}"}), 400
    except Exception as e: logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True); return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/sheets/rows/append', methods=['POST'])
def append_rows_endpoint():
    
    try:
        data = request.json; logger.debug(f"ENDPOINT : Request body: {data}")
        if not data or not all(k in data for k in ('range_name', 'values_data', 'refresh_token')):
            logger.warning(f"ENDPOINT : Missing required fields in JSON body.")
            return jsonify({"success": False, "error": "Missing 'range_name', 'values_data', or 'refresh_token' in JSON body"}), 400
        range_name = data['range_name']; values_data = data['values_data']; refresh_token = data['refresh_token']
        value_input_option = data.get('value_input_option', "USER_ENTERED")
        if not isinstance(values_data, list) or not all(isinstance(row, list) for row in values_data):
            logger.warning(f"ENDPOINT {endpoint_name}: 'values_data' is not a list of lists.")
            return jsonify({"success": False, "error": "'values_data' must be a list of lists (rows of cells)."}), 400
        spreadsheet_id = data['spreadsheet_id']
        endpoint_name = f"/sheets/{spreadsheet_id}/rows/append"; logger.info(f"ENDPOINT {endpoint_name}: Request received.")
        access_token = get_access_token(refresh_token); service = get_sheets_service(access_token)
        result = api_append_rows(service, spreadsheet_id, range_name, values_data, value_input_option)
        logger.info(f"ENDPOINT {endpoint_name}: Row append successful.")
        return jsonify({"success": True, "message": "Rows appended successfully.", "details": result.get("updates")})
    except HttpError as e: error_content = e.content.decode('utf-8', 'ignore') if e.content else str(e); logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True); return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status if hasattr(e, 'resp') and e.resp else 500
    except ValueError as ve: logger.error(f"ENDPOINT {endpoint_name}: Value error: {str(ve)}", exc_info=True); return jsonify({"success": False, "error": f"Input or authentication error: {str(ve)}"}), 400
    except Exception as e: logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True); return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

# --- NEW: Endpoint to get values ---
@app.route('/sheets/values/get', methods=['POST'])
def get_values_endpoint():
    
    logger.info(f"ENDPOINT : Request received.")
    try:
        data = request.json
        logger.debug(f"ENDPOINT : Request body: {data}")
        if not data or not all(k in data for k in ('range_name', 'refresh_token')):
            logger.warning(f"ENDPOINT : Missing 'range_name' or 'refresh_token' in JSON body.")
            return jsonify({"success": False, "error": "Missing 'range_name' or 'refresh_token' in JSON body"}), 400
        range_name = data['range_name']; refresh_token = data['refresh_token']
        if not range_name:
            logger.warning(f"ENDPOINT : 'range_name' cannot be empty.")
            return jsonify({"success": False, "error": "'range_name' cannot be empty"}), 400
        spreadsheet_id = data['spreadsheet_id']
        endpoint_name = f"/sheets/{spreadsheet_id}/values/get"
        access_token = get_access_token(refresh_token) 
        service = get_sheets_service(access_token)
        values = api_get_values(service, spreadsheet_id, range_name)
        logger.info(f"ENDPOINT {endpoint_name}: Successfully retrieved values from range '{range_name}'.")
        return jsonify({"success": True, "spreadsheet_id": spreadsheet_id, "range_queried": range_name, "values": values})
    except HttpError as e: error_content = e.content.decode('utf-8', 'ignore') if e.content else str(e); logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True); return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status if hasattr(e, 'resp') and e.resp else 500
    except ValueError as ve: logger.error(f"ENDPOINT {endpoint_name}: Value error: {str(ve)}", exc_info=True); return jsonify({"success": False, "error": f"Input or authentication error: {str(ve)}"}), 400
    except Exception as e: logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True); return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500
# --- END NEW ---

@app.route('/sheets/rows/delete', methods=['POST'])
def delete_rows_endpoint():
    
    try:
        data = request.json; logger.debug(f"ENDPOINT : Request body: {data}")
        if not data or not all(k in data for k in ('sheet_id', 'start_row_index', 'end_row_index', 'refresh_token')):
            logger.warning(f"ENDPOINT : Missing required fields in JSON body.")
            return jsonify({"success": False, "error": "Missing 'sheet_id', 'start_row_index', 'end_row_index', or 'refresh_token' in JSON body"}), 400
        sheet_id = int(data['sheet_id']); start_row_index = int(data['start_row_index']); end_row_index = int(data['end_row_index']); refresh_token = data['refresh_token']
        if start_row_index < 0 or end_row_index <= start_row_index:
            logger.warning(f"ENDPOINT : Invalid row indices.")
            return jsonify({"success": False, "error": "Invalid 'start_row_index' or 'end_row_index'. Ensure start < end and both >= 0."}), 400
        spreadsheet_id = data['spreadsheet_id']
        endpoint_name = f"/sheets/{spreadsheet_id}/rows/delete"; logger.info(f"ENDPOINT {endpoint_name}: Request received.")
        access_token = get_access_token(refresh_token); service = get_sheets_service(access_token)
        result = api_delete_rows(service, spreadsheet_id, sheet_id, start_row_index, end_row_index)
        logger.info(f"ENDPOINT {endpoint_name}: Row deletion request successful.")
        return jsonify({"success": True, "message": "Row deletion request processed.", "details": result})
    except ValueError: logger.warning(f"ENDPOINT {endpoint_name}: Invalid non-integer input for sheet_id or row indices.", exc_info=True); return jsonify({"success": False, "error": "sheet_id, start_row_index, and end_row_index must be integers."}), 400
    except HttpError as e: error_content = e.content.decode('utf-8', 'ignore') if e.content else str(e); logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True); return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status if hasattr(e, 'resp') and e.resp else 500
    except Exception as e: logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True); return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/sheets/tabs/create', methods=['POST'])
def create_tab_endpoint():
    
    try:
        data = request.json; logger.debug(f"ENDPOINT : Request body: {data}")
        if not data or not all(k in data for k in ('new_sheet_title', 'refresh_token')):
            logger.warning(f"ENDPOINT : Missing required fields in JSON body.")
            return jsonify({"success": False, "error": "Missing 'new_sheet_title' or 'refresh_token' in JSON body"}), 400
        spreadsheet_id = data['spreadsheet_id']
        endpoint_name = f"/sheets/{spreadsheet_id}/tabs/create"; logger.info(f"ENDPOINT {endpoint_name}: Request received.")
        new_sheet_title = data['new_sheet_title']; refresh_token = data['refresh_token']
        access_token = get_access_token(refresh_token); service = get_sheets_service(access_token)
        result = api_create_new_tab(service, spreadsheet_id, new_sheet_title)
        new_sheet_props = result.get('replies', [{}])[0].get('addSheet', {}).get('properties', {})
        logger.info(f"ENDPOINT {endpoint_name}: New tab creation successful.")
        return jsonify({"success": True, "message": "New tab/sheet created successfully.", "new_sheet_properties": new_sheet_props})
    except HttpError as e: error_content = e.content.decode('utf-8', 'ignore') if e.content else str(e); logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True); return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status if hasattr(e, 'resp') and e.resp else 500
    except ValueError as ve: logger.error(f"ENDPOINT {endpoint_name}: Value error: {str(ve)}", exc_info=True); return jsonify({"success": False, "error": f"Input or authentication error: {str(ve)}"}), 400
    except Exception as e: logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True); return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/sheets/values/clear', methods=['POST'])
def clear_values_endpoint():
    
    try:
        data = request.json; logger.debug(f"ENDPOINT : Request body: {data}")
        if not data or not all(k in data for k in ('range_name', 'refresh_token')):
            logger.warning(f"ENDPOINT: Missing required fields in JSON body.")
            return jsonify({"success": False, "error": "Missing 'range_name' or 'refresh_token' in JSON body"}), 400
        spreadsheet_id = data['spreadsheet_id']
        endpoint_name = f"/sheets/{spreadsheet_id}/values/clear"; logger.info(f"ENDPOINT {endpoint_name}: Request received.")
        range_name = data['range_name']; refresh_token = data['refresh_token']
        access_token = get_access_token(refresh_token); service = get_sheets_service(access_token)
        result = api_clear_values(service, spreadsheet_id, range_name)
        logger.info(f"ENDPOINT {endpoint_name}: Values clear successful.")
        return jsonify({"success": True, "message": "Values cleared successfully.", "details": result})
    except HttpError as e: error_content = e.content.decode('utf-8', 'ignore') if e.content else str(e); logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True); return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status if hasattr(e, 'resp') and e.resp else 500
    except ValueError as ve: logger.error(f"ENDPOINT {endpoint_name}: Value error: {str(ve)}", exc_info=True); return jsonify({"success": False, "error": f"Input or authentication error: {str(ve)}"}), 400
    except Exception as e: logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True); return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/sheets/metadata', methods=['POST'])
def get_metadata_endpoint():
    
    try:
        data = request.json # Changed to get refresh_token from JSON body
        logger.debug(f"ENDPOINT : Request body: {data}")
        if not data or 'refresh_token' not in data:
            logger.warning(f"ENDPOINT: Missing 'refresh_token' in JSON body.")
            return jsonify({"success": False, "error": "Missing 'refresh_token' in JSON body"}), 400
        spreadsheet_id = data['spreadsheet_id']
        endpoint_name = f"/sheets/{spreadsheet_id}/metadata"; logger.info(f"ENDPOINT {endpoint_name}: Request received.")
        refresh_token = data['refresh_token']
        access_token = get_access_token(refresh_token); service = get_sheets_service(access_token)
        metadata = api_get_spreadsheet_metadata(service, spreadsheet_id)
        logger.info(f"ENDPOINT {endpoint_name}: Metadata retrieval successful.")
        return jsonify({"success": True, "metadata": metadata})
    except HttpError as e: error_content = e.content.decode('utf-8', 'ignore') if e.content else str(e); logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True); return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status if hasattr(e, 'resp') and e.resp else 500
    except ValueError as ve: logger.error(f"ENDPOINT {endpoint_name}: Value error: {str(ve)}", exc_info=True); return jsonify({"success": False, "error": f"Input or authentication error: {str(ve)}"}), 400
    except Exception as e: logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True); return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/token', methods=['GET'])
def specific_user_token_endpoint():
    endpoint_name = "/token"; logger.info(f"ENDPOINT {endpoint_name}: Request received to get specific user access token.")
    try:
        access_token = get_specific_user_access_token()
        logger.info(f"ENDPOINT {endpoint_name}: Successfully obtained access token for specific user.")
        return jsonify({"success": True, "access_token": access_token})
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Failed to get specific user access token: {str(e)}", exc_info=True)
        # Check for HttpError specifically for status code
        status_code = 500
        if isinstance(e, HttpError) and hasattr(e, 'resp') and e.resp is not None:
            status_code = e.resp.status
        elif isinstance(e, ValueError): # Often indicates bad input or auth logic problem before API call
            status_code = 400
        return jsonify({"success": False, "error": f"Failed to obtain access token: {str(e)}"}), status_code

def get_sheet_id_by_name(service, spreadsheet_id, sheet_name):
    logger.info(f"Attempting to find sheetId for sheet name '{sheet_name}' in spreadsheet '{spreadsheet_id}'.")
    try:
        metadata = api_get_spreadsheet_metadata(service, spreadsheet_id)
        for sheet_prop in metadata.get('sheets', []):
            properties = sheet_prop.get('properties', {})
            if properties.get('title') == sheet_name:
                sheet_id = properties.get('sheetId')
                if sheet_id is not None:
                    logger.info(f"Found sheetId {sheet_id} for sheet name '{sheet_name}'.")
                    return sheet_id
        logger.warning(f"Sheet name '{sheet_name}' not found in spreadsheet '{spreadsheet_id}'.") # Removed metadata dump
        return None
    except Exception as e:
        logger.error(f"Error getting sheetId for sheet name '{sheet_name}': {str(e)}", exc_info=True)
        raise # Re-raise to be caught by the endpoint's general exception handler

@app.route('/sheets/deduplicate', methods=['POST'])
def deduplicate_sheet_rows_endpoint():
    
    try:
        data = request.json; logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")
        required_fields = ['refresh_token', 'key_columns']
        if not data or not (data.get('sheet_name') or data.get('sheet_id') is not None):
            logger.warning(f"ENDPOINT: Missing 'sheet_name' or 'sheet_id' in JSON body.")
            return jsonify({"success": False, "error": "Missing 'sheet_name' or 'sheet_id' in JSON body"}), 400
        if not all(k in data for k in required_fields):
            logger.warning(f"ENDPOINT : Missing required fields among {required_fields} in JSON body.")
            return jsonify({"success": False, "error": f"Missing one or more required fields: {', '.join(required_fields)} in JSON body"}), 400
        refresh_token = data['refresh_token']; key_column_indices = data['key_columns']
        sheet_name_param = data.get('sheet_name'); sheet_id_param = data.get('sheet_id')
        header_rows_count = int(data.get('header_rows', 1)); keep_option = data.get('keep', 'first').lower()
        if not isinstance(key_column_indices, list) or not all(isinstance(i, int) and i >= 0 for i in key_column_indices):
            return jsonify({"success": False, "error": "'key_columns' must be a list of non-negative integers (0-based column indices)."}), 400
        if not key_column_indices: return jsonify({"success": False, "error": "'key_columns' cannot be empty."}), 400
        if keep_option not in ['first', 'last']: return jsonify({"success": False, "error": "Invalid 'keep' option. Must be 'first' or 'last'."}), 400

        spreadsheet_id = data['spreadsheet_id']
        endpoint_name = f"/sheets/{spreadsheet_id}/deduplicate"; logger.info(f"ENDPOINT {endpoint_name}: Request received.")
        access_token = get_access_token(refresh_token); service = get_sheets_service(access_token)
        numeric_sheet_id = None; sheet_identifier_for_get_api = None
        if sheet_id_param is not None:
            numeric_sheet_id = int(sheet_id_param) # ValueError caught by general handler
            metadata = api_get_spreadsheet_metadata(service, spreadsheet_id)
            found_sheet = next((s['properties'] for s in metadata.get('sheets', []) if s['properties']['sheetId'] == numeric_sheet_id), None)
            if not found_sheet: return jsonify({"success": False, "error": f"Sheet with ID {numeric_sheet_id} not found."}), 404
            sheet_identifier_for_get_api = found_sheet['title']; logger.info(f"Using provided sheet_id: {numeric_sheet_id} (Title: {sheet_identifier_for_get_api}).")
        elif sheet_name_param:
            numeric_sheet_id = get_sheet_id_by_name(service, spreadsheet_id, sheet_name_param)
            if numeric_sheet_id is None: return jsonify({"success": False, "error": f"Sheet name '{sheet_name_param}' not found."}), 404
            sheet_identifier_for_get_api = sheet_name_param; logger.info(f"Using sheet_name: '{sheet_name_param}', found sheet_id: {numeric_sheet_id}.")
        else: return jsonify({"success": False, "error": "Sheet identifier (name or id) is missing."}), 400
        range_to_get = f"'{sheet_identifier_for_get_api}'!A:ZZ"; logger.info(f"ENDPOINT {endpoint_name}: Fetching data from range: {range_to_get}")
        try: result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=range_to_get).execute()
        except HttpError as he_get:
            if he_get.resp.status == 400 and "Unable to parse range" in str(he_get):
                 logger.warning(f"ENDPOINT {endpoint_name}: Could not parse range '{range_to_get}'. Trying to fetch just '{sheet_identifier_for_get_api}'.")
                 result = service.spreadsheets().values().get(spreadsheetId=spreadsheet_id, range=sheet_identifier_for_get_api).execute()
            else: raise
        all_rows_from_sheet = result.get('values', [])
        if not all_rows_from_sheet: return jsonify({"success": True, "message": "Sheet is empty, no duplicates to remove.", "rows_deleted_count": 0})
        logger.info(f"ENDPOINT {endpoint_name}: Fetched {len(all_rows_from_sheet)} rows from sheet '{sheet_identifier_for_get_api}'.")
        data_rows_with_original_indices = [{'data': row_content, 'original_index_in_sheet': i} for i, row_content in enumerate(all_rows_from_sheet) if i >= header_rows_count]
        if not data_rows_with_original_indices: return jsonify({"success": True, "message": "No data rows to process after headers.", "rows_deleted_count": 0})
        seen_keys = {}; indices_to_delete_0_based = [] 
        max_key_col_index = max(key_column_indices) if key_column_indices else -1 # handle empty key_columns defensively
        for row_info in data_rows_with_original_indices:
            row_data = row_info['data']; current_original_index = row_info['original_index_in_sheet']
            composite_key_parts = []
            # Check if row is long enough for all key columns
            is_row_too_short_for_all_keys = len(row_data) <= max_key_col_index if max_key_col_index >=0 else False
            for k_idx in key_column_indices:
                if k_idx < len(row_data): composite_key_parts.append(row_data[k_idx])
                else: composite_key_parts.append(None) # Use None for missing cells in key
            composite_key = tuple(composite_key_parts)
            if is_row_too_short_for_all_keys:
                logger.debug(f"Row {current_original_index+1} (0-idx {current_original_index}) is short. Key generated: {composite_key}. Treating as unique for safety unless an identical short row key is found.")
            if composite_key in seen_keys:
                if keep_option == 'first': indices_to_delete_0_based.append(current_original_index)
                elif keep_option == 'last': indices_to_delete_0_based.append(seen_keys[composite_key]); seen_keys[composite_key] = current_original_index
            else: seen_keys[composite_key] = current_original_index
        if not indices_to_delete_0_based: return jsonify({"success": True, "message": "No duplicate rows found.", "rows_deleted_count": 0})
        indices_to_delete_0_based = sorted(list(set(indices_to_delete_0_based)), reverse=True)
        logger.info(f"ENDPOINT {endpoint_name}: Identified {len(indices_to_delete_0_based)} rows for deletion. Indices: {indices_to_delete_0_based}")
        delete_requests = [{"deleteDimension": {"range": {"sheetId": numeric_sheet_id, "dimension": "ROWS", "startIndex": row_idx_to_delete, "endIndex": row_idx_to_delete + 1}}} for row_idx_to_delete in indices_to_delete_0_based]
        if delete_requests:
            body = {"requests": delete_requests}; logger.info(f"ENDPOINT {endpoint_name}: Sending batchUpdate to delete {len(delete_requests)} rows.")
            start_time_delete = time.time()
            service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()
            duration_delete = time.time() - start_time_delete; logger.info(f"ENDPOINT {endpoint_name}: Batch deletion successful in {duration_delete:.2f}s.")
        return jsonify({"success": True, "message": f"Deduplication complete. {len(indices_to_delete_0_based)} row(s) removed.", "rows_deleted_count": len(indices_to_delete_0_based), "deleted_row_indices_0_based": indices_to_delete_0_based})
    except HttpError as e: error_content = e.content.decode('utf-8', 'ignore') if e.content else str(e); logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True); return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status if hasattr(e, 'resp') and e.resp else 500
    except ValueError as ve: logger.error(f"ENDPOINT {endpoint_name}: Value error: {str(ve)}", exc_info=True); return jsonify({"success": False, "error": f"Invalid input value: {str(ve)}"}), 400
    except Exception as e: logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True); return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500


# NEW ROUTE ----------------------------------------------------------------------------------------------------------------------------
@app.route('/sheets/sheet/read_all', methods=['POST'])
def read_entire_sheet_endpoint():
    # Use the literal route path for initial logs before spreadsheet_id is confirmed
    route_path_literal = "/sheets/sheet/read_all" 
    logger.info(f"ENDPOINT {route_path_literal}: Request received.")
    
    try:
        data = request.json
        if not data:
            logger.warning(f"ENDPOINT {route_path_literal}: Request body is missing or not valid JSON.")
            return jsonify({"success": False, "error": "Request body is missing or not valid JSON."}), 400
        
        # Consistent debug log after confirming data exists
        logger.debug(f"ENDPOINT {route_path_literal}: Request body: {data}")

        # Check for all required fields, including spreadsheet_id
        required_fields = ['spreadsheet_id', 'sheet_name', 'refresh_token']
        if not all(k in data for k in required_fields):
            missing = [k for k in required_fields if k not in data]
            logger.warning(f"ENDPOINT {route_path_literal}: Missing required fields: {', '.join(missing)} in JSON body.")
            return jsonify({"success": False, "error": f"Missing required fields: {', '.join(missing)} in JSON body"}), 400

        spreadsheet_id = data['spreadsheet_id']
        sheet_name = data['sheet_name'] # Expecting 'sheet_name' for clarity
        refresh_token = data['refresh_token']

        # Define endpoint_name AFTER spreadsheet_id is successfully extracted, similar to other endpoints
        # It typically includes the spreadsheet_id but not other dynamic parts like sheet_name for the base endpoint_name.
        endpoint_name = f"/sheets/{spreadsheet_id}/sheet/read_all"
        # Log with the specific endpoint_name now that it's defined
        logger.info(f"ENDPOINT {endpoint_name}: Processing request to read sheet '{sheet_name}'.")

        access_token = get_access_token(refresh_token)
        service = get_sheets_service(access_token)
        
        # Use sheet_name directly as the range for api_get_values.
        # The Google Sheets API interprets "SheetTitle" as the entire range of that sheet.
        values = api_get_values(service, spreadsheet_id, sheet_name) 
        
        logger.info(f"ENDPOINT {endpoint_name}: Successfully retrieved all values ({len(values)} rows) from sheet '{sheet_name}'.")
        return jsonify({
            "success": True, 
            "spreadsheet_id": spreadsheet_id, 
            "sheet_name_queried": sheet_name, 
            "values": values
        })

    except HttpError as e:
        # endpoint_name should be defined if we've passed the initial checks
        # If an error occurs before spreadsheet_id is parsed (e.g., data is not JSON),
        # endpoint_name might not be defined. The initial checks try to prevent this.
        log_context_name = endpoint_name if 'endpoint_name' in locals() else route_path_literal
        error_content = e.content.decode('utf-8', 'ignore') if e.content else str(e)
        logger.error(f"ENDPOINT {log_context_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status if hasattr(e, 'resp') and e.resp else 500
    except ValueError as ve:
        log_context_name = endpoint_name if 'endpoint_name' in locals() else route_path_literal
        logger.error(f"ENDPOINT {log_context_name}: Value error: {str(ve)}", exc_info=True)
        return jsonify({"success": False, "error": f"Input or authentication error: {str(ve)}"}), 400
    except Exception as e:
        log_context_name = endpoint_name if 'endpoint_name' in locals() else route_path_literal
        logger.error(f"ENDPOINT {log_context_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500
#NEW ROUTE END------------------------------------------------------------------------------------------------------------------------------------------------------------------




# Run Flask
if __name__ == "__main__":
    if not CLIENT_SECRET:
        logger.critical("CRITICAL STARTUP ERROR: CLIENT_SECRET is not set.") # Simplified message
        print("CRITICAL ERROR: CLIENT_SECRET is not set. The application will likely fail on token operations.")
        print("Please ensure CLIENT_SECRET is correctly defined at the top of the script.")
    else:
        logger.info(f"CLIENT_SECRET is loaded (length: {len(CLIENT_SECRET)}).")
    logger.info("Starting Flask application...")
    # For Render, Gunicorn will be used, so this app.run is mainly for local dev
    # Render uses the PORT environment variable.
    port = int(os.environ.get("PORT", 5000))
    app.run(debug=False, host="0.0.0.0", port=port) # debug=False for production-like behavior
