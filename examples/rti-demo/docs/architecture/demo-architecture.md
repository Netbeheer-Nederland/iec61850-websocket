# Architecture Demo-Setup

See the design specification produced for:

- session management
- model explorer
- stream viewer
- point detail
- scenario runner
- diagnostics

This scaffold implements the baseline project structure and extension points for those features.

## MileStone 1

The following illustration describes the first iteration (milestone 1) on the demo-set.

It contains for three docker container:

- Human Machine Interface, contains the frontend development and runs in a standard reverse proxy server.
- Backend for frontend, contains all logic to connect the frontend functionality to each of the RTI - roles (RTI-FSP)
- RTI-FSP, contains all the logic to operates the ACSI-server and the ActiveWebSocketConnector. It also provides a
  BBF-service-endpoint, where functional request are mapped to IEC 61850 protocol (services, data-model)

![img.png](img.png)

### Role mapping

| Container | WS role                               | IEC 61850 ACSI role | ws61850 class                        |
|-----------|---------------------------------------|---------------------|--------------------------------------|
| RTI-SO    | PassiveWebSocketConnector (WS server) | ACSI client         | `PassiveEndpoint` + `IEC61850Client` |
| RTI-FSP   | ActiveWebSocketConnector (WS client)  | ACSI server         | `ActiveEndpoint` + `IEC61850Server`  |

The BFF embeds the RTI-SO in the same Python process for M1. The Flask REST thread and the
asyncio event loop (RTI-SO) run concurrently; the REST endpoints surface IEC 61850 data to the
HMI.

---
