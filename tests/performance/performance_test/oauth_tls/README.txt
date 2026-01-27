The scripts in this folder have been used to perform testcase "RTI2-NT1 Performance" with OAuth and TLS.
*To automatically create the clients on keycloak run create_keycloak_clients_file.py
    -Make sure to specify the desired number of clients in 'NUM_CLIENTS_IN_BATCH' and the desired name of the file that the credentials of each client will be stored in.
    -The credentials file will be saved in ../../client_credentials
*To run the test, run ws_server.py, multiple_client_oauth_tls_b1_runner.py and multiple_client_oauth_tls_b1_runner.py
    -The testcase uses the client credential file 'client_credentials_250_1' for the multiple_client_oauth_tls_b1_runner.py script
    -The testcase uses the client credential file 'client_credentials_250_2' for the multiple_client_oauth_tls_b2_runner.py script
    -The lifespan of each access token is set to 10 minutes in keycloak
    -A new access token is requested 40 seconds before a token expires