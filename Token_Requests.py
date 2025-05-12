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
CLIENT_ID = "26763482887-coiufpukc1l69aaulaiov5o0u3en2del.apps.googleusercontent.com"
CLIENT_SECRET = "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"
TOKEN_URL = "https://oauth2.googleapis.com/token"
REDIRECT_URI = "https://serverless.on-demand.io/apps/googlesheets/auth/callback"
REQUEST_TIMEOUT_SECONDS = 30

# --- OAuth and Token Helper Functions (Main App) ---
def exchange_code_for_tokens(authorization_code):
    logger.info(f"Attempting to exchange authorization code for tokens. Code starts with: {authorization_code[:10]}...")
    start_time = time.time()
    if not CLIENT_SECRET:
        logger.error("CRITICAL: GOOGLE_CLIENT_SECRET environment variable not set for token exchange.")
        raise ValueError("GOOGLE_CLIENT_SECRET environment variable not set.")
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
        if token_data.get("access_token"): #and token_data.get("refresh_token"):
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
        "client_id": CLIENT_ID, "client_secret": CLIENT_SECRET,
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
        logger.error(f"HTTPError ({e.response.status_code}) during token refresh after {duration:.2f} seconds: {e.response.text if e.response else str(e)}")
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
    except HttpError as e: duration = time.time() - start_time; error_content = e.content.decode('utf-8') if e.content else str(e); logger.error(f"API: HttpError updating cell after {duration:.2f}s: {error_content}", exc_info=True); raise
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
    except HttpError as e: duration = time.time() - start_time; error_content = e.content.decode('utf-8') if e.content else str(e); logger.error(f"API: HttpError appending rows after {duration:.2f}s: {error_content}", exc_info=True); raise
    except Exception as e: duration = time.time() - start_time; logger.error(f"API: Generic error appending rows after {duration:.2f}s: {str(e)}", exc_info=True); raise

def api_delete_rows(service, spreadsheet_id, sheet_id, start_row_index, end_row_index):
    logger.info(f"API: Deleting rows from sheet '{spreadsheet_id}', sheetId {sheet_id}, from index {start_row_index} to {end_row_index-1}.")
    start_time = time.time()
    try:
        requests_body = [{"deleteDimension": {"range": {"sheetId": sheet_id, "dimension": "ROWS", "startIndex": start_row_index, "endIndex": end_row_index}}}]
        body = {"requests": requests_body}
        result = service.spreadsheets().batchUpdate(spreadsheetId=spreadsheet_id, body=body).execute()
        duration = time.time() - start_time; logger.info(f"API: Row deletion successful in {duration:.2f}s. Result: {result}"); return result
    except HttpError as e: duration = time.time() - start_time; error_content = e.content.decode('utf-8') if e.content else str(e); logger.error(f"API: HttpError deleting rows after {duration:.2f}s: {error_content}", exc_info=True); raise
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
    except HttpError as e: duration = time.time() - start_time; error_content = e.content.decode('utf-8') if e.content else str(e); logger.error(f"API: HttpError creating new tab after {duration:.2f}s: {error_content}", exc_info=True); raise
    except Exception as e: duration = time.time() - start_time; logger.error(f"API: Generic error creating new tab after {duration:.2f}s: {str(e)}", exc_info=True); raise

def api_clear_values(service, spreadsheet_id, range_name):
    logger.info(f"API: Clearing values from sheet '{spreadsheet_id}', range '{range_name}'.")
    start_time = time.time()
    try:
        result = service.spreadsheets().values().clear(spreadsheetId=spreadsheet_id, range=range_name, body={}).execute()
        duration = time.time() - start_time; logger.info(f"API: Values clear successful in {duration:.2f}s. Cleared range: {result.get('clearedRange')}"); return result
    except HttpError as e: duration = time.time() - start_time; error_content = e.content.decode('utf-8') if e.content else str(e); logger.error(f"API: HttpError clearing values after {duration:.2f}s: {error_content}", exc_info=True); raise
    except Exception as e: duration = time.time() - start_time; logger.error(f"API: Generic error clearing values after {duration:.2f}s: {str(e)}", exc_info=True); raise

