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
    level=logging.INFO, # Use logging.DEBUG for more verbose output
    format='%(asctime)s - %(levelname)s - %(name)s - %(module)s:%(lineno)d - %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

app = Flask(__name__)

# --- Configuration ---
CLIENT_ID = "26763482887-q9lcln5nmb0setr60gkohdjrt2msl6o5.apps.googleusercontent.com"
REFRESH_TOKEN = "1//09zxz8WxEV7hpCgYIARAAGAkSNwF-L9IrfoSJ7UYywPUkdJEdW-Jj_bMFoA7HNh109drcwUm0RgaAbxbP-o0Ppnf8v6E_Jmndbjc"
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
TOKEN_URL = "https://oauth2.googleapis.com/token"

REQUEST_TIMEOUT_SECONDS = 30 # Timeout for external HTTP requests

# --- Helper Functions ---
def get_access_token():
    """Obtains a new access token using the refresh token."""
    logger.info("Attempting to get new access token...")
    start_time = time.time()

    if not CLIENT_SECRET:
        logger.error("CRITICAL: GOOGLE_CLIENT_SECRET environment variable not set.")
        raise ValueError("GOOGLE_CLIENT_SECRET environment variable not set.")

    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token"
    }
    # Avoid logging sensitive parts of payload directly in production if possible
    logger.debug(f"Token request payload (client_secret and refresh_token redacted for log): {{'client_id': '{CLIENT_ID}', 'grant_type': 'refresh_token'}}")

    try:
        response = requests.post(TOKEN_URL, data=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        token_data = response.json()
        access_token = token_data.get("access_token")
        duration = time.time() - start_time
        if access_token:
            logger.info(f"Successfully obtained new access token in {duration:.2f} seconds. Expires in: {token_data.get('expires_in')}s")
            return access_token
        else:
            logger.error(f"Failed to get access token from response after {duration:.2f}s. Response: {token_data}")
            raise ValueError("Access token not found in response from token endpoint.")
    except requests.exceptions.Timeout:
        duration = time.time() - start_time
        logger.error(f"Timeout ({REQUEST_TIMEOUT_SECONDS}s) while requesting new access token after {duration:.2f} seconds.")
        raise
    except requests.exceptions.HTTPError as e:
        duration = time.time() - start_time
        logger.error(f"HTTPError ({e.response.status_code}) when requesting token after {duration:.2f} seconds: {e.response.text if e.response else str(e)}")
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Generic exception while requesting token after {duration:.2f} seconds: {str(e)}", exc_info=True)
        raise

def get_sheets_service(access_token):
    """Builds and returns an authorized Sheets API service instance."""
    logger.info("Building Google Sheets API service...")
    if not access_token:
        logger.error("Cannot build sheets service: access_token is missing.")
        raise ValueError("Access token is required to build sheets service.")
    try:
        creds = OAuthCredentials(token=access_token)
        service = build("sheets", "v4", credentials=creds)
        logger.info("Google Sheets API service built successfully.")
        return service
    except Exception as e:
        logger.error(f"Failed to build Google Sheets API service: {str(e)}", exc_info=True)
        raise

# --- Google Sheets API Wrapper Functions ---

def api_create_spreadsheet(service, title):
    logger.info(f"API: Attempting to create spreadsheet with title: '{title}'")
    start_time = time.time()
    spreadsheet_body = {"properties": {"title": title}}
    try:
        spreadsheet = (
            service.spreadsheets()
            .create(body=spreadsheet_body, fields="spreadsheetId,spreadsheetUrl")
            .execute()
        )
        duration = time.time() - start_time
        logger.info(f"API: Successfully created spreadsheet '{title}' in {duration:.2f} seconds. ID: {spreadsheet.get('spreadsheetId')}")
        return spreadsheet
    except HttpError as e:
        duration = time.time() - start_time
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"API: Google HttpError creating spreadsheet '{title}' after {duration:.2f}s: {error_content}", exc_info=True)
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"API: Generic error creating spreadsheet '{title}' after {duration:.2f}s: {str(e)}", exc_info=True)
        raise

