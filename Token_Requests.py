from flask import Flask, jsonify, request
import os
import requests

# Imports for Google API
from google.oauth2.credentials import Credentials as OAuthCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

app = Flask(__name__)

# --- Configuration (Consider moving to environment variables or a config file) ---
# Client ID from your Google Cloud Console OAuth 2.0 Credentials
CLIENT_ID = "26763482887-q9lcln5nmb0setr60gkohdjrt2msl6o5.apps.googleusercontent.com"
# Refresh token obtained through OAuth 2.0 flow
REFRESH_TOKEN = "1//09zxz8WxEV7hpCgYIARAAGAkSNwF-L9IrfoSJ7UYywPUkdJEdW-Jj_bMFoA7HNh109drcwUm0RgaAbxbP-o0Ppnf8v6E_Jmndbjc"
# Google Client Secret - SET THIS AS AN ENVIRONMENT VARIABLE
CLIENT_SECRET = os.getenv("GOOGLE_CLIENT_SECRET")

TOKEN_URL = "https://oauth2.googleapis.com/token"

# --- Helper Functions ---
def get_access_token():
    """Obtains a new access token using the refresh token."""
    if not CLIENT_SECRET:
        raise ValueError("GOOGLE_CLIENT_SECRET environment variable not set.")

    payload = {
        "client_id": CLIENT_ID,
        "client_secret": CLIENT_SECRET,
        "refresh_token": REFRESH_TOKEN,
        "grant_type": "refresh_token"
    }
    response = requests.post(TOKEN_URL, data=payload)
    response.raise_for_status() # Raises an HTTPError for bad responses (4XX or 5XX)
    return response.json()["access_token"]

def get_sheets_service(access_token):
    """Builds and returns an authorized Sheets API service instance."""
    creds = OAuthCredentials(token=access_token)
    # If your refresh token might expire or be revoked, you might need to handle
    # refreshing it here or ensure the `creds` object can refresh itself if it had more info.
    # For this setup, `get_access_token` is called per request or as needed.
    service = build("sheets", "v4", credentials=creds)
    return service

# --- Google Sheets API Wrapper Functions (adapted from your snippets) ---

def api_create_spreadsheet(service, title):
    """Creates a new spreadsheet."""
    spreadsheet_body = {"properties": {"title": title}}
    spreadsheet = (
        service.spreadsheets()
        .create(body=spreadsheet_body, fields="spreadsheetId,spreadsheetUrl")
        .execute()
    )
    return spreadsheet

def api_get_values(service, spreadsheet_id, range_name):
    """Gets values from a spreadsheet."""
    result = (
        service.spreadsheets()
        .values()
        .get(spreadsheetId=spreadsheet_id, range=range_name)
        .execute()
    )
    return result

def api_append_values(service, spreadsheet_id, range_name, value_input_option, values_data):
    """Appends values to a spreadsheet."""
    body = {"values": values_data}
    result = (
        service.spreadsheets()
        .values()
        .append(
            spreadsheetId=spreadsheet_id,
            range=range_name,
            valueInputOption=value_input_option,
            body=body,
            insertDataOption="INSERT_ROWS" # Common option for append
        )
        .execute()
    )
    return result

def api_update_values(service, spreadsheet_id, range_name, value_input_option, values_data):
    """Updates values in a spreadsheet."""
    body = {"values": values_data}
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
    return result

# --- Flask Endpoints ---

@app.route('/token', methods=['GET'])
def token_endpoint():
    """Returns a fresh access token."""
    try:
        access_token = get_access_token()
        return jsonify({
            "success": True,
            "access_token": access_token
        })
    except requests.exceptions.HTTPError as e:
        return jsonify({
            "success": False,
            "error": "Failed to obtain access token",
            "details": str(e.response.text if e.response else e)
        }), 500
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/spreadsheets/create', methods=['POST'])
def create_spreadsheet_endpoint():
    """
    Creates a new spreadsheet.
    JSON Body: {"title": "My New Spreadsheet"}
    """
    try:
        data = request.get_json()
        if not data or "title" not in data:
            return jsonify({"success": False, "error": "Missing 'title' in request body"}), 400

        title = data["title"]
        access_token = get_access_token()
        service = get_sheets_service(access_token)
        
        spreadsheet_info = api_create_spreadsheet(service, title)
        return jsonify({
            "success": True,
            "message": f"Spreadsheet created successfully.",
            "spreadsheetId": spreadsheet_info.get("spreadsheetId"),
            "spreadsheetUrl": spreadsheet_info.get("spreadsheetUrl")
        })
    except HttpError as e:
        return jsonify({"success": False, "error": "Google API Error", "details": str(e)}), e.resp.status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/spreadsheets/<spreadsheet_id>/values/<path:range_name>', methods=['GET'])
