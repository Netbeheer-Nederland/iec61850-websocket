## FT9: Verify that the WebSocket connection can use TLS 1.2 or TLS 1.3

*To perform the test, run ws_server.py and ws_client.py.

```shell
python ws_server.py
```

```shell
python ws_client.py
```

**Conclusions:**

1. The WebSocket client verifies the identity of the WebSocket server by validating the server certificate.
1. A successful handshake is established using TLS1.2 and the WebSocket connection is secured by TLS encryption and
   message authentication.
1. A successful handshake is established using TLS1.3 and the WebSocket connection is secured by TLS encryption and
   message authentication.
1. The testcase **passed.**