def api_get_spreadsheet_metadata(service, spreadsheet_id):
    logger.info(f"API: Getting metadata for spreadsheet '{spreadsheet_id}'.")
    start_time = time.time()
    try:
        result = service.spreadsheets().get(spreadsheetId=spreadsheet_id, fields="properties,sheets.properties").execute()
        duration = time.time() - start_time; logger.info(f"API: Metadata retrieval successful in {duration:.2f}s."); return result
    except HttpError as e: duration = time.time() - start_time; error_content = e.content.decode('utf-8') if e.content else str(e); logger.error(f"API: HttpError getting metadata after {duration:.2f}s: {error_content}", exc_info=True); raise
    except Exception as e: duration = time.time() - start_time; logger.error(f"API: Generic error getting metadata after {duration:.2f}s: {str(e)}", exc_info=True); raise

# --- NEW: Helper function for the /token endpoint (uses specific hardcoded values) ---
def get_specific_user_access_token():
    logger.info("Attempting to get access token for a specific pre-configured user.")
    specific_client_id = "26763482887-q9lcln5nmb0setr60gkohdjrt2msl6o5.apps.googleusercontent.com"
    # --- THIS IS THE UPDATED REFRESH TOKEN ---
    specific_refresh_token = "1//09qu30gV5_1hZCgYIARAAGAkSNwF-L9IrEOR20gZnhzmvcFcU46oN89TXt-Sf7ET2SAUwx7d9wo0E2E2ISkXw4CxCDDNxouGAVo4"
    # --- END OF UPDATE ---

    if not CLIENT_SECRET:
        logger.error("CRITICAL: GOOGLE_CLIENT_SECRET environment variable not set for token refresh (specific user).")
        raise ValueError("GOOGLE_CLIENT_SECRET environment variable not set.")
    payload = {
        "client_id": specific_client_id, "client_secret": CLIENT_SECRET,
        "refresh_token": specific_refresh_token, "grant_type": "refresh_token"
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
        logger.error(f"HTTPError ({e.response.status_code}) during specific user token refresh after {duration:.2f} seconds: {e.response.text if e.response else str(e)}")
        if "invalid_grant" in (e.response.text if e.response else ""):
            logger.warning("Specific user token refresh failed with 'invalid_grant'. Refresh token may be expired or revoked.")
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Generic exception during specific user token refresh after {duration:.2f} seconds: {str(e)}", exc_info=True)
        raise

# --- Flask Endpoints (Main App) ---
@app.route('/auth/callback', methods=['GET'])
def oauth2callback_endpoint():
    endpoint_name = "/auth/callback"; logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    authorization_code = request.args.get('code')
    if authorization_code:
        try:
            token_data = exchange_code_for_tokens(authorization_code)
            logger.info(f"ENDPOINT {endpoint_name}: Authorization successful, tokens obtained.")
            return jsonify({"message": "Authorization successful. IMPORTANT: Securely store the refresh_token.", "tokens": token_data})
        except Exception as e:
            logger.error(f"ENDPOINT {endpoint_name}: Error during token exchange: {str(e)}", exc_info=True)
            return jsonify({"error": f"Failed to exchange authorization code for tokens: {str(e)}"}), 500
    else:
        logger.warning(f"ENDPOINT {endpoint_name}: Authorization code missing in request.")
        return jsonify({"error": "Authorization code missing"}), 400

@app.route('/sheets/<spreadsheet_id>/cell/update', methods=['POST'])
def update_cell_endpoint(spreadsheet_id):
    endpoint_name = f"/sheets/{spreadsheet_id}/cell/update"; logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.json; logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")
        if not all(k in data for k in ('cell_range', 'new_value', 'refresh_token')):
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields.")
            return jsonify({"success": False, "error": "Missing 'cell_range', 'new_value', or 'refresh_token'"}), 400
        cell_range = data['cell_range']; new_value = data['new_value']; refresh_token = data['refresh_token']
        value_input_option = data.get('value_input_option', "USER_ENTERED")
        access_token = get_access_token(refresh_token); service = get_sheets_service(access_token)
        result = api_update_cell(service, spreadsheet_id, cell_range, new_value, value_input_option)
        logger.info(f"ENDPOINT {endpoint_name}: Cell update successful.")
        return jsonify({"success": True, "message": "Cell updated successfully.", "details": result})
    except HttpError as e: error_content = e.content.decode('utf-8') if e.content else str(e); logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True); return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e: logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True); return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/sheets/<spreadsheet_id>/rows/append', methods=['POST'])
