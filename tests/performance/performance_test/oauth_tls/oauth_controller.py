import requests
import json
import os
import sys
import urllib3
import time


from oauth.oauth_functions import get_access_token

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


keycloak_url = os.environ.get("KEYCLOAK_URL", "https://192.168.100.15:8443")
realm = os.environ.get("KEYCLOAK_REALM", "master")


cert_root = ""
for path in sys.path:
    if path.endswith("certs"):
        cert_root = path
        break
cert_path = os.path.join(cert_root, 'keycloak.crt')

keycloak_cert_path = cert_path

token_endpoint = f"{keycloak_url}/realms/{realm}/protocol/openid-connect/token"
# credentials_file is now passed dynamically by the runner scripts


# ---------------------

def load_credentials_from_file(credentials_file_path):
    """Loads client credentials from the persistent JSON file specific to the batch."""
    try:

        script_dir = os.path.dirname(os.path.abspath(__file__))
        full_path = os.path.join(script_dir, credentials_file_path)

        with open(full_path, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"Error: Credentials file not found at {full_path}. Did the corresponding runner script run Step 1?")
        return []
    except json.JSONDecodeError:
        print(f"Error: Credentials file is corrupted or empty at {full_path}.")
        return []


async def authenticate_clients(credentials_file_path):
    """
    Loads credentials from the specified file, authenticates each client, and enriches the data with a live access token.
    """
    # Load only the batch-specific clients
    client_credentials_list = load_credentials_from_file(credentials_file_path)
    authenticated_list = []

    if not client_credentials_list:
        print("No credentials loaded to authenticate.")
        return authenticated_list

    print(f"\nAttempting to authenticate {len(client_credentials_list)} clients from {credentials_file_path}...")

    for client_data in client_credentials_list:
        client_id = client_data.get('client_id')
        client_secret = client_data.get('client_secret')
        cp_id = client_data.get('cp_id')


        access_token = await get_access_token(
            token_endpoint,
            client_id,
            client_secret,
            keycloak_cert_path,
            None
        )

        if access_token:

            client_data['access_token'] = access_token
            client_data['keycloak_cert_path'] = keycloak_cert_path
            # -----------------------------------------------------------
            authenticated_list.append(client_data)
        else:
            print(f"[{cp_id}] Failed to retrieve access token. Skipping.")

    return authenticated_list


if __name__ == "__main__":
    # This script is intended to be called by the runner scripts.
    print("This script is intended to be called by the runner scripts.")
    pass
