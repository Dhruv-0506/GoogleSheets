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

# --- Configuration ---
# IMPORTANT: Ensure this Client ID matches the one used for generating the authorization code
# and is configured with the correct redirect URI in Google Cloud Console.
CLIENT_ID = "26763482887-coiufpukc1l69aaulaiov5o0u3en2del.apps.googleusercontent.com"
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET") # Ensure this is set in your environment
TOKEN_URL = "https://oauth2.googleapis.com/token"
# This redirect URI must be authorized in your Google Cloud Console for the Client ID
REDIRECT_URI = "https://serverless.on-demand.io/auth/callback" # Or your local/dev redirect URI

REQUEST_TIMEOUT_SECONDS = 30

# --- OAuth and Token Helper Functions ---

def exchange_code_for_tokens(authorization_code):
    logger.info(f"Attempting to exchange authorization code for tokens. Code starts with: {authorization_code[:10]}...")
    start_time = time.time()

    if not CLIENT_SECRET:
        logger.error("CRITICAL: GOOGLE_CLIENT_SECRET environment variable not set for token exchange.")
        raise ValueError("GOOGLE_CLIENT_SECRET environment variable not set.")

    payload = {
        "code": authorization_code,
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "redirect_uri": REDIRECT_URI,
        "grant_type": "authorization_code"
    }
    logger.debug(f"Token exchange payload (secrets redacted): { {k: (v if k not in ['client_secret', 'code'] else '...') for k,v in payload.items()} }")

    try:
        response = requests.post(TOKEN_URL, data=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        token_data = response.json()
        duration = time.time() - start_time
        if token_data.get("access_token") and token_data.get("refresh_token"):
            logger.info(f"Successfully exchanged code for tokens in {duration:.2f} seconds.")
            return token_data
        else:
            logger.error(f"Token exchange response missing access_token or refresh_token after {duration:.2f}s. Response: {token_data}")
            raise ValueError("Access token or refresh token not found in response.")
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
        logger.error("CRITICAL: GOOGLE_CLIENT_SECRET environment variable not set for token refresh.")
        raise ValueError("GOOGLE_CLIENT_SECRET environment variable not set.")

    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
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
        logger.error(f"HTTPError ({e.response.status_code}) during token refresh after {duration:.2f} seconds: {e.response.text if e.response else str(e)}")
        # Common issue: "invalid_grant" if refresh token is expired/revoked
        if "invalid_grant" in (e.response.text if e.response else ""):
            logger.warning("Token refresh failed with 'invalid_grant'. Refresh token may be expired or revoked.")
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
        service = build("sheets", "v4", credentials=creds)
        logger.info("Google Sheets API service object built successfully.")
        return service
    except Exception as e:
        logger.error(f"Failed to build Google Sheets API service object: {str(e)}", exc_info=True)
        raise

# --- Google Sheets API Wrapper Functions (using google-api-python-client) ---

def api_update_cell(service, spreadsheet_id, cell_range, new_value, value_input_option="USER_ENTERED"):
    logger.info(f"API: Updating cell '{cell_range}' in sheet '{spreadsheet_id}' to '{new_value}' with option '{value_input_option}'.")
    start_time = time.time()
    try:
        body = {"values": [[new_value]]} # Values is a list of lists (rows)
        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=cell_range,
            valueInputOption=value_input_option,
            body=body
        ).execute()
        duration = time.time() - start_time
        logger.info(f"API: Cell update successful in {duration:.2f}s. Result: {result}")
        return result
    except HttpError as e:
        duration = time.time() - start_time
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"API: HttpError updating cell after {duration:.2f}s: {error_content}", exc_info=True)
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"API: Generic error updating cell after {duration:.2f}s: {str(e)}", exc_info=True)
        raise

def api_append_rows(service, spreadsheet_id, range_name, values_data, value_input_option="USER_ENTERED"):
    logger.info(f"API: Appending rows to sheet '{spreadsheet_id}', range '{range_name}', option '{value_input_option}'. Rows: {len(values_data)}")
    logger.debug(f"API: Values to append: {values_data}")
    start_time = time.time()
    try:
        body = {"values": values_data}
        result = service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name, # e.g., "Sheet1" or "Sheet1!A1" (appends after last data in this range)
            valueInputOption=value_input_option,
            insertDataOption="INSERT_ROWS", # Other option: "OVERWRITE"
            body=body
        ).execute()
        duration = time.time() - start_time
        logger.info(f"API: Row append successful in {duration:.2f}s. Updates: {result.get('updates')}")
        return result
    except HttpError as e:
        duration = time.time() - start_time
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"API: HttpError appending rows after {duration:.2f}s: {error_content}", exc_info=True)
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"API: Generic error appending rows after {duration:.2f}s: {str(e)}", exc_info=True)
        raise