def append_rows_endpoint(spreadsheet_id):
    endpoint_name = f"/sheets/{spreadsheet_id}/rows/append"; logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.json; logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")
        if not all(k in data for k in ('range_name', 'values_data', 'refresh_token')):
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields.")
            return jsonify({"success": False, "error": "Missing 'range_name', 'values_data', or 'refresh_token'"}), 400
        range_name = data['range_name']; values_data = data['values_data']; refresh_token = data['refresh_token']
        value_input_option = data.get('value_input_option', "USER_ENTERED")
        if not isinstance(values_data, list) or not all(isinstance(row, list) for row in values_data):
            logger.warning(f"ENDPOINT {endpoint_name}: 'values_data' is not a list of lists.")
            return jsonify({"success": False, "error": "'values_data' must be a list of lists (rows of cells)."}), 400
        access_token = get_access_token(refresh_token); service = get_sheets_service(access_token)
        result = api_append_rows(service, spreadsheet_id, range_name, values_data, value_input_option)
        logger.info(f"ENDPOINT {endpoint_name}: Row append successful.")
        return jsonify({"success": True, "message": "Rows appended successfully.", "details": result.get("updates")})
    except HttpError as e: error_content = e.content.decode('utf-8') if e.content else str(e); logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True); return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e: logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True); return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/sheets/<spreadsheet_id>/rows/delete', methods=['POST'])
def delete_rows_endpoint(spreadsheet_id):
    endpoint_name = f"/sheets/{spreadsheet_id}/rows/delete"; logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    
    try:
        data = request.json; logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")
        if not all(k in data for k in ('sheet_id', 'start_row_index', 'end_row_index', 'refresh_token')):
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields.")
            return jsonify({"success": False, "error": "Missing 'sheet_id', 'start_row_index', 'end_row_index', or 'refresh_token'"}), 400
        sheet_id = int(data['sheet_id']); start_row_index = int(data['start_row_index']); end_row_index = int(data['end_row_index']); refresh_token = data['refresh_token']
       
        if start_row_index < 0 or end_row_index <= start_row_index:
            logger.warning(f"ENDPOINT {endpoint_name}: Invalid row indices.")
            return jsonify({"success": False, "error": "Invalid 'start_row_index' or 'end_row_index'. Ensure start < end and both >= 0."}), 400
        access_token = get_access_token(refresh_token); service = get_sheets_service(access_token)
        result = api_delete_rows(service, spreadsheet_id, sheet_id, start_row_index, end_row_index)
        logger.info(f"ENDPOINT {endpoint_name}: Row deletion request successful.")
        return jsonify({"success": True, "message": "Row deletion request processed.", "details": result})
    except ValueError: logger.warning(f"ENDPOINT {endpoint_name}: Invalid non-integer input for sheet_id or row indices.", exc_info=True); return jsonify({"success": False, "error": "sheet_id, start_row_index, and end_row_index must be integers."}), 400
    except HttpError as e: error_content = e.content.decode('utf-8') if e.content else str(e); logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True); return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e: logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True); return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/sheets/<spreadsheet_id>/tabs/create', methods=['POST'])
