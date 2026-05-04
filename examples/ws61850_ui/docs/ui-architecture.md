# UI Architecture

See the design specification produced for:

- session management
- model explorer
- stream viewer
- point detail
- scenario runner
- diagnostics

This scaffold implements the baseline project structure and extension points for those features.

```mermaid
flowchart TB
    subgraph SO["RTI-SO"]
        SOA["ws_server + iec_client"]
        SOB["Port 9100"]
        SOC["Accepts connections from RTI-FSP / BFF client-server target"]
    end

    subgraph FSP["RTI-FSP"]
        FSPA["ws_client + iec_server"]
        FSPB["Dials to RTI-SO"]
        FSPC["Serves IEC 61850 data model"]
    end

    subgraph BFF["RTI-BFF"]
        BFFA["Flask REST API"]
        BFFB["Port 8000 (REST)"]
        BFFC["Port 9000 (WebSocket server)"]
        BFFD["rti-so target: ws_server + iec_client"]
        BFFE["RTI-FSP can connect here"]
        BFFF["rti-fsp target: ws_client + iec_server"]
        BFFG["Dials to RTI-SO:9100"]
    end

    subgraph UI["UI"]
        UIA["React SPA + Nginx"]
        UIB["Port 80"]
    end

    FSP -->|" WebSocket dial-in "| SO
    UI -->|" /api/ "| BFF
    FSP -.->|" Optional WebSocket connect "| BFF
    BFF -->|" Outbound WebSocket to 9100 "| SO
```

```mermaid
flowchart TB
    SO["RTI-SO<br/>ws_server + iec_client<br/>Port 9100"]
    FSP["RTI-FSP<br/>ws_client + iec_server<br/>Serves IEC 61850 application functions"]
    BFF["RTI-BFF<br/>Flask REST API<br/>Port 8000 (REST)<br/>Port 9000 (WebSocket server)"]
    UI["UI<br/>React SPA + Nginx<br/>Port 80"]
    FSP -->|" WebSocket "| SO
    UI -->|" /api/ "| BFF
    FSP -.->|" Can also connect "| BFF
    BFF -->|" Dials to RTI-SO:9100 "| SO
```

```mermaid
sequenceDiagram
    participant UI as UI (React SPA + Nginx :80)
    participant BFF as RTI-BFF (REST :8000 / WS :9000)
    participant SO as RTI-SO (ws_server + iec_client :9100)
    participant FSP as RTI-FSP (ws_client + iec_server)
    UI ->> BFF: REST calls via /api/
    FSP ->> SO: WebSocket dial-in
    FSP -->> BFF: Optional WebSocket connection to :9000
    BFF ->> SO: Outbound WebSocket to RTI-SO:9100
```

```mermaid
        C4Context
    title System Context diagram for Internet Banking System
    Enterprise_Boundary(b0, "RTI") {
        Person(demoUser, "Demo User", "A demon user.")
        System(RTI-System, "RTI", "Allows .")

        Enterprise_Boundary(b1, "RTI Demo Setup") {
            Person(roleFSP, "Flexibility Service Provider", ".")
            Person(roleSO, "System Operator", ".")

            System_Boundary(b2, "") {
                System(SystemA, "RTI-FSP", "ws_client+iec_server")
                System(SystemB, "RTI-SO", "(ws_server+iec_client)")
            }
        }
    }

    BiRel(SystemA, SystemB, "Uses")
    Rel(roleFSP, SystemA, "Uses")
    Rel(roleSO, SystemB, "Uses")
```