def api_delete_rows(service, spreadsheet_id, sheet_id, start_row_index, end_row_index):
    # Note: start_row_index is 0-based and inclusive. end_row_index is 0-based and exclusive.
    # To delete row 1 (user view), use start_row_index=0, end_row_index=1.
    # To delete rows 5-7 (user view), use start_row_index=4, end_row_index=7.
    logger.info(f"API: Deleting rows from sheet '{spreadsheet_id}', sheetId {sheet_id}, from index {start_row_index} to {end_row_index-1}.")
    start_time = time.time()
    try:
        requests_body = [{
            "deleteDimension": {
                "range": {
                    "sheetId": sheet_id,
                    "dimension": "ROWS",
                    "startIndex": start_row_index,
                    "endIndex": end_row_index
                }
            }
        }]
        body = {"requests": requests_body}
        result = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body
        ).execute()
        duration = time.time() - start_time
        logger.info(f"API: Row deletion successful in {duration:.2f}s. Result: {result}")
        return result
    except HttpError as e:
        duration = time.time() - start_time
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"API: HttpError deleting rows after {duration:.2f}s: {error_content}", exc_info=True)
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"API: Generic error deleting rows after {duration:.2f}s: {str(e)}", exc_info=True)
        raise

def api_create_new_tab(service, spreadsheet_id, new_sheet_title):
    logger.info(f"API: Creating new tab/sheet named '{new_sheet_title}' in spreadsheet '{spreadsheet_id}'.")
    start_time = time.time()
    try:
        requests_body = [{
            "addSheet": {
                "properties": {
                    "title": new_sheet_title
                    # You can add other properties like "index" to control position
                }
            }
        }]
        body = {"requests": requests_body}
        result = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=body
        ).execute()
        duration = time.time() - start_time
        new_sheet_props = result.get('replies', [{}])[0].get('addSheet', {}).get('properties', {})
        logger.info(f"API: New tab creation successful in {duration:.2f}s. New sheet ID: {new_sheet_props.get('sheetId')}, Title: {new_sheet_props.get('title')}")
        return result
    except HttpError as e:
        duration = time.time() - start_time
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"API: HttpError creating new tab after {duration:.2f}s: {error_content}", exc_info=True)
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"API: Generic error creating new tab after {duration:.2f}s: {str(e)}", exc_info=True)
        raise

def api_clear_values(service, spreadsheet_id, range_name):
    logger.info(f"API: Clearing values from sheet '{spreadsheet_id}', range '{range_name}'.")
    start_time = time.time()
    try:
        result = service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            body={} # Clear request has an empty body
        ).execute()
        duration = time.time() - start_time
        logger.info(f"API: Values clear successful in {duration:.2f}s. Cleared range: {result.get('clearedRange')}")
        return result
    except HttpError as e:
        duration = time.time() - start_time
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"API: HttpError clearing values after {duration:.2f}s: {error_content}", exc_info=True)
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"API: Generic error clearing values after {duration:.2f}s: {str(e)}", exc_info=True)
        raise

def api_get_spreadsheet_metadata(service, spreadsheet_id):
    logger.info(f"API: Getting metadata for spreadsheet '{spreadsheet_id}'.")
    start_time = time.time()
    try:
        # You can specify fields="sheets.properties" to get only sheet names and IDs
        result = service.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="properties,sheets.properties").execute()
        duration = time.time() - start_time
        logger.info(f"API: Metadata retrieval successful in {duration:.2f}s.")
        return result
    except HttpError as e:
        duration = time.time() - start_time
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"API: HttpError getting metadata after {duration:.2f}s: {error_content}", exc_info=True)
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"API: Generic error getting metadata after {duration:.2f}s: {str(e)}", exc_info=True)
        raise

# --- Flask Endpoints ---