def create_tab_endpoint(spreadsheet_id):
    endpoint_name = f"/sheets/{spreadsheet_id}/tabs/create"; logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.json; logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")
        if not all(k in data for k in ('new_sheet_title', 'refresh_token')):
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields.")
            return jsonify({"success": False, "error": "Missing 'new_sheet_title' or 'refresh_token'"}), 400
        new_sheet_title = data['new_sheet_title']; refresh_token = data['refresh_token']
        access_token = get_access_token(refresh_token); service = get_sheets_service(access_token)
        result = api_create_new_tab(service, spreadsheet_id, new_sheet_title)
        new_sheet_props = result.get('replies', [{}])[0].get('addSheet', {}).get('properties', {})
        logger.info(f"ENDPOINT {endpoint_name}: New tab creation successful.")
        return jsonify({"success": True, "message": "New tab/sheet created successfully.", "new_sheet_properties": new_sheet_props})
    except HttpError as e: error_content = e.content.decode('utf-8') if e.content else str(e); logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True); return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e: logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True); return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/sheets/<spreadsheet_id>/values/clear', methods=['POST'])
def clear_values_endpoint(spreadsheet_id):
    endpoint_name = f"/sheets/{spreadsheet_id}/values/clear"; logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.json; logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")
        if not all(k in data for k in ('range_name', 'refresh_token')):
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields.")
            return jsonify({"success": False, "error": "Missing 'range_name' or 'refresh_token'"}), 400
        range_name = data['range_name']; refresh_token = data['refresh_token']
        access_token = get_access_token(refresh_token); service = get_sheets_service(access_token)
        result = api_clear_values(service, spreadsheet_id, range_name)
        logger.info(f"ENDPOINT {endpoint_name}: Values clear successful.")
        return jsonify({"success": True, "message": "Values cleared successfully.", "details": result})
    except HttpError as e: error_content = e.content.decode('utf-8') if e.content else str(e); logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True); return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e: logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True); return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

@app.route('/sheets/<spreadsheet_id>/metadata', methods=['POST'])
def get_metadata_endpoint(spreadsheet_id):
    data = request.json
    refresh_token = data['refresh_token']
    endpoint_name = f"/sheets/{spreadsheet_id}/metadata"; logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        if not refresh_token:
            logger.warning(f"ENDPOINT {endpoint_name}: Missing 'refresh_token' query parameter.")
            return jsonify({"success": False, "error": "Missing 'refresh_token' query parameter"}), 400
        access_token = get_access_token(refresh_token); service = get_sheets_service(access_token)
        metadata = api_get_spreadsheet_metadata(service, spreadsheet_id)
        logger.info(f"ENDPOINT {endpoint_name}: Metadata retrieval successful.")
        return jsonify({"success": True, "metadata": metadata})
    except HttpError as e: error_content = e.content.decode('utf-8') if e.content else str(e); logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True); return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e: logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True); return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

# --- NEW: Endpoint to get an access token for a specific hardcoded refresh token ---
@app.route('/token', methods=['GET'])
def specific_user_token_endpoint():
    endpoint_name = "/token"
    logger.info(f"ENDPOINT {endpoint_name}: Request received to get specific user access token.")
    try:
        access_token = get_specific_user_access_token()
        logger.info(f"ENDPOINT {endpoint_name}: Successfully obtained access token for specific user.")
        return jsonify({"success": True, "access_token": access_token})
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Failed to get specific user access token: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"Failed to obtain access token: {str(e)}"}), 500

#NEW CODE TEST -----------------------------------------------------------------------------------------------------------------------------
from flask import Flask, request, jsonify
from googleapiclient.errors import HttpError
import logging

# Assume 'app' and 'logger' are initialized elsewhere in your application
# For example:
# app = Flask(__name__)
# logger = logging.getLogger(__name__)
# logging.basicConfig(level=logging.INFO) # Basic config