def api_get_values(service, spreadsheet_id, range_name):
    logger.info(f"API: Attempting to get values from spreadsheet '{spreadsheet_id}', range '{range_name}'")
    start_time = time.time()
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )
        duration = time.time() - start_time
        logger.info(f"API: Successfully got values from '{spreadsheet_id}', range '{range_name}' in {duration:.2f} seconds. Rows: {len(result.get('values', []))}")
        return result
    except HttpError as e:
        duration = time.time() - start_time
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"API: Google HttpError getting values from '{spreadsheet_id}', range '{range_name}' after {duration:.2f}s: {error_content}", exc_info=True)
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"API: Generic error getting values from '{spreadsheet_id}', range '{range_name}' after {duration:.2f}s: {str(e)}", exc_info=True)
        raise

def api_append_values(service, spreadsheet_id, range_name, value_input_option, values_data):
    logger.info(f"API: Attempting to append values to spreadsheet '{spreadsheet_id}', range '{range_name}', option '{value_input_option}'")
    logger.debug(f"API: Values to append: {values_data}")
    start_time = time.time()
    body = {"values": values_data}
    try:
        result = (
            service.spreadsheets()
            .values()
            .append(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption=value_input_option,
                body=body,
                insertDataOption="INSERT_ROWS"
            )
            .execute()
        )
        duration = time.time() - start_time
        logger.info(f"API: Successfully appended values to '{spreadsheet_id}' in {duration:.2f} seconds. Cells updated: {result.get('updates', {}).get('updatedCells', 0)}")
        return result
    except HttpError as e:
        duration = time.time() - start_time
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"API: Google HttpError appending values to '{spreadsheet_id}' after {duration:.2f}s: {error_content}", exc_info=True)
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"API: Generic error appending values to '{spreadsheet_id}' after {duration:.2f}s: {str(e)}", exc_info=True)
        raise

def api_update_values(service, spreadsheet_id, range_name, value_input_option, values_data):
    logger.info(f"API: Attempting to update values in spreadsheet '{spreadsheet_id}', range '{range_name}', option '{value_input_option}'")
    logger.debug(f"API: Values to update: {values_data}")
    start_time = time.time()
    body = {"values": values_data}
    try:
        result = (
            service.spreadsheets()
            .values()
            .update(
                spreadsheetId=spreadsheet_id,
                range=range_name,
                valueInputOption=value_input_option,
                body=body,
            )
            .execute()
        )
        duration = time.time() - start_time
        logger.info(f"API: Successfully updated values in '{spreadsheet_id}' in {duration:.2f} seconds. Cells updated: {result.get('updatedCells', 0)}")
        return result
    except HttpError as e:
        duration = time.time() - start_time
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"API: Google HttpError updating values in '{spreadsheet_id}' after {duration:.2f}s: {error_content}", exc_info=True)
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"API: Generic error updating values in '{spreadsheet_id}' after {duration:.2f}s: {str(e)}", exc_info=True)
        raise

def api_delete_rows(service, spreadsheet_id, sheet_id, start_index, end_index):
    logger.info(f"API: Attempting to delete rows from spreadsheet '{spreadsheet_id}', sheetId {sheet_id}, rows {start_index}-{end_index-1}")
    start_time = time.time()
    requests_body = [{
        "deleteDimension": {
            "range": {
                "sheetId": sheet_id,
                "dimension": "ROWS",
                "startIndex": start_index,
                "endIndex": end_index
            }
        }
    }]
    body = {"requests": requests_body}
    try:
        response = (
            service.spreadsheets()
            .batchUpdate(spreadsheetId=spreadsheet_id, body=body)
            .execute()
        )
        duration = time.time() - start_time
        logger.info(f"API: Successfully sent delete rows request for '{spreadsheet_id}', sheet {sheet_id} in {duration:.2f} seconds. Replies: {len(response.get('replies',[]))}")
        return response
    except HttpError as e:
        duration = time.time() - start_time
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"API: Google HttpError deleting rows from '{spreadsheet_id}', sheet {sheet_id} after {duration:.2f}s: {error_content}", exc_info=True)
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"API: Generic error deleting rows from '{spreadsheet_id}', sheet {sheet_id} after {duration:.2f}s: {str(e)}", exc_info=True)
        raise

