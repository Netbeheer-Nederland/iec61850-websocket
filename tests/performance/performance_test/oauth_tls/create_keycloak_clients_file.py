import asyncio
from kc_client_gen import generate_clients
from oauth_controller import authenticate_clients

NUM_CLIENTS_IN_BATCH = 300
CLIENT_START_ID = 1
CREDENTIALS_FILE = "../../client_credentials/client_credentials_250_2.json"

async def main():
    client_end_id = CLIENT_START_ID + NUM_CLIENTS_IN_BATCH - 1
    print(f"--- Starting Client Runner Batch 1 (Clients cp{CLIENT_START_ID} to cp{client_end_id}) ---")

    print("\nSTEP 1: Provisioning clients in Keycloak and saving credentials...")
    try:
        # Note: If clients already exist from a previous run, this will skip creation
        generate_clients(
            num_clients_to_gen=NUM_CLIENTS_IN_BATCH,
            start_id=CLIENT_START_ID,
            credentials_file_path=CREDENTIALS_FILE
        )
    except ConnectionError as e:
        print(f"CRITICAL ERROR in Step 1 (Client Generation): {e}. Cannot proceed.")
        return
    except Exception as e:
        print(f"Unexpected error during client generation: {e}")
        return

    print("-" * 40)

    print("STEP 2: Authenticating clients and retrieving live access tokens...")
    authenticated_clients_batch = authenticate_clients(CREDENTIALS_FILE)

    if not authenticated_clients_batch:
        print("ERROR: No clients were authenticated. Exiting runner.")
        return

    print(f"Step 2 Complete: Retrieved tokens for {len(authenticated_clients_batch)} clients.")
    print("-" * 40)

if __name__ == "__main__":
    try:
        asyncio.run(main())
    except Exception as e:
        print(f"Critical error in main runner: {e}")