# --- Helper function for Batch Updates ---
def api_batch_update(service, spreadsheet_id, batch_update_requests_payload):
    """
    Executes a batchUpdate request to the Google Sheets API.
    Args:
        service: Authorized Google Sheets service instance.
        spreadsheet_id: The ID of the spreadsheet.
        batch_update_requests_payload: The dict containing the 'requests' list for batchUpdate.
                                      Example: {"requests": [{...one_request...}, {...another_request...}]}
    Returns:
        The result from the API call.
    """
    try:
        result = service.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id,
            body=batch_update_requests_payload
        ).execute()
        logger.info(f"Batch update successful for spreadsheet {spreadsheet_id}.")
        return result
    except HttpError as error:
        # The error object already contains detailed information.
        # Re-raising allows the endpoint's specific error handler to catch it.
        logger.error(f"Google API HttpError in api_batch_update for spreadsheet {spreadsheet_id}: {error.resp.status} - {error._get_reason()}", exc_info=True)
        raise error


# --- New Flask Endpoints for Batch Operations ---

@app.route('/sheets/<spreadsheet_id>/borders/update', methods=['POST'])
def update_cell_borders_endpoint(spreadsheet_id):
    endpoint_name = f"/sheets/{spreadsheet_id}/borders/update"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.json
        logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")

        required_fields = ['refresh_token', 'range_details']
        if not data or not all(k in data for k in required_fields):
            missing = [k for k in required_fields if not data or k not in data]
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields. Need: {required_fields}, Missing: {missing}")
            return jsonify({"success": False, "error": f"Missing one or more required fields: {', '.join(missing)}"}), 400

        refresh_token = data['refresh_token']
        range_details = data['range_details']

        required_range_fields = ['sheetId', 'startRowIndex', 'endRowIndex', 'startColumnIndex', 'endColumnIndex']
        if not isinstance(range_details, dict) or not all(k in range_details for k in required_range_fields):
            logger.warning(f"ENDPOINT {endpoint_name}: Invalid or missing fields in range_details. Need: {required_range_fields}")
            return jsonify({"success": False, "error": f"Invalid or missing fields in range_details. Each must be a dict with: {', '.join(required_range_fields)}"}), 400

        update_borders_payload = {"range": range_details}
        border_keys_map = {
            'top_border_details': 'top',
            'bottom_border_details': 'bottom',
            'left_border_details': 'left',
            'right_border_details': 'right',
            'inner_horizontal_details': 'innerHorizontal',
            'inner_vertical_details': 'innerVertical'
        }
        
        found_border_spec = False
        for client_key, api_key in border_keys_map.items():
            if client_key in data:
                # Basic validation for border detail (must be an object)
                if not isinstance(data[client_key], dict):
                    logger.warning(f"ENDPOINT {endpoint_name}: Border detail '{client_key}' must be an object.")
                    return jsonify({"success": False, "error": f"Border detail '{client_key}' must be an object."}), 400
                update_borders_payload[api_key] = data[client_key]
                found_border_spec = True
        
        if not found_border_spec:
            logger.warning(f"ENDPOINT {endpoint_name}: No border details provided (e.g., 'top_border_details').")
            return jsonify({"success": False, "error": "At least one border specification (e.g., 'top_border_details', 'inner_horizontal_details') must be provided."}), 400

        batch_update_body = {
            "requests": [{"updateBorders": update_borders_payload}]
        }

        access_token = get_access_token(refresh_token) # Assumed to be defined
        service = get_sheets_service(access_token)    # Assumed to be defined

        result = api_batch_update(service, spreadsheet_id, batch_update_body)
        logger.info(f"ENDPOINT {endpoint_name}: Cell borders update successful.")
        return jsonify({"success": True, "message": "Cell borders updated successfully.", "details": result})

    except HttpError as e:
        error_content = e.content.decode('utf-8') if hasattr(e, 'content') and e.content else str(e)
        status_code = e.resp.status if hasattr(e, 'resp') else 500
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), status_code
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500