def api_clear_values(service, spreadsheet_id, range_name):
    logger.info(f"API: Attempting to clear values from spreadsheet '{spreadsheet_id}', range '{range_name}'")
    start_time = time.time()
    try:
        result = service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            body={} # Clear request body is empty
        ).execute()
        duration = time.time() - start_time
        logger.info(f"API: Successfully cleared values from '{spreadsheet_id}', range '{range_name}' in {duration:.2f} seconds. Cleared range: {result.get('clearedRange')}")
        return result
    except HttpError as e:
        duration = time.time() - start_time
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"API: Google HttpError clearing values from '{spreadsheet_id}', range '{range_name}' after {duration:.2f}s: {error_content}", exc_info=True)
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"API: Generic error clearing values from '{spreadsheet_id}', range '{range_name}' after {duration:.2f}s: {str(e)}", exc_info=True)
        raise

def api_get_sheet_metadata(service, spreadsheet_id):
    logger.info(f"API: Attempting to get metadata for spreadsheet '{spreadsheet_id}'")
    start_time = time.time()
    try:
        metadata = service.spreadsheets().get(spreadsheetId=spreadsheet_id).execute()
        duration = time.time() - start_time
        logger.info(f"API: Successfully got metadata for spreadsheet '{spreadsheet_id}' in {duration:.2f} seconds.")
        logger.debug(f"API: Metadata for '{spreadsheet_id}': {metadata}") # Metadata can be large
        return metadata
    except HttpError as e:
        duration = time.time() - start_time
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"API: Google HttpError getting metadata for '{spreadsheet_id}' after {duration:.2f}s: {error_content}", exc_info=True)
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"API: Generic error getting metadata for '{spreadsheet_id}' after {duration:.2f}s: {str(e)}", exc_info=True)
        raise

# --- Flask Endpoints ---

@app.route('/token', methods=['GET'])
def token_endpoint():
    endpoint_name = "/token"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        access_token = get_access_token()
        logger.info(f"ENDPOINT {endpoint_name}: Successfully processed.")
        return jsonify({"success": True, "access_token": access_token})
    except requests.exceptions.HTTPError as e: # More specific for token errors
        logger.error(f"ENDPOINT {endpoint_name}: HTTPError during token retrieval: {str(e.response.text if e.response else e)}", exc_info=True)
        return jsonify({"success": False, "error": "Failed to obtain access token", "details": str(e.response.text if e.response else e)}), 500
    except ValueError as e: # For CLIENT_SECRET not set or token not found
        logger.error(f"ENDPOINT {endpoint_name}: ValueError during token retrieval: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 400 # Or 500 if server misconfiguration
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "An unexpected error occurred while obtaining token."}), 500

@app.route('/spreadsheets/create', methods=['POST'])
def create_spreadsheet_endpoint():
    endpoint_name = "/spreadsheets/create"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.get_json()
        logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")
        if not data or "title" not in data:
            logger.warning(f"ENDPOINT {endpoint_name}: Missing 'title' in request body.")
            return jsonify({"success": False, "error": "Missing 'title' in request body"}), 400

        title = data["title"]
        logger.info(f"ENDPOINT {endpoint_name}: Processing with title: '{title}'")
        access_token = get_access_token()
        service = get_sheets_service(access_token)
        
        spreadsheet_info = api_create_spreadsheet(service, title)
        logger.info(f"ENDPOINT {endpoint_name}: Successfully processed for title '{title}'.")
        return jsonify({
            "success": True,
            "message": f"Spreadsheet created successfully.",
            "spreadsheetId": spreadsheet_info.get("spreadsheetId"),
            "spreadsheetUrl": spreadsheet_info.get("spreadsheetUrl")
        })
    except HttpError as e:
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e: # Catches errors from get_access_token too if not HttpError
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "An unexpected server error occurred."}), 500

