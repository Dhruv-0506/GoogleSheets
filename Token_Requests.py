from flask import Flask, jsonify, request
import os
import requests

app = Flask(__name__)

def get_access_token():
    token_url = "https://oauth2.googleapis.com/token"
    client_id = "26763482887-q9lcln5nmb0setr60gkohdjrt2msl6o5.apps.googleusercontent.com"
    client_secret = os.getenv("GOOGLE_CLIENT_SECRET")
    refresh_token = "1//09zxz8WxEV7hpCgYIARAAGAkSNwF-L9IrfoSJ7UYywPUkdJEdW-Jj_bMFoA7HNh109drcwUm0RgaAbxbP-o0Ppnf8v6E_Jmndbjc"

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

@app.route('/token', methods=['GET'])
def token_endpoint():
    try:
        access_token = get_access_token()
        return jsonify({
            "success": True,
            "access_token": access_token
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "error": str(e)
        }), 500

@app.route('/apps/googlesheets/edit', methods=['POST'])
def edit_cell():
    try:
        data = request.json
        spreadsheet_id = data['spreadsheet_id']
        cell_range = data['cell_range']  # e.g., "Sheet1!B2"
        new_value = data['new_value']

        access_token = get_access_token()

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

if __name__ == "__main__":
    app.run(debug=True)
