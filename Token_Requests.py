from flask import Flask, jsonify, request
import os
import requests
import logging
import time # For timing operations

# Imports for Google API
from google.oauth2.credentials import Credentials as OAuthCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

# --- Logging Configuration ---
# Configure logging to output to console. You can customize this further.
# For example, to write to a file, add: filename='app.log'
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
        "client_secret": CLIENT_SECRET, # Be mindful of logging secrets in production
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token"
    }
    logger.debug(f"Token request payload (excluding client_secret for safety): {{'client_id': '{CLIENT_ID}', 'refresh_token': '...', 'grant_type': 'refresh_token'}}")

    try:
        response = requests.post(TOKEN_URL, data=payload, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()  # Raises an HTTPError for bad responses (4XX or 5XX)
        token_data = response.json()
        access_token = token_data.get("access_token")
        duration = time.time() - start_time
        if access_token:
            logger.info(f"Successfully obtained new access token in {duration:.2f} seconds. Expires in: {token_data.get('expires_in')}s")
            return access_token
        else:
            logger.error(f"Failed to get access token from response. Response: {token_data}")
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
        logger.error(f"Generic exception while requesting token after {duration:.2f} seconds: {str(e)}")
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
        logger.error(f"Failed to build Google Sheets API service: {str(e)}")
        raise

# --- Google Sheets API Wrapper Functions ---

def api_create_spreadsheet(service, title):
    """Creates a new spreadsheet."""
    logger.info(f"Attempting to create spreadsheet with title: '{title}'")
    start_time = time.time()
    spreadsheet_body = {"properties": {"title": title}}
    try:
        spreadsheet = (
            service.spreadsheets()
            .create(body=spreadsheet_body, fields="spreadsheetId,spreadsheetUrl")
            .execute()
        )
        duration = time.time() - start_time
        logger.info(f"Successfully created spreadsheet '{title}' in {duration:.2f} seconds. ID: {spreadsheet.get('spreadsheetId')}")
        return spreadsheet
    except HttpError as e:
        duration = time.time() - start_time
        logger.error(f"Google API HttpError creating spreadsheet '{title}' after {duration:.2f}s: {e.content.decode() if e.content else str(e)}")
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Generic error creating spreadsheet '{title}' after {duration:.2f}s: {str(e)}")
        raise

def api_get_values(service, spreadsheet_id, range_name):
    """Gets values from a spreadsheet."""
    logger.info(f"Attempting to get values from spreadsheet '{spreadsheet_id}', range '{range_name}'")
    start_time = time.time()
    try:
        result = (
            service.spreadsheets()
            .values()
            .get(spreadsheetId=spreadsheet_id, range=range_name)
            .execute()
        )
        duration = time.time() - start_time
        logger.info(f"Successfully got values from '{spreadsheet_id}', range '{range_name}' in {duration:.2f} seconds. Rows: {len(result.get('values', []))}")
        return result
    except HttpError as e:
        duration = time.time() - start_time
        logger.error(f"Google API HttpError getting values from '{spreadsheet_id}', range '{range_name}' after {duration:.2f}s: {e.content.decode() if e.content else str(e)}")
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Generic error getting values from '{spreadsheet_id}', range '{range_name}' after {duration:.2f}s: {str(e)}")
        raise


def api_append_values(service, spreadsheet_id, range_name, value_input_option, values_data):
    """Appends values to a spreadsheet."""
    logger.info(f"Attempting to append values to spreadsheet '{spreadsheet_id}', range '{range_name}', option '{value_input_option}'")
    logger.debug(f"Values to append: {values_data}")
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
        logger.info(f"Successfully appended values to '{spreadsheet_id}' in {duration:.2f} seconds. Cells updated: {result.get('updates', {}).get('updatedCells', 0)}")
        return result
    except HttpError as e:
        duration = time.time() - start_time
        logger.error(f"Google API HttpError appending values to '{spreadsheet_id}' after {duration:.2f}s: {e.content.decode() if e.content else str(e)}")
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Generic error appending values to '{spreadsheet_id}' after {duration:.2f}s: {str(e)}")
        raise

def api_update_values(service, spreadsheet_id, range_name, value_input_option, values_data):
    """Updates values in a spreadsheet."""
    logger.info(f"Attempting to update values in spreadsheet '{spreadsheet_id}', range '{range_name}', option '{value_input_option}'")
    logger.debug(f"Values to update: {values_data}")
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
        logger.info(f"Successfully updated values in '{spreadsheet_id}' in {duration:.2f} seconds. Cells updated: {result.get('updatedCells', 0)}")
        return result
    except HttpError as e:
        duration = time.time() - start_time
        logger.error(f"Google API HttpError updating values in '{spreadsheet_id}' after {duration:.2f}s: {e.content.decode() if e.content else str(e)}")
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Generic error updating values in '{spreadsheet_id}' after {duration:.2f}s: {str(e)}")
        raise

def api_delete_rows(service, spreadsheet_id, sheet_id, start_index, end_index):
    """Deletes rows from a specific sheet within a spreadsheet."""
    logger.info(f"Attempting to delete rows from spreadsheet '{spreadsheet_id}', sheetId {sheet_id}, rows {start_index}-{end_index-1}")
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
        logger.info(f"Successfully sent delete rows request for '{spreadsheet_id}', sheet {sheet_id} in {duration:.2f} seconds. Replies: {len(response.get('replies',[]))}")
        return response
    except HttpError as e:
        duration = time.time() - start_time
        logger.error(f"Google API HttpError deleting rows from '{spreadsheet_id}', sheet {sheet_id} after {duration:.2f}s: {e.content.decode() if e.content else str(e)}")
        raise
    except Exception as e:
        duration = time.time() - start_time
        logger.error(f"Generic error deleting rows from '{spreadsheet_id}', sheet {sheet_id} after {duration:.2f}s: {str(e)}")
        raise


# --- Flask Endpoints ---

@app.route('/token', methods=['GET'])
def token_endpoint():
    endpoint_name = "/token"
    logger.info(f"Request received for {endpoint_name}")
    try:
        access_token = get_access_token() # Logging is inside this function
        logger.info(f"Successfully processed {endpoint_name}")
        return jsonify({"success": True, "access_token": access_token})
    except requests.exceptions.HTTPError as e:
        logger.error(f"HTTPError in {endpoint_name}: {str(e.response.text if e.response else e)}")
        return jsonify({"success": False, "error": "Failed to obtain access token", "details": str(e.response.text if e.response else e)}), 500
    except Exception as e:
        logger.error(f"Exception in {endpoint_name}: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/spreadsheets/create', methods=['POST'])
def create_spreadsheet_endpoint():
    endpoint_name = "/spreadsheets/create"
    logger.info(f"Request received for {endpoint_name}")
    try:
        data = request.get_json()
        logger.debug(f"Request body for {endpoint_name}: {data}")
        if not data or "title" not in data:
            logger.warning(f"Missing 'title' in request body for {endpoint_name}")
            return jsonify({"success": False, "error": "Missing 'title' in request body"}), 400

        title = data["title"]
        logger.info(f"Processing {endpoint_name} with title: '{title}'")
        access_token = get_access_token()
        service = get_sheets_service(access_token)
        
        spreadsheet_info = api_create_spreadsheet(service, title)
        logger.info(f"Successfully processed {endpoint_name} for title '{title}'")
        return jsonify({
            "success": True,
            "message": f"Spreadsheet created successfully.",
            "spreadsheetId": spreadsheet_info.get("spreadsheetId"),
            "spreadsheetUrl": spreadsheet_info.get("spreadsheetUrl")
        })
    except HttpError as e:
        logger.error(f"Google API HttpError in {endpoint_name}: {e.content.decode() if e.content else str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": e.content.decode() if e.content else str(e)}), e.resp.status
    except Exception as e:
        logger.error(f"Exception in {endpoint_name}: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/spreadsheets/<spreadsheet_id>/values/<path:range_name>', methods=['GET'])
def get_values_endpoint(spreadsheet_id, range_name):
    endpoint_name = f"/spreadsheets/{spreadsheet_id}/values/{range_name}"
    logger.info(f"Request received for {endpoint_name}")
    try:
        logger.info(f"Processing {endpoint_name} for spreadsheet '{spreadsheet_id}', range '{range_name}'")
        access_token = get_access_token()
        service = get_sheets_service(access_token)
        
        result = api_get_values(service, spreadsheet_id, range_name)
        logger.info(f"Successfully processed {endpoint_name}")
        return jsonify({
            "success": True,
            "range": result.get("range"),
            "values": result.get("values", [])
        })
    except HttpError as e:
        logger.error(f"Google API HttpError in {endpoint_name}: {e.content.decode() if e.content else str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": e.content.decode() if e.content else str(e)}), e.resp.status
    except Exception as e:
        logger.error(f"Exception in {endpoint_name}: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/spreadsheets/<spreadsheet_id>/values/append', methods=['POST'])
def append_values_endpoint(spreadsheet_id):
    endpoint_name = f"/spreadsheets/{spreadsheet_id}/values/append"
    logger.info(f"Request received for {endpoint_name}")
    try:
        data = request.get_json()
        logger.debug(f"Request body for {endpoint_name}: {data}")
        if not data or not all(k in data for k in ("range", "valueInputOption", "values")):
            logger.warning(f"Missing required fields in request body for {endpoint_name}")
            return jsonify({"success": False, "error": "Missing 'range', 'valueInputOption', or 'values' in request body"}), 400

        range_name = data["range"]
        value_input_option = data["valueInputOption"]
        values_data = data["values"]
        logger.info(f"Processing {endpoint_name} for spreadsheet '{spreadsheet_id}', range '{range_name}'")

        access_token = get_access_token()
        service = get_sheets_service(access_token)
        
        result = api_append_values(service, spreadsheet_id, range_name, value_input_option, values_data)
        logger.info(f"Successfully processed {endpoint_name}")
        return jsonify({
            "success": True,
            "message": f"{result.get('updates', {}).get('updatedCells', 0)} cells appended.",
            "updatedRange": result.get('updates', {}).get('updatedRange')
        })
    except HttpError as e:
        logger.error(f"Google API HttpError in {endpoint_name}: {e.content.decode() if e.content else str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": e.content.decode() if e.content else str(e)}), e.resp.status
    except Exception as e:
        logger.error(f"Exception in {endpoint_name}: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/spreadsheets/<spreadsheet_id>/values/update', methods=['PUT'])
def update_values_endpoint(spreadsheet_id):
    endpoint_name = f"/spreadsheets/{spreadsheet_id}/values/update"
    logger.info(f"Request received for {endpoint_name}")
    try:
        data = request.get_json()
        logger.debug(f"Request body for {endpoint_name}: {data}")
        if not data or not all(k in data for k in ("range", "valueInputOption", "values")):
            logger.warning(f"Missing required fields in request body for {endpoint_name}")
            return jsonify({"success": False, "error": "Missing 'range', 'valueInputOption', or 'values' in request body"}), 400
        
        range_name = data["range"]
        value_input_option = data["valueInputOption"]
        values_data = data["values"]
        logger.info(f"Processing {endpoint_name} for spreadsheet '{spreadsheet_id}', range '{range_name}'")

        access_token = get_access_token()
        service = get_sheets_service(access_token)
        
        result = api_update_values(service, spreadsheet_id, range_name, value_input_option, values_data)
        logger.info(f"Successfully processed {endpoint_name}")
        return jsonify({
            "success": True,
            "message": f"{result.get('updatedCells', 0)} cells updated.",
            "updatedRange": result.get('updatedRange')
        })
    except HttpError as e:
        logger.error(f"Google API HttpError in {endpoint_name}: {e.content.decode() if e.content else str(e)}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": e.content.decode() if e.content else str(e)}), e.resp.status
    except Exception as e:
        logger.error(f"Exception in {endpoint_name}: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/spreadsheets/<spreadsheet_id>/rows/delete', methods=['DELETE'])
def delete_rows_endpoint(spreadsheet_id):
    endpoint_name = f"/spreadsheets/{spreadsheet_id}/rows/delete"
    logger.info(f"Request received for {endpoint_name}")
    try:
        data = request.get_json()
        logger.debug(f"Request body for {endpoint_name}: {data}")
        if not data or not all(k in data for k in ("sheetId", "startIndex", "endIndex")):
            logger.warning(f"Missing required fields in request body for {endpoint_name}")
            return jsonify({"success": False, "error": "Missing 'sheetId', 'startIndex', or 'endIndex' in request body"}), 400

        sheet_id = int(data["sheetId"])
        start_index = int(data["startIndex"])
        end_index = int(data["endIndex"])
        logger.info(f"Processing {endpoint_name} for spreadsheet '{spreadsheet_id}', sheetId {sheet_id}, rows {start_index}-{end_index-1}")


        if start_index < 0 or end_index < 0 or start_index >= end_index:
            logger.warning(f"Invalid startIndex/endIndex for {endpoint_name}: start={start_index}, end={end_index}")
            return jsonify({"success": False, "error": "Invalid startIndex or endIndex. startIndex must be < endIndex and both >= 0."}), 400

        access_token = get_access_token()
        service = get_sheets_service(access_token)

        response = api_delete_rows(service, spreadsheet_id, sheet_id, start_index, end_index)
        num_replies = len(response.get("replies", []))
        logger.info(f"Successfully processed {endpoint_name}. Replies count: {num_replies}")

        return jsonify({
            "success": True,
            "message": f"Delete rows request processed for sheetId {sheet_id} from index {start_index} to {end_index-1}.",
            "spreadsheetId": response.get("spreadsheetId"),
            "replies_count": num_replies
        })
    except HttpError as e:
        error_content = e.content.decode('utf-8') if e.content else str(e)
        logger.error(f"Google API HttpError in {endpoint_name}: {error_content}", exc_info=True)
        return jsonify({"success": False, "error": "Google API Error", "details": error_content}), e.resp.status
    except ValueError as e: # Catches int() conversion errors
        logger.warning(f"ValueError in {endpoint_name} (likely invalid input type): {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": f"Invalid input for sheetId, startIndex, or endIndex. Must be integers. Details: {str(e)}"}), 400
    except Exception as e:
        logger.error(f"Exception in {endpoint_name}: {str(e)}", exc_info=True)
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    if not CLIENT_SECRET:
        # This will be logged by get_access_token as well, but good to have an early warning.
        logger.critical("CRITICAL STARTUP ERROR: GOOGLE_CLIENT_SECRET environment variable is not set.")
        print("CRITICAL ERROR: GOOGLE_CLIENT_SECRET environment variable is not set.")
        print("Please set it before running the application.")
        print("Example (Linux/macOS): export GOOGLE_CLIENT_SECRET='your_actual_secret_here'")
        print("Example (Windows CMD): set GOOGLE_CLIENT_SECRET=your_actual_secret_here")
        print("Example (Windows PowerShell): $env:GOOGLE_CLIENT_SECRET='your_actual_secret_here'")
    else:
        logger.info(f"GOOGLE_CLIENT_SECRET is set (length: {len(CLIENT_SECRET)}).")
        logger.info("Starting Flask application...")
        # Host 0.0.0.0 makes it accessible on your network.
        app.run(host="0.0.0.0", port=5000, debug=True) # debug=True might interfere with some production logging setups if not careful
