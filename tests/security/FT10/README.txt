This test case is used for checking the functionality of FT10 module.
*To perform the test case, run ws_server.py and ws_client.py located in the same folder. Make sure that the keycloak authorization server is running.
*To perform the negative test case 1, run ws_server.py and ws_client_n1.py located in the same folder. Make sure that the keycloak authorization server is running.
*To perform the negative test case 2, run ws_server.py and ws_client_n2.py located in the same folder. Make sure that the keycloak authorization server is running.
IMPORTANT NOTE: If keycloak is running on a different host or port, please modify the url in src/EndPoint/endpoint.py and ws_client.py,
and ws_client_n1.py and ws_client_n2.py accordingly.