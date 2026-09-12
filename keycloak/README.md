To start the keycloak server, you can use the following command:

```bash
bin\kc.bat start-dev --https-certificate-file=./cert/keycloak.crt --https-certificate-key-file=./cert/keycloak.key --https-port=8443 --https-client-auth=request --verbose --https-protocols=TLSv1.2

```
This command has to be run from the following directory:

```bash
\keycloak\keycloak-26.2.4
```

Keycloak will be available at the following URL:

```bash
https://localhost:8443
http://localhost:8080
```
The used certificate is a self-signed certificate and will not be trusted by your browser. You will have to accept the risk and continue to the website.