@app.route('/spreadsheets/<spreadsheet_id>/values/<path:range_name>', methods=['GET'])
def get_values_endpoint(spreadsheet_id, range_name):
    endpoint_name = f"/spreadsheets/{spreadsheet_id}/values/{range_name}"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        logger.info(f"ENDPOINT {endpoint_name}: Processing for spreadsheet '{spreadsheet_id}', range '{range_name}'")
        access_token = get_access_token()
        service = get_sheets_service(access_token)
        
        result = api_get_values(service, spreadsheet_id, range_name)
        logger.info(f"ENDPOINT {endpoint_name}: Successfully processed.")
        return jsonify({
            "success": True,
            "range": result.get("range"),
            "values": result.get("values", [])
        })
    except HttpError as e:
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "An unexpected server error occurred."}), 500

@app.route('/spreadsheets/<spreadsheet_id>/values/append', methods=['POST'])
def append_values_endpoint(spreadsheet_id):
    endpoint_name = f"/spreadsheets/{spreadsheet_id}/values/append"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.get_json()
        logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")
        if not data or not all(k in data for k in ("range", "valueInputOption", "values")):
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields in request body.")
            return jsonify({"success": False, "error": "Missing 'range', 'valueInputOption', or 'values' in request body"}), 400

        range_name = data["range"]
        value_input_option = data["valueInputOption"]
        values_data = data["values"]
        logger.info(f"ENDPOINT {endpoint_name}: Processing for spreadsheet '{spreadsheet_id}', range '{range_name}'")

        access_token = get_access_token()
        service = get_sheets_service(access_token)
        
        result = api_append_values(service, spreadsheet_id, range_name, value_input_option, values_data)
        logger.info(f"ENDPOINT {endpoint_name}: Successfully processed.")
        return jsonify({
            "success": True,
            "message": f"{result.get('updates', {}).get('updatedCells', 0)} cells appended.",
            "updatedRange": result.get('updates', {}).get('updatedRange')
        })
    except HttpError as e:
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "An unexpected server error occurred."}), 500

@app.route('/spreadsheets/<spreadsheet_id>/values/update', methods=['PUT'])
def update_values_endpoint(spreadsheet_id):
    endpoint_name = f"/spreadsheets/{spreadsheet_id}/values/update"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.get_json()
        logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")
        if not data or not all(k in data for k in ("range", "valueInputOption", "values")):
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields in request body.")
            return jsonify({"success": False, "error": "Missing 'range', 'valueInputOption', or 'values' in request body"}), 400
        
        range_name = data["range"]
        value_input_option = data["valueInputOption"]
        values_data = data["values"]
        logger.info(f"ENDPOINT {endpoint_name}: Processing for spreadsheet '{spreadsheet_id}', range '{range_name}'")

        access_token = get_access_token()
        service = get_sheets_service(access_token)
        
        result = api_update_values(service, spreadsheet_id, range_name, value_input_option, values_data)
        logger.info(f"ENDPOINT {endpoint_name}: Successfully processed.")
        return jsonify({
            "success": True,
            "message": f"{result.get('updatedCells', 0)} cells updated.",
            "updatedRange": result.get('updatedRange')
        })
    except HttpError as e:
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "An unexpected server error occurred."}), 500

@app.route('/spreadsheets/<spreadsheet_id>/rows/delete', methods=['DELETE'])
def delete_rows_endpoint(spreadsheet_id):
    endpoint_name = f"/spreadsheets/{spreadsheet_id}/rows/delete"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.get_json()
        logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")
        if not data or not all(k in data for k in ("sheetId", "startIndex", "endIndex")):
            logger.warning(f"ENDPOINT {endpoint_name}: Missing required fields in request body.")
            return jsonify({"success": False, "error": "Missing 'sheetId', 'startIndex', or 'endIndex' in request body"}), 400

        sheet_id = int(data["sheetId"])
        start_index = int(data["startIndex"])
        end_index = int(data["endIndex"])
        
        if start_index < 0 or end_index < 0 or start_index >= end_index:
            logger.warning(f"ENDPOINT {endpoint_name}: Invalid startIndex/endIndex: start={start_index}, end={end_index}")
            return jsonify({"success": False, "error": "Invalid startIndex or endIndex. startIndex must be < endIndex and both >= 0."}), 400
        
        logger.info(f"ENDPOINT {endpoint_name}: Processing for spreadsheet '{spreadsheet_id}', sheetId {sheet_id}, rows {start_index}-{end_index-1}")
        access_token = get_access_token()
        service = get_sheets_service(access_token)

        response = api_delete_rows(service, spreadsheet_id, sheet_id, start_index, end_index)
        num_replies = len(response.get("replies", []))
        logger.info(f"ENDPOINT {endpoint_name}: Successfully processed. Replies count: {num_replies}")

        return jsonify({
            "success": True,
            "message": f"Delete rows request processed for sheetId {sheet_id} from index {start_index} to {end_index-1}.",
            "spreadsheetId": response.get("spreadsheetId"),
            "replies_count": num_replies
        })
    except HttpError as e:
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except ValueError as e: 
        logger.warning(f"ENDPOINT {endpoint_name}: ValueError (likely invalid input type for int conversion): {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"Invalid input for sheetId, startIndex, or endIndex. Must be integers. Details: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "An unexpected server error occurred."}), 500

