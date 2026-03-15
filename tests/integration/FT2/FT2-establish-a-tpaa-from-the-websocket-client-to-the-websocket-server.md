## FT2: Establish a TPAA from the WebSocket client to the WebSocket server

The following negative test case variations can be considered (Optional):

- WebSocket establishment not successful because WebSocket server is unavailable- Expected: WebSocket client is
                                                                                  re-trying after a specified amount of
                                                                                  time- WebSocket establishment not
                                                                                        successful because of unknown
                                                                                        value in Sec-WebSocket-Protocol
                                                                                        header- WebSocket establishment
                                                                                                not successful because
                                                                                                of wrong value in
                                                                                                Sec-WebSocket-Protocol
                                                                                                header- WebSocket
                                                                                                        successfully
                                                                                                        established but
                                                                                                        access point
                                                                                                        cannot be found-
Expect a Reject message (ServiceError as response to the Associate request)

**Conclusions:**

- The connection establishes after the WebSocket client sends an associate request to the WebSocket server.
- The connection does NOT establish if the SO Endpoint is unavailable and the Connected Party re-tries to establish a
  connection.
- The connection does NOT establish if the value in Sec-WebSocket-Protocol header is unknown to the SO Endpoint.
- The connection does NOT establish if the value in Sec-WebSocket-Protocol header is incorrect.
- When the Access Point can’t be found, the associate response shows a service error with an “instanceNotAvailable”
  message.
- The test case **passed.**
