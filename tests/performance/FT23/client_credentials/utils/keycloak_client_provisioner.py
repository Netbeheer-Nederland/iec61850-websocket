import logging
import os
from pathlib import Path

import requests
import urllib3

from testing.utils.credentials_store import load_credentials, save_credentials

# urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

logger = logging.getLogger(__name__)

DEFAULT_NUM_CLIENTS = 10
DEFAULT_CREDENTIALS_FILE = "client_credentials_{batch_name}.json"
REQUEST_TIMEOUT_SECONDS = 15

BASE = os.environ.get("KEYCLOAK_URL", "http://localhost:8080")
admin_realm = os.environ.get("KEYCLOAK_REALM", "master")
admin_username = os.environ.get("KEYCLOAK_ADMIN_USER", "admin")
admin_password = os.environ.get("KEYCLOAK_ADMIN_PASSWORD", "admin")

TARGET_REALM = os.environ.get("IEC61850_REALM", "iec61850-test")
token_endpoint = f"{BASE}/realms/{admin_realm}/protocol/openid-connect/token"
clients_endpoint = f"{BASE}/admin/realms/{TARGET_REALM}/clients"


def kc_post(url, token=None, data=None, json=None):
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.post(url, headers=headers, data=data, json=json)
    r.raise_for_status()
    return r


def kc_get(url, token, params=None):
    headers = {"Authorization": f"Bearer {token}"}
    r = requests.get(url, headers=headers, params=params)
    r.raise_for_status()
    return r.json()


def _admin_headers(admin_token: str) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {admin_token}",
        "Content-Type": "application/json",
    }


def _get_admin_token() -> str | None:
    logger.info("Requesting Keycloak admin token from %s", token_endpoint)
    token_data = {
        "client_id": "admin-cli",
        "username": admin_username,
        "password": admin_password,
        "grant_type": "password",
    }
    try:
        response = requests.post(token_endpoint, data=token_data, verify=False, timeout=REQUEST_TIMEOUT_SECONDS)
        response.raise_for_status()
        return response.json().get("access_token")
    except requests.exceptions.RequestException as error:
        logger.error("Failed to retrieve admin token: %s", error)
        return None


def _get_client_by_client_id(token, realm, client_id):
    clients = kc_get(
        f"{BASE}/admin/realms/{realm}/clients",
        token,
        params={"clientId": client_id},
    )
    if not clients:
        raise RuntimeError(f"Client not found: {client_id}")
    return clients[0]


def _create_client(admin_token: str, client_name: str):
    payload = {
        "clientId": client_name,
        "name": client_name,
        "enabled": True,
        "protocol": "openid-connect",
        "publicClient": False,
        "serviceAccountsEnabled": True,
        "standardFlowEnabled": False,
        "directAccessGrantsEnabled": False,
        "fullScopeAllowed": True,  # dev-friendly; tighten in production
    }
    try:
        logger.info("Created client %s", client_name)
        kc_post(f"{BASE}/admin/realms/{TARGET_REALM}/clients", admin_token, json=payload)
        client = _get_client_by_client_id(admin_token, TARGET_REALM, client_name)
        logger.info("Client '%s' created successfully", client["id"])
        return client

    except requests.exceptions.HTTPError as error:
        if error.response is not None and error.response.status_code == 409:
            logger.info("Client %s already exists. Reusing.", client_name)
            return None
        logger.error("Failed creating client %s: %s", client_name, error)
        return None
    except requests.exceptions.RequestException as error:
        logger.error("Failed creating client %s: %s", client_name, error)
        return None


def _get_client_secret(token, realm, client_uuid):
    secret = kc_get(
        f"{BASE}/admin/realms/{realm}/clients/{client_uuid}/client-secret",
        token,
    )
    return secret["value"]


def _get_service_account_user(token, realm, client_uuid):
    return kc_get(
        f"{BASE}/admin/realms/{TARGET_REALM}/clients"
        f"{BASE}/admin/realms/{realm}/clients/{client_uuid}/service-account-user",
        token,
    )


def provision_clients(
    num_clients_to_gen: int = DEFAULT_NUM_CLIENTS,
    start_id: int = 1,
    credentials_file_path: Path | None = None,
) -> list[dict[str, str]]:
    admin_token = _get_admin_token()
    if not admin_token:
        raise ConnectionError("Cannot proceed without a valid admin token.")

    credentials: list[dict[str, str]] = []
    if credentials_file_path is None:
        credentials_file_path = DEFAULT_CREDENTIALS_FILE.format(batch_name=f"start{start_id}_count{num_clients_to_gen}")
    else:
        credentials = load_credentials(credentials_file_path)

    for client_num in range(start_id, start_id + num_clients_to_gen):
        client_id = f"ws-client_{client_num:03}"
        pocc_id = f"EAN{client_num:03}"

        service_client = _create_client(admin_token, client_id)
        if not service_client:
            continue
        service_client_uuid = service_client["id"]

        client_secret = _get_client_secret(admin_token, TARGET_REALM, service_client_uuid)
        if not client_secret:
            continue
        credentials.append(
            {
                "client_id": client_id,
                "client_secret": client_secret,
                "service_client_uuid": service_client_uuid,
                "pocc_id": pocc_id,
            }
        )

    if not credentials:
        logger.warning("No client credentials were provisioned.")
        return []

    logger.info("Saving %s provisioned credentials to %s", len(credentials), credentials_file_path)
    save_credentials(credentials_file_path, credentials)
    return credentials
