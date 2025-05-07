import requests

def get_access_token():
    token_url = "https://oauth2.googleapis.com/token"
    
    payload = {
        "client_id": "26763482887-q9lcln5nmb0setr60gkohdjrt2msl6o5.apps.googleusercontent.com",
        "client_secret": "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",
        "refresh_token": "1//09zxz8WxEV7hpCgYIARAAGAkSNwF-L9IrfoSJ7UYywPUkdJEdW-Jj_bMFoA7HNh109drcwUm0RgaAbxbP-o0Ppnf8v6E_Jmndbjc",
        "grant_type": "refresh_token"
    }

    response = requests.post(token_url, data=payload)
    
    if response.status_code == 200:
        return response.json()["access_token"]
    else:
        raise Exception(f"Failed to obtain access token: {response.text}")

# Example usage:
# access_token = get_access_token()
# print("Access Token:", access_token)
