The scripts in this folder have been used to perform testcase "RTI2-FT1". 
*To perform the test, run ws_server.py and ws_client.py.
*To run the negative test case 1, only run ws_client.py. 
*To run negative test case 2, run instances ws_server_n2.py and ws_client_n2.py.
*To run negative test case 3, run instances ws_server_n3.py and ws_client_n3.py.
*To run negative test case 4, change "cp1" to "cp2" in line 37 of ws_client.py:
	iec61850_server_1 = IEC61850Server(ied1, "cp2")