@app.route('/spreadsheets/<spreadsheet_id>/values/clear', methods=['POST'])
def clear_values_endpoint(spreadsheet_id):
    endpoint_name = f"/spreadsheets/{spreadsheet_id}/values/clear"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        data = request.get_json()
        logger.debug(f"ENDPOINT {endpoint_name}: Request body: {data}")
        if not data or 'range' not in data:
            logger.warning(f"ENDPOINT {endpoint_name}: Missing 'range' in request body.")
            return jsonify({"success": False, "error": "Missing 'range' in request body"}), 400
        
        range_to_clear = data['range']
        logger.info(f"ENDPOINT {endpoint_name}: Processing to clear range '{range_to_clear}' in spreadsheet '{spreadsheet_id}'")
        access_token = get_access_token()
        service = get_sheets_service(access_token)
        
        result = api_clear_values(service, spreadsheet_id, range_to_clear)
        logger.info(f"ENDPOINT {endpoint_name}: Successfully processed.")
        return jsonify({
            "success": True,
            "message": f"Successfully cleared values in range: {result.get('clearedRange')}",
            "clearedRange": result.get("clearedRange"),
            "spreadsheetId": result.get("spreadsheetId")
        })
    except HttpError as e:
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "An unexpected server error occurred."}), 500

@app.route('/spreadsheets/<spreadsheet_id>/metadata', methods=['GET'])
def get_metadata_endpoint(spreadsheet_id):
    endpoint_name = f"/spreadsheets/{spreadsheet_id}/metadata"
    logger.info(f"ENDPOINT {endpoint_name}: Request received.")
    try:
        logger.info(f"ENDPOINT {endpoint_name}: Processing to get metadata for spreadsheet '{spreadsheet_id}'")
        access_token = get_access_token()
        service = get_sheets_service(access_token)
        
        metadata = api_get_sheet_metadata(service, spreadsheet_id)
        logger.info(f"ENDPOINT {endpoint_name}: Successfully processed.")
        return jsonify({"success": True, "metadata": metadata})
    except HttpError as e:
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"ENDPOINT {endpoint_name}: Google API HttpError: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except Exception as e:
        logger.error(f"ENDPOINT {endpoint_name}: Generic exception: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "An unexpected server error occurred."}), 500

if __name__ == '__main__':
    if not CLIENT_SECRET:
        logger.critical("CRITICAL STARTUP ERROR: GOOGLE_CLIENT_SECRET environment variable is not set.")
        print("CRITICAL ERROR: GOOGLE_CLIENT_SECRET environment variable is not set.")
        print("Please set it before running the application.")
        print("Example (Linux/macOS): export GOOGLE_CLIENT_SECRET='your_actual_secret_here'")
        print("Example (Windows CMD): set GOOGLE_CLIENT_SECRET=your_actual_secret_here")
        print("Example (Windows PowerShell): $env:GOOGLE_CLIENT_SECRET='your_actual_secret_here'")
    else:
        logger.info(f"GOOGLE_CLIENT_SECRET is set (length: {len(CLIENT_SECRET)}).") # Avoid logging the secret itself
        logger.info("Starting Flask application...")
        # Host 0.0.0.0 makes it accessible on your network.
        # debug=True is useful for development but should be False in production
        # as it can expose security risks and affect performance/logging.
        app.run(host="0.0.0.0", port=5000, debug=True)
