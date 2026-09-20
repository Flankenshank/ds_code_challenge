import json
import urllib.request

URL = "https://cct-ds-code-challenge-input-data.s3.af-south-1.amazonaws.com/ds_code_challenge_creds.json"

def fetch_client_keys():
    with urllib.request.urlopen(URL) as response:
        raw_data = response.read()

    keys = json.loads(raw_data)
    return keys