@app.route('/sheets/<spreadsheet_id>/header/format', methods=['POST'])
def format_header_row_endpoint(spreadsheet_id):
    endpoint_name = f"/sheets/{spreadsheet_id}/header/format"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.json
        logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")

        required_fields = ['refresh_token', 'sheet_id', 'header_row_index', 'format_options']
        if not data or not all(k in data for k in required_fields):
            missing = [k for k in required_fields if not data or k not in data]
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields. Need: {required_fields}, Missing: {missing}")
            return jsonify({"success": False, "error": f"Missing one or more required fields: {', '.join(missing)}"}), 400

        refresh_token = data['refresh_token']
        sheet_id = data['sheet_id']
        header_row_index = data['header_row_index']
        format_options = data['format_options']
        freeze_header = data.get('freeze_header', True)

        if not isinstance(format_options, dict) or not format_options:
            logger.warning(f"ENDPOINT {endpoint_name}: 'format_options' must be a non-empty dictionary.")
            return jsonify({"success": False, "error": "'format_options' must be a non-empty dictionary."}), 400
        if not isinstance(sheet_id, int) or not isinstance(header_row_index, int) or header_row_index < 0:
            logger.warning(f"ENDPOINT {endpoint_name}: 'sheet_id' and 'header_row_index' must be valid integers (index >=0).")
            return jsonify({"success": False, "error": "'sheet_id' must be an integer and 'header_row_index' a non-negative integer."}), 400


        # Dynamically build the fields string for userEnteredFormat
        field_paths = []
        if 'backgroundColor' in format_options: field_paths.append('backgroundColor')
        if 'horizontalAlignment' in format_options: field_paths.append('horizontalAlignment')
        if 'textFormat' in format_options: field_paths.append('textFormat') # Covers all sub-fields like bold, fontSize, etc.
        # Add other common direct children of userEnteredFormat if needed (e.g., verticalAlignment, wrapStrategy, numberFormat)
        
        if not field_paths:
            logger.warning(f"ENDPOINT {endpoint_name}: 'format_options' is empty or contains no recognizable top-level formatting keys for 'fields' string.")
            return jsonify({"success": False, "error": "'format_options' must contain recognizable formatting keys (e.g., backgroundColor, textFormat, horizontalAlignment)."}), 400
        
        fields_string = f"userEnteredFormat({','.join(field_paths)})"

        api_requests = []
        repeat_cell_request = {
            "repeatCell": {
                "range": {
                    "sheetId": sheet_id,
                    "startRowIndex": header_row_index,
                    "endRowIndex": header_row_index + 1
                },
                "cell": {"userEnteredFormat": format_options},
                "fields": fields_string
            }
        }
        api_requests.append(repeat_cell_request)

        if freeze_header:
            update_sheet_properties_request = {
                "updateSheetProperties": {
                    "properties": {
                        "sheetId": sheet_id,
                        "gridProperties": {"frozenRowCount": header_row_index + 1}
                    },
                    "fields": "gridProperties.frozenRowCount"
                }
            }
            api_requests.append(update_sheet_properties_request)

        batch_update_body = {"requests": api_requests}
        access_token = get_access_token(refresh_token)
        service = get_sheets_service(access_token)

        result = api_batch_update(service, spreadsheet_id, batch_update_body)
        logger.info(f"ENDPOINT {endpoint_name}: Header row formatting successful.")
        return jsonify({"success": True, "message": "Header row formatted successfully.", "details": result})

    except HttpError as e:
        error_content = e.content.decode('utf-8') if hasattr(e, 'content') and e.content else str(e)
        status_code = e.resp.status if hasattr(e, 'resp') else 500
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), status_code
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500


