import requests
import json
import os
import urllib3
import sys

urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)


keycloak_url = os.environ.get("KEYCLOAK_URL", "https://192.168.100.15:8443")
realm = os.environ.get("KEYCLOAK_REALM", "master")
admin_username = os.environ.get("KEYCLOAK_ADMIN_USER", "admin")
admin_password = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")
admin_client_id = "admin-cli"

default_num_clients = 10
default_credentials_file = "../client_credentials/client_credentials_{batch_name}.json"

# API Endpoints
token_endpoint = f"{keycloak_url}/realms/{realm}/protocol/openid-connect/token"
clients_endpoint = f"{keycloak_url}/admin/realms/{realm}/clients"


# ---------------------

def get_admin_token():
    """Retrieves an admin access token from Keycloak."""

    print(f"Attempting to retrieve Admin Token from: {token_endpoint}...")

    token_data = {
        "grant_type": "password",
        "client_id": admin_client_id,
        "username": admin_username,
        "password": admin_password
    }

    try:
        response = requests.post(token_endpoint, data=token_data, verify=False)
        response.raise_for_status()
        token = response.json().get('access_token')

        print(f"Successfully retrieved Admin Access Token!")
        return token
    except requests.exceptions.RequestException as e:
        print(f"\n--- ADMIN AUTHENTICATION FAILED ---")
        print(f"Error connecting to Keycloak. Details: {e}")
        return None


def create_client(admin_token, client_name):
    """Creates a new Service Account enabled client in Keycloak."""


    client_payload = {
        "clientId": client_name,
        "name": "",
        "description": "",
        "rootUrl": "",
        "adminUrl": "",
        "baseUrl": "",
        "surrogateAuthRequired": False,
        "enabled": True,
        "alwaysDisplayInConsole": False,
        "clientAuthenticatorType": "client-secret",
        "redirectUris": ["/*"],
        "webOrigins": ["/*"],
        "notBefore": 0,
        "bearerOnly": False,
        "consentRequired": False,
        "standardFlowEnabled": False,
        "implicitFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "serviceAccountsEnabled": True,
        "publicClient": False,
        "frontchannelLogout": False,
        "protocol": "openid-connect",
        "fullScopeAllowed": True,
        "nodeReRegistrationTimeout": -1,
        "defaultClientScopes": [
            "service_account", "web-origins", "roles", "profile", "basic", "email"
        ],
        "optionalClientScopes": [],
    }

    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }

    print(f"Creating client: {client_name}...")
    try:
        response = requests.post(clients_endpoint, headers=headers, data=json.dumps(client_payload), verify=False)
        response.raise_for_status()
        print(f"Client {client_name} created successfully.")
        return True
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 409:
            # Client already exists, treat as success for idempotence
            print(f"Client {client_name} already exists. Skipping creation.")
            return True
        print(f"Failed to create client {client_name}. Status: {e.response.status_code}, Response: {e.response.text}")
        return False


def get_client_secret(admin_token, client_name):
    """Finds the Client UUID and retrieves the secret."""
    headers = {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json"
    }

    try:
        # 1. Find the Client UUID (Internal ID)
        search_response = requests.get(f"{clients_endpoint}?clientId={client_name}", headers=headers, verify=False)
        search_response.raise_for_status()
        client_data = search_response.json()

        if not client_data:
            print(f"Error: Could not find client data for {client_name}.")
            return None

        client_uuid = client_data[0]['id']

        # 2. Get the Secret using the UUID
        secret_endpoint = f"{clients_endpoint}/{client_uuid}/client-secret"

        secret_response = requests.get(secret_endpoint, headers=headers, verify=False)
        secret_response.raise_for_status()
        secret_data = secret_response.json()

        return secret_data.get('value')

    except requests.exceptions.RequestException as e:
        print(f"Failed to retrieve secret for {client_name}. Details: {e}")
        return None


def generate_clients(num_clients_to_gen=default_num_clients, start_id=1, credentials_file_path=None):
    """
    Main orchestration function to generate clients within a specific ID range and save credentials
    to a batch-specific file.
    """
    admin_token = get_admin_token()

    if not admin_token:
        raise ConnectionError("Cannot proceed without a valid Admin Token.")

    # Determine the end ID for the loop
    end_id = start_id + num_clients_to_gen

    # Determine the credentials file path
    if credentials_file_path is None:

        credentials_file_path = default_credentials_file.format(batch_name=f"start{start_id}_count{num_clients_to_gen}")


    client_credentials_list = []


    for i in range(start_id, end_id):

        client_name = f"test_client_{i}"
        cp_id = f"cp{i}"

        if create_client(admin_token, client_name):
            client_secret = get_client_secret(admin_token, client_name)

            if client_secret:
                client_credentials_list.append({
                    "client_id": client_name,
                    "client_secret": client_secret,
                    "cp_id": cp_id,
                })


    # Save credentials to file
    if client_credentials_list:
        print(f"Saving credentials for {len(client_credentials_list)} clients to {credentials_file_path}...")

        # Ensure the directory exists
        output_dir = os.path.dirname(credentials_file_path)
        if output_dir and not os.path.exists(output_dir):
            os.makedirs(output_dir, exist_ok=True)

        with open(credentials_file_path, 'w') as f:
            json.dump(client_credentials_list, f, indent=4)

        print(f"Successfully saved {len(client_credentials_list)} clients to {credentials_file_path}.")
        return client_credentials_list
    else:
        print("No clients were successfully generated or retrieved.")
        return []


if __name__ == "__main__":
    try:
        print("Running default client generation (clients 1-10)...")
        generate_clients(num_clients_to_gen=10, start_id=1, credentials_file_path=default_credentials_file.format(batch_name="default"))
    except Exception as e:
        print(f"An error occurred during client generation: {e}")
