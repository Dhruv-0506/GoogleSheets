from flask import Flask, jsonify, request
import os
import requests
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

app = Flask(__name__)

# --- Configuration ---
# Load from environment variables
CLIENT_ID = os.getenv("GOOGLE_CLIENT_ID")
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")
REFRESH_TOKEN = os.getenv("GOOGLE_REFRESH_TOKEN")
DEFAULT_SPREADSHEET_ID = os.getenv("DEFAULT_SPREADSHEET_ID") # Optional default

TOKEN_URI = "https://oauth2.googleapis.com/token"
SCOPES = ['https://www.googleapis.com/auth/spreadsheets']

if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
    print("ERROR: Ensure GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN are set as environment variables.")
    # exit(1) # Or handle more gracefully

# --- Authentication Helper ---
def get_credentials():
    """Gets fresh Google API credentials using the refresh token."""
    if not CLIENT_ID or not CLIENT_SECRET or not REFRESH_TOKEN:
        raise ValueError("Client ID, Client Secret, or Refresh Token is missing. Set environment variables.")

    creds = Credentials(
        None,  # No access token initially, it will be refreshed
        refresh_token=REFRESH_TOKEN,
        token_uri=TOKEN_URI,
        client_id=CLIENT_ID,
        client_secret=CLIENT_SECRET,
        scopes=SCOPES
    )
    # The Credentials object will automatically refresh the access token if it's expired or not present.
    # You can force a refresh if needed:
    # if not creds.valid:
    #     if creds.expired and creds.refresh_token:
    #         creds.refresh(Request())
    return creds

def get_sheets_service():
    """Builds and returns a Google Sheets API service object."""
    credentials = get_credentials()
    service = build('sheets', 'v4', credentials=credentials)
    return service

# --- Raw Access Token Endpoint (as per original request) ---
@app.route('/token', methods=['GET'])
def token_endpoint():
    """Provides the raw access token. Use with caution."""
    try:
        # This re-implements the token refresh, useful if you need just the token string
        # For Google API client library usage, get_credentials() is preferred.
        payload = {
            "client_id": CLIENT_ID,
            "client_secret": CLIENT_SECRET,
            "refresh_token": REFRESH_TOKEN,
            "grant_type": "refresh_token"
        }
        response = requests.post(TOKEN_URI, data=payload)
        response.raise_for_status() # Raises an HTTPError for bad responses (4XX or 5XX)
        access_token = response.json()["access_token"]
        return jsonify({
            "success": True,
            "access_token": access_token
        })
    except requests.exceptions.HTTPError as http_err:
        return jsonify({
            "success": False,
            "error": f"HTTP error obtaining access token: {http_err}",
            "details": http_err.response.text if http_err.response else "No response details"
        }), response.status_code
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

# --- Google Sheets API Endpoints ---

@app.route('/sheet/data', methods=['GET'])
def get_sheet_data():
    """
    Gets data from a specified range in a Google Sheet.
    Query Params:
        spreadsheet_id (str, optional): The ID of the spreadsheet. Uses DEFAULT_SPREADSHEET_ID if not provided.
        range_name (str, required): The A1 notation of the range to retrieve (e.g., 'Sheet1!A1:B5').
    """
    spreadsheet_id = request.args.get('spreadsheet_id', DEFAULT_SPREADSHEET_ID)
    range_name = request.args.get('range_name')

    if not spreadsheet_id:
        return jsonify({"success": False, "error": "spreadsheet_id is required if DEFAULT_SPREADSHEET_ID is not set."}), 400
    if not range_name:
        return jsonify({"success": False, "error": "range_name query parameter is required."}), 400

    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().get(
            spreadsheetId=spreadsheet_id,
            range=range_name
        ).execute()
        values = result.get('values', [])
        return jsonify({"success": True, "spreadsheet_id": spreadsheet_id, "range": range_name, "values": values})
    except HttpError as e:
        return jsonify({"success": False, "error": f"Google API Error: {e.resp.status} {e._get_reason()}", "details": e.content.decode()}), e.resp.status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/sheet/data', methods=['POST'])