@app.route('/auth/callback', methods=['GET'])
def oauth2callback_endpoint():
    endpoint_name = "/auth/callback"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    authorization_code = request.args.get('code')
    if authorization_code:
        try:
            token_data = exchange_code_for_tokens(authorization_code)
            # IMPORTANT: In a real app, securely store token_data.refresh_token
            # associated with the user. For this example, we just return it.
            logger.info(f"ENDPOINT {endpoint_name}: Authorization successful, tokens obtained.")
            return jsonify({
                "message": "Authorization successful. IMPORTANT: Securely store the refresh_token.",
                "tokens": token_data # Contains access_token, refresh_token, expires_in, etc.
            })
        except Exception as e:
            logger.error(f"ENDPOINT {endpoint_name}: Error during token exchange: {str(e)}", exc_info=True)
            return jsonify({"error": f"Failed to exchange authorization code for tokens: {str(e)}"}), 500
    else:
        logger.warning(f"ENDPOINT {endpoint_name}: Authorization code missing in request.")
        return jsonify({"error": "Authorization code missing"}), 400

# Renamed for clarity and better practice
@app.route('/sheets/<spreadsheet_id>/cell/update', methods=['POST'])
def update_cell_endpoint(spreadsheet_id):
    endpoint_name = f"/sheets/{spreadsheet_id}/cell/update"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.json
        logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")
        if not all(k in data for k in ('cell_range', 'new_value', 'refresh_token')):
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields.")
            return jsonify({"success": False, "error": "Missing 'cell_range', 'new_value', or 'refresh_token'"}), 400

        cell_range = data['cell_range']
        new_value = data['new_value']
        refresh_token = data['refresh_token']
        value_input_option = data.get('value_input_option', "USER_ENTERED") # Optional

        access_token = get_access_token(refresh_token)
        service = get_sheets_service(access_token)
        result = api_update_cell(service, spreadsheet_id, cell_range, new_value, value_input_option)
        
        logger.info(f"ENDPOINT {endpoint_name}: Cell update successful.")
        return jsonify({"success": True, "message": "Cell updated successfully.", "details": result})
    except HttpError as e:
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/sheets/<spreadsheet_id>/rows/append', methods=['POST'])
def append_rows_endpoint(spreadsheet_id):
    endpoint_name = f"/sheets/{spreadsheet_id}/rows/append"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.json
        logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")
        if not all(k in data for k in ('range_name', 'values_data', 'refresh_token')):
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields.")
            return jsonify({"success": False, "error": "Missing 'range_name', 'values_data', or 'refresh_token'"}), 400

        range_name = data['range_name'] # e.g., "Sheet1" or "Sheet1!A1"
        values_data = data['values_data'] # Should be a list of lists, e.g., [["ValA1", "ValB1"], ["ValA2", "ValB2"]]
        refresh_token = data['refresh_token']
        value_input_option = data.get('value_input_option', "USER_ENTERED")

        if not isinstance(values_data, list) or not all(isinstance(row, list) for row in values_data):
            logger.warning(f"ENDPOINT {endpoint_name}: 'values_data' is not a list of lists.")
            return jsonify({"success": False, "error": "'values_data' must be a list of lists (rows of cells)."}), 400

        access_token = get_access_token(refresh_token)
        service = get_sheets_service(access_token)
        result = api_append_rows(service, spreadsheet_id, range_name, values_data, value_input_option)
        
        logger.info(f"ENDPOINT {endpoint_name}: Row append successful.")
        return jsonify({"success": True, "message": "Rows appended successfully.", "details": result.get("updates")})
    except HttpError as e:
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/sheets/<spreadsheet_id>/rows/delete', methods=['POST']) # Using POST for batchUpdate
def delete_rows_endpoint(spreadsheet_id):
    endpoint_name = f"/sheets/{spreadsheet_id}/rows/delete"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.json
        logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")
        if not all(k in data for k in ('sheet_id', 'start_row_index', 'end_row_index', 'refresh_token')):
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields.")
            return jsonify({"success": False, "error": "Missing 'sheet_id', 'start_row_index', 'end_row_index', or 'refresh_token'"}), 400

        sheet_id = int(data['sheet_id']) # Numeric ID of the sheet/tab
        start_row_index = int(data['start_row_index']) # 0-based, inclusive
        end_row_index = int(data['end_row_index'])     # 0-based, exclusive
        refresh_token = data['refresh_token']

        if start_row_index < 0 or end_row_index <= start_row_index:
            logger.warning(f"ENDPOINT {endpoint_name}: Invalid row indices.")
            return jsonify({"success": False, "error": "Invalid 'start_row_index' or 'end_row_index'. Ensure start < end and both >= 0."}), 400

        access_token = get_access_token(refresh_token)
        service = get_sheets_service(access_token)
        result = api_delete_rows(service, spreadsheet_id, sheet_id, start_row_index, end_row_index)
        
        logger.info(f"ENDPOINT {endpoint_name}: Row deletion request successful.")
        return jsonify({"success": True, "message": "Row deletion request processed.", "details": result})
    except ValueError: # Catches int() conversion errors
        logger.warning(f"ENDPOINT {endpoint_name}: Invalid non-integer input for sheet_id or row indices.", exc_info=True)
        return jsonify({"success": False, "error": "sheet_id, start_row_index, and end_row_index must be integers."}), 400
    except HttpError as e:
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/sheets/<spreadsheet_id>/tabs/create', methods=['POST'])
def create_tab_endpoint(spreadsheet_id):
    endpoint_name = f"/sheets/{spreadsheet_id}/tabs/create"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.json
        logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")
        if not all(k in data for k in ('new_sheet_title', 'refresh_token')):
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields.")
            return jsonify({"success": False, "error": "Missing 'new_sheet_title' or 'refresh_token'"}), 400

        new_sheet_title = data['new_sheet_title']
        refresh_token = data['refresh_token']

        access_token = get_access_token(refresh_token)
        service = get_sheets_service(access_token)
        result = api_create_new_tab(service, spreadsheet_id, new_sheet_title)
        
        new_sheet_props = result.get('replies', [{}])[0].get('addSheet', {}).get('properties', {})
        logger.info(f"ENDPOINT {endpoint_name}: New tab creation successful.")
        return jsonify({
            "success": True,
            "message": "New tab/sheet created successfully.",
            "new_sheet_properties": new_sheet_props
        })
    except HttpError as e:
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/sheets/<spreadsheet_id>/values/clear', methods=['POST'])
def clear_values_endpoint(spreadsheet_id):
    endpoint_name = f"/sheets/{spreadsheet_id}/values/clear"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.json
        logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")
        if not all(k in data for k in ('range_name', 'refresh_token')):
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields.")
            return jsonify({"success": False, "error": "Missing 'range_name' or 'refresh_token'"}), 400

        range_name = data['range_name']
        refresh_token = data['refresh_token']

        access_token = get_access_token(refresh_token)
        service = get_sheets_service(access_token)
        result = api_clear_values(service, spreadsheet_id, range_name)
        
        logger.info(f"ENDPOINT {endpoint_name}: Values clear successful.")
        return jsonify({"success": True, "message": "Values cleared successfully.", "details": result})
    except HttpError as e:
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/sheets/<spreadsheet_id>/metadata', methods=['GET'])
def get_metadata_endpoint(spreadsheet_id):
    endpoint_name = f"/sheets/{spreadsheet_id}/metadata"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        # For GET requests, refresh_token is often passed as a query parameter or header
        # For consistency with POST, let's expect it as a query param for this example
        refresh_token = request.args.get('refresh_token')
        if not refresh_token:
            logger.warning(f"ENDPOINT {endpoint_name}: Missing 'refresh_token' query parameter.")
            return jsonify({"success": False, "error": "Missing 'refresh_token' query parameter"}), 400

        access_token = get_access_token(refresh_token)
        service = get_sheets_service(access_token)
        metadata = api_get_spreadsheet_metadata(service, spreadsheet_id)
        
        logger.info(f"ENDPOINT {endpoint_name}: Metadata retrieval successful.")
        return jsonify({"success": True, "metadata": metadata})
    except HttpError as e:
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500


# Run Flask
if __name__ == "__main__":
    if not CLIENT_SECRET:
        logger.critical("CRITICAL STARTUP ERROR: GOOGLE_CLIENT_SECRET environment variable is not set.")
        # Also print to console for immediate visibility if logs aren't checked
        print("CRITICAL ERROR: GOOGLE_CLIENT_SECRET environment variable is not set. The application will likely fail on token operations.")
        print("Please set this environment variable before running.")
    else:
        logger.info(f"GOOGLE_CLIENT_SECRET is loaded (length: {len(CLIENT_SECRET)}).")

    logger.info("Starting Flask application...")
    # For production, use a proper WSGI server like Gunicorn or uWSGI
    # And set debug=False
    app.run(debug=True, host="0.0.0.0", port=5000)