def get_values_endpoint(spreadsheet_id, range_name):
    """
    Gets values from a specific range in a spreadsheet.
    Example: /spreadsheets/your_sheet_id/values/Sheet1!A1:B5
    """
    try:
        access_token = get_access_token()
        service = get_sheets_service(access_token)
        
        result = api_get_values(service, spreadsheet_id, range_name)
        return jsonify({
            "success": True,
            "range": result.get("range"),
            "values": result.get("values", [])
        })
    except HttpError as e:
        return jsonify({"success": False, "error": "Google API Error", "details": str(e)}), e.resp.status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/spreadsheets/<spreadsheet_id>/values/append', methods=['POST'])
def append_values_endpoint(spreadsheet_id):
    """
    Appends values to a sheet.
    JSON Body: {
        "range": "Sheet1!A1", // The sheet and starting cell, e.g., "Sheet1" or "Sheet1!A1"
        "valueInputOption": "USER_ENTERED" or "RAW",
        "values": [["Row1Col1", "Row1Col2"], ["Row2Col1", "Row2Col2"]]
    }
    """
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ("range", "valueInputOption", "values")):
            return jsonify({"success": False, "error": "Missing 'range', 'valueInputOption', or 'values' in request body"}), 400

        range_name = data["range"]
        value_input_option = data["valueInputOption"]
        values_data = data["values"]

        access_token = get_access_token()
        service = get_sheets_service(access_token)
        
        result = api_append_values(service, spreadsheet_id, range_name, value_input_option, values_data)
        return jsonify({
            "success": True,
            "message": f"{result.get('updates', {}).get('updatedCells', 0)} cells appended.",
            "updatedRange": result.get('updates', {}).get('updatedRange')
        })
    except HttpError as e:
        return jsonify({"success": False, "error": "Google API Error", "details": str(e)}), e.resp.status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/spreadsheets/<spreadsheet_id>/values/update', methods=['PUT']) # Or POST
def update_values_endpoint(spreadsheet_id):
    """
    Updates values in a specific range of a sheet.
    JSON Body: {
        "range": "Sheet1!A1:B2", // The exact range to update
        "valueInputOption": "USER_ENTERED" or "RAW",
        "values": [["NewA1", "NewB1"], ["NewA2", "NewB2"]]
    }
    """
    try:
        data = request.get_json()
        if not data or not all(k in data for k in ("range", "valueInputOption", "values")):
            return jsonify({"success": False, "error": "Missing 'range', 'valueInputOption', or 'values' in request body"}), 400
        
        range_name = data["range"]
        value_input_option = data["valueInputOption"]
        values_data = data["values"]

        access_token = get_access_token()
        service = get_sheets_service(access_token)
        
        result = api_update_values(service, spreadsheet_id, range_name, value_input_option, values_data)
        return jsonify({
            "success": True,
            "message": f"{result.get('updatedCells', 0)} cells updated.",
            "updatedRange": result.get('updatedRange')
        })
    except HttpError as e:
        return jsonify({"success": False, "error": "Google API Error", "details": str(e)}), e.resp.status
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500


if __name__ == "__main__":
    if not CLIENT_SECRET:
        print("Error: GOOGLE_CLIENT_SECRET environment variable is not set.")
        print("Please set it before running the application.")
        print("Example: export GOOGLE_CLIENT_SECRET='your_actual_secret_here'")
    else:
        # Host 0.0.0.0 makes it accessible on your network, useful for testing from other devices.
        # Remove if you only want localhost access.
        app.run(host="0.0.0.0", port=5000, debug=True)
