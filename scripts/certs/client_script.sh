openssl genpkey -algorithm RSA -out client.key
openssl req -new -key client.key -out client.csr -config client_cert_conf.cnf
openssl x509 -req -in client.csr -CA root_CA1.pem -CAkey root_CA1.key -CAcreateserial -out client.crt -extfile customer_cert_conf.cnf -extensions req_ext -days 3650 -sha256