# FT10: Using OAuth 2.0 for Connected Party endpoint authentication

## Introduction / Context

This test verifies OAuth 2.0 authentication for a Connected Party (CP) WebSocket session. The WebSocket server accepts
or rejects CP connections based on access tokens issued by a Keycloak authorization server. The Keycloak realm and
client configuration used by this test are imported from the local `keycloak` directory in this test folder.

## Test Objective

Confirm that:

1. A Connected Party connection is accepted when a valid OAuth 2.0 access token is presented.
2. A Connected Party connection is rejected when an invalid access token is presented.
3. The server closes the connection when a token expires and does not receive a valid refresh token.

## Getting Started

* Keycloak exposed on the local port 8080 and created an initial admin user with the username admin
  and password admin.
* The Keycloak realm and client configuration used by this test are imported from the local `keycloak` directory in this
  test folder.
* The Keycloak Docker image is used to start the Keycloak server.
* SSL is enabled for the Keycloak server and uses a self-signed certificate located in the `testing/certs` directory.
* Run the following command to start Keycloak:

```shell
docker compose up
```

* Log in to the Admin Console, and go to the Keycloak Admin Console.
* Log in with the username and password you created earlier.

![key-cloak start screen](./images/keycloak-start-screen.png)

Or directly test a realm endpoint:

```shell
curl "http://localhost:8080/realms/iec61850-test"
```

* Get an access token for the ws-client client:

```shell
curl -X POST \
  http://localhost:8080/realms/iec61850-test/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=ws-client" \
  -d "client_secret=K4Nrd14seXG52J3xpnIqfMyILTJJu3VI"
```

Or with SSL:

```shell
curl -X POST \
  --cacert ../../../testing/certs/ca.pem \
  https://localhost:8443/realms/iec61850-test/protocol/openid-connect/token \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "grant_type=client_credentials" \
  -d "client_id=ws-client" \
  -d "client_secret=K4Nrd14seXG52J3xpnIqfMyILTJJu3VI"
```

## Test Case Design

This test case is used for checking the functionality of FT10 module.

* To perform the test case, run ws_server.py and ws_client.py located in the same folder. Make sure that the keycloak
  authorization server is running.

* To perform the negative test case 1, run ws_server.py and ws_client_n1.py located in the same folder. Make sure that
  the keycloak authorization server is running.
* To perform the negative test case 2, run ws_server.py and ws_client_n2.py located in the same folder. Make sure that
  the keycloak authorization server is running.

IMPORTANT NOTE: If keycloak is running on a different host or port, please modify the url in src/EndPoint/endpoint.py
and ws_client.py, and ws_client_n1.py and ws_client_n2.py accordingly.

The following negative test case variations can be considered (Optional):

- Verify that the server closes the WebSocket connection when the client presents an invalid access token
- Verify that the server closes the WebSocket connection when the access token expires and cannot be renewed

## Conclusions:

- OAuth 2.0 is used for authenticating the WebSocket client (connected party)
- The connection would not establish with a wrong access token.
- The connection would fail if the access token is expired and no new access token is sent .
- Three seconds before a token expires, WebSocket client sends a new token in the form of an associate message to the
  WebSocket server, and if the token is verified successfully, the connection remains open.
- The test case** passed.**

## Reference Articles

https://www.keycloak.org/getting-started/getting-started-docker