@app.route('/sheets/<spreadsheet_id>/cells/merge', methods=['POST'])
def merge_cells_endpoint(spreadsheet_id):
    endpoint_name = f"/sheets/{spreadsheet_id}/cells/merge"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.json
        logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")

        required_fields = ['refresh_token', 'merge_operations']
        if not data or not all(k in data for k in required_fields):
            missing = [k for k in required_fields if not data or k not in data]
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields. Need: {required_fields}, Missing: {missing}")
            return jsonify({"success": False, "error": f"Missing one or more required fields: {', '.join(missing)}"}), 400

        refresh_token = data['refresh_token']
        merge_operations = data['merge_operations']

        if not isinstance(merge_operations, list) or not merge_operations:
            logger.warning(f"ENDPOINT {endpoint_name}: 'merge_operations' must be a non-empty list.")
            return jsonify({"success": False, "error": "'merge_operations' must be a non-empty list."}), 400

        api_requests = []
        required_range_fields = ['sheetId', 'startRowIndex', 'endRowIndex', 'startColumnIndex', 'endColumnIndex']
        valid_merge_types = ["MERGE_ALL", "MERGE_COLUMNS", "MERGE_ROWS"]

        for i, op in enumerate(merge_operations):
            if not isinstance(op, dict) or not all(k in op for k in ['range_details', 'merge_type']):
                logger.warning(f"ENDPOINT {endpoint_name}: Invalid item at index {i} in 'merge_operations'. Missing 'range_details' or 'merge_type'.")
                return jsonify({"success": False, "error": f"Invalid item at index {i} in 'merge_operations'. Each must have 'range_details' and 'merge_type'."}), 400
            
            range_details = op['range_details']
            merge_type = op['merge_type']

            if not isinstance(range_details, dict) or not all(k in range_details for k in required_range_fields):
                logger.warning(f"ENDPOINT {endpoint_name}: Invalid 'range_details' at index {i}. Need: {required_range_fields}")
                return jsonify({"success": False, "error": f"Invalid 'range_details' at index {i}. Must be dict with: {', '.join(required_range_fields)}"}), 400
            if merge_type not in valid_merge_types:
                logger.warning(f"ENDPOINT {endpoint_name}: Invalid 'merge_type' at index {i}: {merge_type}. Must be one of {valid_merge_types}")
                return jsonify({"success": False, "error": f"Invalid 'merge_type' at index {i}: {merge_type}. Must be one of {valid_merge_types}"}), 400

            api_requests.append({"mergeCells": {"range": range_details, "mergeType": merge_type}})

        batch_update_body = {"requests": api_requests}
        access_token = get_access_token(refresh_token)
        service = get_sheets_service(access_token)

        result = api_batch_update(service, spreadsheet_id, batch_update_body)
        logger.info(f"ENDPOINT {endpoint_name}: Cells merged successfully.")
        return jsonify({"success": True, "message": "Cells merged successfully.", "details": result})

    except HttpError as e:
        error_content = e.content.decode('utf-8') if hasattr(e, 'content') and e.content else str(e)
        status_code = e.resp.status if hasattr(e, 'resp') else 500
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), status_code
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500


