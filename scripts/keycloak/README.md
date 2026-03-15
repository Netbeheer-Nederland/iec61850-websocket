# Running Keycloak with Docker Compose

## Getting Started

* Keycloak exposed on the local port 8080 and created an initial 'admin' user with the username 'admin"
  and password admin (see the Keycloak docker compose file in the scripts/keycloak directory to change the default admin
  user credentials).
* The Keycloak realm and client configuration used by this test are imported from the local `keycloak` directory in this
  test folder.
* The Keycloak Docker image is used to start the Keycloak server.
* SSL is enabled for the Keycloak server and uses a self-signed certificate located in the `testing/certs` directory.
* Run the following command to start Keycloak in the scripts/keycloak directory:

```shell
docker compose up
```

* Log in to the Admin Console (http://localhost:8080), with the username and password you created earlier

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

## Reference Articles

https://www.keycloak.org/getting-started/getting-started-docker
