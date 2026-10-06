<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# FT8: Verify that the Connected Party endpoint can detect a loss of connection

**Conclusions:**

- The Connected Party Endpoint can detect a loss of connection with the SO Endpoint.
- When a loss of connection happens the WebSocket connection is closed, and the Connected Party Endpoint tries to
  reconnect.
- If re-connection is successful, the WebSocket connection is re-established and functionality is normal.
- The test case **passed.**