@app.route('/sheets/<spreadsheet_id>/cells/format/custom', methods=['POST'])
def set_custom_cell_format_endpoint(spreadsheet_id):
    endpoint_name = f"/sheets/{spreadsheet_id}/cells/format/custom"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.json
        logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")

        required_fields = ['refresh_token', 'format_operations']
        if not data or not all(k in data for k in required_fields):
            missing = [k for k in required_fields if not data or k not in data]
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields. Need: {required_fields}, Missing: {missing}")
            return jsonify({"success": False, "error": f"Missing one or more required fields: {', '.join(missing)}"}), 400

        refresh_token = data['refresh_token']
        format_operations = data['format_operations']

        if not isinstance(format_operations, list) or not format_operations:
            logger.warning(f"ENDPOINT {endpoint_name}: 'format_operations' must be a non-empty list.")
            return jsonify({"success": False, "error": "'format_operations' must be a non-empty list."}), 400

        api_requests = []
        required_range_fields = ['sheetId', 'startRowIndex', 'endRowIndex', 'startColumnIndex', 'endColumnIndex']
        # NumberFormatType from API docs: TEXT, NUMBER, PERCENT, CURRENCY, DATE, TIME, DATE_TIME, SCIENTIFIC
        valid_format_types = ["TEXT", "NUMBER", "PERCENT", "CURRENCY", "DATE", "TIME", "DATE_TIME", "SCIENTIFIC"]


        for i, op in enumerate(format_operations):
            if not isinstance(op, dict) or not all(k in op for k in ['range_details', 'format_type', 'pattern']):
                logger.warning(f"ENDPOINT {endpoint_name}: Invalid item at index {i} in 'format_operations'. Missing 'range_details', 'format_type', or 'pattern'.")
                return jsonify({"success": False, "error": f"Invalid item at index {i} in 'format_operations'. Each must have 'range_details', 'format_type', and 'pattern'."}), 400

            range_details = op['range_details']
            format_type = op['format_type'].upper() # Normalize to uppercase
            pattern = op['pattern']

            if not isinstance(range_details, dict) or not all(k in range_details for k in required_range_fields):
                logger.warning(f"ENDPOINT {endpoint_name}: Invalid 'range_details' at index {i}. Need: {required_range_fields}")
                return jsonify({"success": False, "error": f"Invalid 'range_details' at index {i}. Must be dict with: {', '.join(required_range_fields)}"}), 400
            if format_type not in valid_format_types:
                 logger.warning(f"ENDPOINT {endpoint_name}: Invalid 'format_type' at index {i}: {op['format_type']}. Must be one of {valid_format_types}")
                 return jsonify({"success": False, "error": f"Invalid 'format_type' at index {i}: {op['format_type']}. Must be one of {valid_format_types}"}), 400


            api_requests.append({
                "repeatCell": {
                    "range": range_details,
                    "cell": {
                        "userEnteredFormat": {
                            "numberFormat": {
                                "type": format_type,
                                "pattern": pattern
                            }
                        }
                    },
                    "fields": "userEnteredFormat.numberFormat"
                }
            })

        batch_update_body = {"requests": api_requests}
        access_token = get_access_token(refresh_token)
        service = get_sheets_service(access_token)

        result = api_batch_update(service, spreadsheet_id, batch_update_body)
        logger.info(f"ENDPOINT {endpoint_name}: Custom cell formats set successfully.")
        return jsonify({"success": True, "message": "Custom cell formats set successfully.", "details": result})

    except HttpError as e:
        error_content = e.content.decode('utf-8') if hasattr(e, 'content') and e.content else str(e)
        status_code = e.resp.status if hasattr(e, 'resp') else 500
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), status_code
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"An unexpected error occurred: {str(e)}"}), 500

# Remember to define or import:
# - app (Flask instance)
# - logger (logging instance)
# - get_access_token(refresh_token)
# - get_sheets_service(access_token)
# - exchange_code_for_tokens(authorization_code) (for the /auth/callback endpoint if you include it)

#------------------------------------------------------------------------------------------------------------------------------NEW CODE TEST






# Run Flask
if __name__ == "__main__":
    if not CLIENT_SECRET:
        logger.critical("CRITICAL STARTUP ERROR: GOOGLE_CLIENT_SECRET environment variable is not set.")
        print("CRITICAL ERROR: GOOGLE_CLIENT_SECRET environment variable is not set. The application will likely fail on token operations.")
        print("Please set this environment variable before running.")
    else:
        logger.info(f"GOOGLE_CLIENT_SECRET is loaded (length: {len(CLIENT_SECRET)}).")
    logger.info("Starting Flask application...")
    app.run(debug=True, host="0.0.0.0", port=5000)
