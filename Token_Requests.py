from flask import Flask, jsonify, request
import os
import requests

app = Flask(__name__)

# Function to exchange the authorization code for tokens
def exchange_code_for_tokens(authorization_code):
    token_url = "https://oauth2.googleapis.com/token"
    
    client_id = "26763482887-coiufpukc1l69aaulaiov5o0u3en2del.apps.googleusercontent.com"
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")  # Ensure this is set in the platform
    redirect_uri = "https://serverless.on-demand.io/auth/callback"

    payload = {
        "code": authorization_code,
        "client_id": client_id,
        "client_secret": client_secret,
        "redirect_uri": redirect_uri,
        "grant_type": "authorization_code"
    }

    response = requests.post(token_url, data=payload)
    if response.status_code == 200:
        return response.json()
    else:
        raise Exception(f"Failed to get tokens: {response.text}")

# OAuth2 callback route
@app.route('/auth/callback', methods=['GET'])
def oauth2callback():
    authorization_code = request.args.get('code')
    if authorization_code:
        try:
            token_data = exchange_code_for_tokens(authorization_code)
            return jsonify({
                "message": "Authorization successful",
                "tokens": token_data
            })
        except Exception as e:
            return jsonify({"error": str(e)}), 500
    else:
        return jsonify({"error": "Authorization code missing"}), 400

# Function to get access token using a refresh token
def get_access_token(refresh_token):
    token_url = "https://oauth2.googleapis.com/token"
    client_id = "26763482887-coiufpukc1l69aaulaiov5o0u3en2del.apps.googleusercontent.com"
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

    payload = {
        "client_id": client_id,
        "client_secret": client_secret,
        "refresh_token": refresh_token,
        "grant_type": "refresh_token"
    }

    response = requests.post(token_url, data=payload)
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise Exception(f"Failed to obtain access token: {response.text}")

# Endpoint to update a cell in Google Sheets
@app.route('/apps/googlesheets/edit', methods=['POST'])
def edit_cell():
    try:
        data = request.json
        spreadsheet_id = data['spreadsheet_id']
        cell_range = data['cell_range']
        new_value = data['new_value']
        refresh_token = data['refresh_token']

        access_token = get_access_token(refresh_token)

        update_url = f"https://sheets.googleapis.com/v4/spreadsheets/{spreadsheet_id}/values/{cell_range}?valueInputOption=RAW"

        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json"
        }

        body = {
            "range": cell_range,
            "majorDimension": "ROWS",
            "values": [[new_value]]
        }

        response = requests.put(update_url, headers=headers, json=body)
        if response.status_code == 200:
            return jsonify({"success": True, "message": "Cell updated successfully."})
        else:
            return jsonify({"success": False, "error": response.text}), 400

    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# Run the Flask app on the correct host and port
if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=int(os.environ.get("PORT", 8080)))
