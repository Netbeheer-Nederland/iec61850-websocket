# FT3: Fetch the RTI data model from the Connected Party endpoint

The following negative test case variations can be considered (Optional):

- Send a GetLogicalDeviceDirectory request with an ldName parameter value of a non-existing logical device- Send a
                                                                                                            GetLogicalNodeDirectoy
                                                                                                            request with
                                                                                                            a lnName
                                                                                                            parameter
                                                                                                            value of a
                                                                                                            non-existing
                                                                                                            logical node

**Conclusions:**

- The WebSocket server (SO Endpoint) discovers the complete Data model from the WebSocket Client (Connected Party
  Endpoint) using the following services: GetServerDirectory, GetLogicalDeviceDirectory, GetLogicalNodeDirectory,
  GetDataDirectory, GetDataDefinition, GetDataSetDirectory.
- The expected LD names, LN names, DO names, dataset names, BRCB names and URCB names are received.
- The test case **passed.**