def append_sheet_data():
    """
    Appends data to a sheet. The data is appended after the last row with data in the specified range.
    Query Params:
        spreadsheet_id (str, optional): The ID of the spreadsheet. Uses DEFAULT_SPREADSHEET_ID if not provided.
        range_name (str, required): The A1 notation of the range (e.g., 'Sheet1!A1').
                                    The API will find the first empty row after data in this range.
    JSON Body:
        {
            "values": [
                ["Row1Col1", "Row1Col2"],
                ["Row2Col1", "Row2Col2"]
            ]
        }
    """
    spreadsheet_id = request.args.get('spreadsheet_id', DEFAULT_SPREADSHEET_ID)
    range_name = request.args.get('range_name') # e.g., "Sheet1" or "Sheet1!A1" to append after table in A column

    if not spreadsheet_id:
        return jsonify({"success": False, "error": "spreadsheet_id is required if DEFAULT_SPREADSHEET_ID is not set."}), 400
    if not range_name:
        return jsonify({"success": False, "error": "range_name query parameter is required."}), 400

    try:
        data = request.get_json()
        if not data or 'values' not in data:
            return jsonify({"success": False, "error": "JSON body with 'values' array is required."}), 400

        values_to_append = data['values']
        if not isinstance(values_to_append, list):
            return jsonify({"success": False, "error": "'values' must be an array of arrays."}), 400

        body = {
            'values': values_to_append
        }
        service = get_sheets_service()
        result = service.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='USER_ENTERED',  # Or 'RAW'
            insertDataOption='INSERT_ROWS', # Or 'OVERWRITE' if range is specific and you want to replace
            body=body
        ).execute()
        return jsonify({"success": True, "spreadsheet_id": spreadsheet_id, "updates": result.get('updates')})
    except HttpError as e:
        return jsonify({"success": False, "error": f"Google API Error: {e.resp.status} {e._get_reason()}", "details": e.content.decode()}), e.resp.status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/sheet/data', methods=['PUT'])
def update_sheet_data():
    """
    Updates data in a specific range of a Google Sheet.
    Query Params:
        spreadsheet_id (str, optional): The ID of the spreadsheet. Uses DEFAULT_SPREADSHEET_ID if not provided.
        range_name (str, required): The A1 notation of the range to update (e.g., 'Sheet1!A1:B2').
    JSON Body:
        {
            "values": [
                ["UpdatedVal1", "UpdatedVal2"],
                ["UpdatedVal3", "UpdatedVal4"]
            ]
        }
    """
    spreadsheet_id = request.args.get('spreadsheet_id', DEFAULT_SPREADSHEET_ID)
    range_name = request.args.get('range_name')

    if not spreadsheet_id:
        return jsonify({"success": False, "error": "spreadsheet_id is required if DEFAULT_SPREADSHEET_ID is not set."}), 400
    if not range_name:
        return jsonify({"success": False, "error": "range_name query parameter is required."}), 400

    try:
        data = request.get_json()
        if not data or 'values' not in data:
            return jsonify({"success": False, "error": "JSON body with 'values' array is required."}), 400

        values_to_update = data['values']
        if not isinstance(values_to_update, list):
            return jsonify({"success": False, "error": "'values' must be an array of arrays."}), 400

        body = {
            'values': values_to_update
        }
        service = get_sheets_service()
        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption='USER_ENTERED',  # Or 'RAW'
            body=body
        ).execute()
        return jsonify({"success": True, "spreadsheet_id": spreadsheet_id, "updated_range": result.get('updatedRange')})
    except HttpError as e:
        return jsonify({"success": False, "error": f"Google API Error: {e.resp.status} {e._get_reason()}", "details": e.content.decode()}), e.resp.status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/sheet/data', methods=['DELETE'])
def clear_sheet_data():
    """
    Clears data from a specific range in a Google Sheet.
    Query Params:
        spreadsheet_id (str, optional): The ID of the spreadsheet. Uses DEFAULT_SPREADSHEET_ID if not provided.
        range_name (str, required): The A1 notation of the range to clear (e.g., 'Sheet1!A1:B10').
    """
    spreadsheet_id = request.args.get('spreadsheet_id', DEFAULT_SPREADSHEET_ID)
    range_name = request.args.get('range_name')

    if not spreadsheet_id:
        return jsonify({"success": False, "error": "spreadsheet_id is required if DEFAULT_SPREADSHEET_ID is not set."}), 400
    if not range_name:
        return jsonify({"success": False, "error": "range_name query parameter is required."}), 400

    try:
        service = get_sheets_service()
        result = service.spreadsheets().values().clear(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            body={} # Body is required, even if empty for clear
        ).execute()
        return jsonify({"success": True, "spreadsheet_id": spreadsheet_id, "cleared_range": result.get('clearedRangeId') or range_name})
    except HttpError as e:
        return jsonify({"success": False, "error": f"Google API Error: {e.resp.status} {e._get_reason()}", "details": e.content.decode()}), e.resp.status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

if __name__ == "__main__":
    if not all([CLIENT_ID, CLIENT_SECRET, REFRESH_TOKEN]):
        print("CRITICAL ERROR: Missing Google API credentials in environment variables.")
        print("Please set GOOGLE_CLIENT_ID, GOOGLE_CLIENT_SECRET, and GOOGLE_REFRESH_TOKEN.")
    else:
        print(f"Flask app running. Default Spreadsheet ID: {DEFAULT_SPREADSHEET_ID or 'Not Set'}")
        print("Ensure your refresh token has 'https://www.googleapis.com/auth/spreadsheets' scope.")
        app.run(debug=True, port=5000) # Port 5000 is common for Flask, 8080 is often Gunicorn default
