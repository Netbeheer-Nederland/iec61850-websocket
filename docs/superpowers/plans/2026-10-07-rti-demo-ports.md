<!--
SPDX-FileCopyrightText: 2026 Netbeheer Nederland

SPDX-License-Identifier: Apache-2.0
-->

# rti-demo Port Change Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Move the rti-demo's default ports to HMI 8080, BFF 3000, SO 5000 and IO 9000 (FSP stays 5001 / 5005), in
code, Docker, `launch.py`, tests and docs, and keep them from drifting apart again.

**Architecture:** Every default lives in a handful of places (code `os.getenv("PORT", ...)` defaults, Dockerfile
`ARG APP_PORT`, `docker-compose.yml` ports and `rti.port` labels, `launch.py` `SERVICES`, the HMI's `src/config.js`,
Vite and nginx). One new unit test reads all of them and asserts the agreed table, so the change is test-driven and
any later drift fails CI. The BFF moves off 5000 first (Task 2), then the SO takes 5000 (Task 3), then the HMI
(Task 4); Keycloak moves off the HMI's new port (Task 5) and the IO server gets one port everywhere (Task 6).

**Tech Stack:** Python 3.13 (FastAPI, pytest, PyYAML), React/Vite (vitest), Docker Compose, nginx, Keycloak.

**Spec:** the request "change port HMI: 8080, BFF: 3000, SO: 5000" (2026-10-07). No separate spec document.

## Global Constraints

- Ports: HMI `8080` (host; Vite dev server and Docker), BFF `3000`, SO `5000` (REST), SO WebSocket stays `8765`,
  FSP `5001` / second FSP `5005`, IO `9000` (direct run, `launch.py` and Docker alike).
- Docs must not link to or defer to the iec61850-websocket-demo repository.
- Every new file carries an SPDX header (`uvx reuse lint` must stay clean).
- Fixed fake ports in unit-test fixtures (e.g. `rti-so:5002`, `bff.local:5000`) are test data, not defaults: leave
  them unless a test asserts a *default*.

## Decision to confirm before Task 5

- **D1 - Keycloak (recommended: move its HTTP port to 8081, inside and outside the container).** Keycloak publishes
  `8080` on the host today, the same port the HMI gets. Only remapping the host port (`8081:8080`) would give the
  host and the containers different token issuers (`KC_HOSTNAME: localhost` builds the issuer from the request's
  port), breaking the SO's issuer check. Moving Keycloak's HTTP listener to 8081 (`KC_HTTP_PORT=8081`, `8081:8081`)
  keeps one issuer, `http://localhost:8081/realms/iec61850-test`, exactly like today's setup on 8080.
- **IO (decided 2026-10-07): 9000 everywhere.** Today it is 8080 when `main.py` runs directly and 8000 under
  `launch.py` and Docker; both values collide or confuse (8080 is the HMI's new port).

## Review Focus

1. A browser that saved `bffPort: 5000` on the HMI's Settings page now reaches the SO, not the BFF - expect the
   upgrade note in the rti-demo README and HMI README to say how to fix it (Task 7).
2. An existing `bff-config` volume still holds the seeded SO connection on port 5002 - the seed is only copied on
   first start; expect the README to give the reset/edit step (Task 7).
3. Keycloak issuer: a token fetched from the host and one fetched by a container must carry the same `iss`
   (Task 5, Step 4 checks both).
4. Port drift: one file updated and another forgotten (compose label vs Dockerfile vs code default) - the
   consistency test (Task 1) pins every source.
5. The SO's own code default was `5003` while Docker and `launch.py` said `5002` - after Task 3 a plain
   `uv run --package so python -m so.bff_endpoint` must listen on 5000 (consistency test covers the code default).

---

### Task 1: Port consistency test (fails until Tasks 2-4 are done)

**Files:**
- Create: `tests/unit/test_rti_demo_ports.py`

**Interfaces:**
- Produces: `EXPECTED_PORTS = {"hmi": 8080, "bff": 3000, "so": 5000, "fsp": 5001, "fsp2": 5005, "io": 9000}` and one test per
  source; later tasks run this file to see which sources are still wrong.

- [ ] **Step 1: Write the test**

```python
# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The rti-demo's default ports, read from every place that sets one.

One table; each source - code defaults, Dockerfiles, docker-compose.yml,
launch.py, the HMI's Vite/nginx/config.js and the seed connections - must
agree with it, so a port can't be changed in one place and forgotten in
another.
"""

import json
import re
from pathlib import Path

import pytest
import yaml

ROOT = Path(__file__).resolve().parents[2]
DEMO = ROOT / "examples" / "rti-demo"
MODULES = DEMO / "modules"

EXPECTED_PORTS = {
    "hmi": 8080,
    "bff": 3000,
    "so": 5000,
    "fsp": 5001,
    "fsp2": 5005,
    "io": 9000,
}


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _one(pattern: str, text: str, where: str) -> int:
    matches = re.findall(pattern, text)
    assert len(matches) >= 1, f"{where}: no match for {pattern!r}"
    assert len(set(matches)) == 1, f"{where}: conflicting values {matches}"
    return int(matches[0])


@pytest.fixture(scope="module")
def compose():
    return yaml.safe_load(_read(DEMO / "docker-compose.yml"))["services"]


@pytest.mark.parametrize(
    ("service", "role"),
    [
        ("rti-bff", "bff"),
        ("rti-so", "so"),
        ("rti-fsp01", "fsp"),
        ("rti-fsp02", "fsp2"),
        ("rti-io", "io"),
    ],
)
def test_compose_publishes_and_labels_the_port(compose, service, role):
    port = EXPECTED_PORTS[role]
    svc = compose[service]
    assert f"{port}:{port}" in svc["ports"]
    assert f"rti.port={port}" in svc["labels"]


def test_compose_publishes_the_hmi_on_8080(compose):
    assert compose["rti-hmi"]["ports"] == [f"{EXPECTED_PORTS['hmi']}:80"]


@pytest.mark.parametrize("service", ["rti-fsp01", "rti-fsp02"])
def test_compose_points_the_fsps_at_the_io_port(compose, service):
    assert (
        f"IO_URL=http://rti-io:{EXPECTED_PORTS['io']}"
        in compose[service]["environment"]
    )


@pytest.mark.parametrize(
    ("module", "role"), [("bff", "bff"), ("so", "so"), ("fsp", "fsp")]
)
def test_dockerfile_default_port(module, role):
    text = _read(MODULES / module / "docker" / "Dockerfile")
    assert (
        _one(r"ARG APP_PORT=(\d+)", text, f"{module} Dockerfile ARG")
        == EXPECTED_PORTS[role]
    )
    assert (
        _one(r"EXPOSE (\d+)", text, f"{module} Dockerfile EXPOSE")
        == EXPECTED_PORTS[role]
    )


def test_io_dockerfile_port_and_health_check():
    text = _read(MODULES / "io" / "docker" / "Dockerfile")
    assert _one(r"PORT=(\d+)", text, "io Dockerfile ENV") == EXPECTED_PORTS["io"]
    assert _one(r"EXPOSE (\d+)", text, "io Dockerfile EXPOSE") == EXPECTED_PORTS["io"]
    # The health check follows $PORT instead of repeating the number.
    assert "http://localhost:$PORT/api/io/health" in text


@pytest.mark.parametrize(
    ("path", "role"),
    [
        ("bff/src/bff/bff_server.py", "bff"),
        ("so/src/so/bff_endpoint.py", "so"),
        ("fsp/src/fsp/bff_endpoint.py", "fsp"),
        ("io/io_api_server/main.py", "io"),
        ("io/io_api_server/api_endpoint.py", "io"),
    ],
)
def test_code_default_port(path, role):
    text = _read(MODULES / path)
    assert _one(r'os\.getenv\("PORT", "(\d+)"\)', text, path) == EXPECTED_PORTS[role]


@pytest.mark.parametrize(
    "path", ["so/src/so/bff_endpoint.py", "fsp/src/fsp/bff_endpoint.py"]
)
def test_io_server_url_default(path):
    text = _read(MODULES / path)
    pattern = r'os\.getenv\("IO_SERVER_URL", "http://localhost:(\d+)"\)'
    assert _one(pattern, text, path) == EXPECTED_PORTS["io"]


@pytest.mark.parametrize(
    "path",
    ["io/io_client/async_client_io.py", "io/io_client/io_router.py"],
)
def test_io_client_default_base_url(path):
    text = _read(MODULES / path)
    assert _one(r'"http://localhost:(\d+)"', text, path) == EXPECTED_PORTS["io"]


def test_launch_py_default_ports():
    text = _read(DEMO / "launch.py")
    roles = (
        ("bff", "BFF"),
        ("so", "SO"),
        ("fsp", "FSP"),
        ("fsp2", "FSP2"),
        ("io", "IO"),
    )
    for role, enum in roles:
        block = re.search(
            rf"ServiceType\.{enum}: ServiceConfig\((.*?)\n    \),", text, re.S
        )
        assert block, f"launch.py: no ServiceConfig for {enum}"
        port = EXPECTED_PORTS[role]
        assert f"default_port={port}," in block.group(1), enum
        assert f'"PORT": "{port}"' in block.group(1), enum
        assert f'"rti.port": "{port}"' in block.group(1), enum


def test_hmi_dev_server_port():
    text = _read(MODULES / "hmi" / "vite.config.js")
    assert _one(r"port:\s*(\d+)", text, "vite.config.js") == EXPECTED_PORTS["hmi"]


def test_hmi_default_bff_port():
    text = _read(MODULES / "hmi" / "src" / "config.js")
    assert (
        _one(r"VITE_BFF_PORT \|\| '(\d+)'", text, "hmi config.js")
        == EXPECTED_PORTS["bff"]
    )


def test_hmi_nginx_proxies_to_the_bff_port():
    text = _read(MODULES / "hmi" / "nginx.conf")
    assert (
        _one(r"proxy_pass http://rti-bff:(\d+);", text, "nginx.conf")
        == EXPECTED_PORTS["bff"]
    )


def test_playbook_default_bff():
    text = _read(MODULES / "bff" / "src" / "bff" / "playbook.py")
    assert (
        _one(r'DEFAULT_BFF = "http://localhost:(\d+)"', text, "playbook.py")
        == EXPECTED_PORTS["bff"]
    )


def test_seed_connections_use_the_service_ports():
    seed = json.loads(_read(MODULES / "bff" / "src" / "bff" / "connections.json"))
    ports = {c["name"]: c["port"] for c in seed}
    assert ports == {
        "SO": EXPECTED_PORTS["so"],
        "FSP01": EXPECTED_PORTS["fsp"],
        "FSP02": EXPECTED_PORTS["fsp2"],
    }
```

- [ ] **Step 2: Run it and record what fails**

Run: `uv run pytest tests/unit/test_rti_demo_ports.py -q`
Expected: 23 FAILED (BFF, SO, HMI and IO in compose, Dockerfiles, code defaults, launch.py, Vite, config.js, nginx,
playbook, seed, the FSP/SO `IO_SERVER_URL` and IO client defaults) and 4 PASSED (the FSP sources). Verified against
the code on 2026-10-07.

- [ ] **Step 3: Don't commit yet** - CI runs `tests/unit`, so the test is committed with Task 4, once it passes.

---

### Task 2: BFF on 3000

**Files:**
- Modify: `examples/rti-demo/modules/bff/src/bff/bff_server.py:1420` and `:1935` (`os.getenv("PORT", "5000")` -> `"3000"`)
- Modify: `examples/rti-demo/modules/bff/src/bff/playbook.py:42` (`DEFAULT_BFF = "http://localhost:3000"`)
- Modify: `examples/rti-demo/modules/bff/docker/Dockerfile:52` (`ARG APP_PORT=3000`) and `:78` (`EXPOSE 3000`)
- Modify: `examples/rti-demo/docker-compose.yml` rti-bff: `"3000:3000"`, label `rti.port=3000`; the HMI comment
  "else localhost:5000" -> "localhost:3000"
- Modify: `examples/rti-demo/launch.py` BFF `ServiceConfig` (`default_port=3000`, `"PORT": "3000"`,
  `"rti.port": "3000"`), the usage line `bff: ... (default: port 3000)` and the help example
  "Launch BFF server on port 3000"
- Modify: `examples/rti-demo/config/launch_config.json.example` BFF `port` / `rti.port` -> 3000
- Modify: `examples/rti-demo/modules/hmi/src/config.js` (`'5000'` -> `'3000'`, doc comment `localhost:3000`)
- Modify: `examples/rti-demo/modules/hmi/src/config.test.js` (expectation `'3000'`, test name `localhost:3000`)
- Modify: `examples/rti-demo/modules/hmi/nginx.conf` (`proxy_pass http://rti-bff:3000;`)
- Modify: HMI default props `bffBaseUrl = 'http://localhost:5000'` in `src/components/OAuthConfigModal.jsx:78`,
  `src/components/TLSConfigModal.jsx:136`, `src/pages/ACSIClient.jsx:38` -> use the shared default:
  `` bffBaseUrl = `http://${DEFAULT_BFF_HOST}:${DEFAULT_BFF_PORT}` `` with
  `import { DEFAULT_BFF_HOST, DEFAULT_BFF_PORT } from '../config';`
- Modify: `examples/rti-demo/playbooks/demo.yaml:14` (`bff: http://localhost:3000`)
- Modify: `examples/rti-demo/tests/integration/test_bff_connections.py:20,42` and
  `test_bff_live_push.py:54` (`localhost:3000`)

**Interfaces:**
- Consumes: `EXPECTED_PORTS["bff"] == 3000` (Task 1)
- Produces: the BFF on `http://localhost:3000` (REST, `/ws`, `/docs`); `DEFAULT_BFF_PORT == '3000'` in the HMI

- [ ] **Step 1: Make the edits listed above**

Use exact replacements, e.g.:

```bash
sed -i 's/os.getenv("PORT", "5000")/os.getenv("PORT", "3000")/' examples/rti-demo/modules/bff/src/bff/bff_server.py
sed -i 's#DEFAULT_BFF = "http://localhost:5000"#DEFAULT_BFF = "http://localhost:3000"#' examples/rti-demo/modules/bff/src/bff/playbook.py
sed -i 's/^ARG APP_PORT=5000$/ARG APP_PORT=3000/; s/^EXPOSE 5000$/EXPOSE 3000/' examples/rti-demo/modules/bff/docker/Dockerfile
sed -i 's#proxy_pass http://rti-bff:5000;#proxy_pass http://rti-bff:3000;#' examples/rti-demo/modules/hmi/nginx.conf
sed -i 's#^bff: http://localhost:5000#bff: http://localhost:3000#' examples/rti-demo/playbooks/demo.yaml
```

Edit `docker-compose.yml`, `launch.py`, `launch_config.json.example`, `config.js`, `config.test.js`, the three HMI
default props and the integration tests by hand (each has comments or structure a blind `sed` would damage).

- [ ] **Step 2: Run the BFF-related checks**

Run: `uv run pytest tests/unit/test_rti_demo_ports.py -q -k "bff or playbook or nginx or default_bff"`
Expected: those PASS; SO and HMI-port tests still FAIL.

Run: `uv run --package bff pytest examples/rti-demo/modules/bff/tests -q` - Expected: all pass.
Run: `cd examples/rti-demo/modules/hmi && npm test` - Expected: all pass (config.test.js now expects 3000).
Run: `uv run pytest examples/rti-demo/tests/test_playbook.py -q` - Expected: pass.

- [ ] **Step 3: Commit**

```bash
git add examples/rti-demo/modules/bff examples/rti-demo/modules/hmi examples/rti-demo/docker-compose.yml \
  examples/rti-demo/launch.py examples/rti-demo/config/launch_config.json.example \
  examples/rti-demo/playbooks/demo.yaml examples/rti-demo/tests/integration
git commit -m "rti-demo: BFF on port 3000"
```

---

### Task 3: SO on 5000

**Files:**
- Modify: `examples/rti-demo/modules/so/src/so/bff_endpoint.py:213` and `:4887` (`os.getenv("PORT", "5003")` -> `"5000"`)
- Modify: `examples/rti-demo/modules/so/src/so/bff_endpoint.py:1366,1368` (`acsi_url` default and example
  `http://localhost:5000`)
- Modify: `examples/rti-demo/modules/so/docker/Dockerfile:48` (`ARG APP_PORT=5000`), `:74` (`EXPOSE 5000`)
- Modify: `examples/rti-demo/docker-compose.yml` rti-so: `"5000:5000"` (keep `"8765:8765"`), label `rti.port=5000`
- Modify: `examples/rti-demo/launch.py` SO `ServiceConfig` (`default_port=5000`, `"PORT": "5000"`,
  `"rti.port": "5000"`) and the usage line `so: RTI-SO (default: port 5000)`
- Modify: `examples/rti-demo/config/launch_config.json.example` SO block -> 5000
- Modify: `examples/rti-demo/modules/bff/src/bff/connections.json` (SO `"port": 5000`)
- Modify: `examples/rti-demo/modules/so/src/so/bff_endpoint.py:4004` - `GET /api/health` reports a hardcoded
  `"port": 8080`, never the SO's port; report the real one:
  `"server": {"status": "ok", "host": "localhost", "port": int(os.getenv("PORT", "5000"))},`
- Leave: `examples/rti-demo/modules/hmi/src/pages/Connections.jsx:34` (`port: 5000` is the new-instance form's
  default instance port - it now matches the SO; update its comment to say so)

**Interfaces:**
- Consumes: BFF no longer on 5000 (Task 2)
- Produces: SO REST on `http://localhost:5000`, WebSocket on 8765 unchanged

- [ ] **Step 1: Make the edits**

```bash
sed -i 's/os.getenv("PORT", "5003")/os.getenv("PORT", "5000")/' examples/rti-demo/modules/so/src/so/bff_endpoint.py
sed -i 's#"http://localhost:5002"#"http://localhost:5000"#g' examples/rti-demo/modules/so/src/so/bff_endpoint.py
sed -i 's/^ARG APP_PORT=5002$/ARG APP_PORT=5000/; s/^EXPOSE 5002$/EXPOSE 5000/' examples/rti-demo/modules/so/docker/Dockerfile
```

Edit compose, `launch.py`, `launch_config.json.example`, the seed and the `Connections.jsx` comment by hand.

- [ ] **Step 2: Run the checks**

Run: `uv run pytest tests/unit/test_rti_demo_ports.py -q -k "so or seed"` - Expected: PASS, except
`test_io_server_url_default[so/...]` (Task 6).
Run: `uv run --package so pytest examples/rti-demo/modules/so/tests -q` - Expected: all pass.
Run: `uv run --package bff pytest examples/rti-demo/modules/bff/tests -q` - Expected: all pass (seed change).

- [ ] **Step 3: Commit**

```bash
git add examples/rti-demo/modules/so examples/rti-demo/modules/bff/src/bff/connections.json \
  examples/rti-demo/modules/hmi/src/pages/Connections.jsx examples/rti-demo/docker-compose.yml \
  examples/rti-demo/launch.py examples/rti-demo/config/launch_config.json.example
git commit -m "rti-demo: SO on port 5000"
```

---

### Task 4: HMI on 8080

**Files:**
- Modify: `examples/rti-demo/modules/hmi/vite.config.js:26` (`port: 8080`)
- Modify: `examples/rti-demo/docker-compose.yml` rti-hmi ports `"8080:80"`
- Commit: `tests/unit/test_rti_demo_ports.py` (Task 1) - now fully green

- [ ] **Step 1: Edit**

```bash
sed -i 's/^    port: 3000,$/    port: 8080,/' examples/rti-demo/modules/hmi/vite.config.js
```

In compose change `- "3001:80"` to `- "8080:80"`.

- [ ] **Step 2: Run the whole consistency test**

Run: `uv run pytest tests/unit/test_rti_demo_ports.py -q`
Expected: all PASS.
Run: `uv run pytest tests/unit -q` - Expected: all pass.

- [ ] **Step 3: Commit**

```bash
git add examples/rti-demo/modules/hmi/vite.config.js examples/rti-demo/docker-compose.yml tests/unit/test_rti_demo_ports.py
git commit -m "rti-demo: HMI on port 8080; test that every source agrees on the ports"
```

---

### Task 5: Keycloak HTTP on 8081 (decision D1)

**Files:**
- Modify: `scripts/keycloak/docker-compose.yml` (ports `"8081:8081"`, keep `"8443:8443"`; environment
  `KC_HTTP_PORT: 8081`)
- Modify: `scripts/keycloak/README.md` (every `localhost:8080` -> `localhost:8081`, "exposed on the local port 8081")
- Modify: `tests/performance/FT23/client_credentials/utils/keycloak_client_provisioner.py:43`
  (`KEYCLOAK_URL` default `http://localhost:8081`)
- Modify: `tests/performance/FT23/FT23-using-oauth-20-tls.md`, `tests/security/FT31/FT31-...md` ("exposes HTTP on `8081`",
  admin API URL)
- Modify: `examples/rti-demo/README.md` Keycloak section (admin console, `http://keycloak:8081`, issuer
  `http://localhost:8081/realms/iec61850-test`, the HMI settings table) and the Services table row
  `keycloak (Docker only) | 8081 / 8443`

- [ ] **Step 1: Edit the files above**

- [ ] **Step 2: Start Keycloak and check one issuer for host and container**

```bash
docker network create rti-network 2>/dev/null || true
cd scripts/keycloak && docker compose up -d && sleep 40
curl -s http://localhost:8081/realms/iec61850-test/.well-known/openid-configuration | python3 -c "import sys,json;print(json.load(sys.stdin)['issuer'])"
docker run --rm --network rti-network curlimages/curl -s http://keycloak:8081/realms/iec61850-test/.well-known/openid-configuration | python3 -c "import sys,json;print(json.load(sys.stdin)['issuer'])"
```

Expected: both print `http://localhost:8081/realms/iec61850-test`. If they differ, set `KC_HOSTNAME` to
`http://localhost:8081` (full URL) and repeat.

- [ ] **Step 3: Stop Keycloak and commit**

```bash
docker compose down
git add scripts/keycloak tests/performance/FT23 tests/security/FT31 examples/rti-demo/README.md
git commit -m "keycloak: HTTP on 8081, freeing 8080 for the HMI"
```

---

### Task 6: IO on 9000

**Files:**
- Modify: `examples/rti-demo/modules/io/io_api_server/main.py:239` and `io_api_server/api_endpoint.py:1547`
  (`os.getenv("PORT", "8080")` -> `"9000"`; delete the "On Windows, port 8000 might be reserved, so we use 8080"
  comment above each); `main.py` docstring: "Run with default port (9000)", custom-port example `PORT=9100`
- Modify: `examples/rti-demo/modules/io/io_client/async_client_io.py` (every `http://localhost:8080` -> `9000`:
  the `base_url` defaults at lines 159, 933, 1704 and the docstring examples at 31, 152, 926, 1696)
- Modify: `examples/rti-demo/modules/io/io_client/io_router.py:89,91` (default `http://localhost:9000`, example
  `http://rti-io:9000`)
- Modify: `examples/rti-demo/modules/io/io_api_server/test_imports.py:132-133` (`port 9000`, `http://localhost:9000/docs`)
- Modify: `examples/rti-demo/modules/io/docker/Dockerfile:51` (`PORT=9000`), `:98` (`EXPOSE 9000`), `:101`
  (health check `curl -f http://localhost:$PORT/api/io/health`)
- Modify: `examples/rti-demo/docker-compose.yml` rti-io `"9000:9000"`, label `rti.port=9000`; rti-fsp01 and
  rti-fsp02 `IO_URL=http://rti-io:9000`
- Modify: `examples/rti-demo/launch.py` IO `ServiceConfig` (`default_port=9000`, `"PORT": "9000"`,
  `"rti.port": "9000"`) and the usage line `io: IO Device Control API (default: port 9000)`
- Modify: `examples/rti-demo/modules/fsp/src/fsp/bff_endpoint.py:354,640,1188` and
  `examples/rti-demo/modules/so/src/so/bff_endpoint.py:351,629,1363` (`IO_SERVER_URL` default, docstring and
  example -> `http://localhost:9000`)
- Docs: `modules/io/README.md` (`PORT` row: default 9000, one port everywhere; Swagger `http://localhost:9000/docs`;
  debug `curl` lines), `modules/io/io_client/README_IO.md` (all IO URLs -> 9000, drop the "8080 when run directly /
  8000 under Docker" notes), `modules/fsp/README.md` and `modules/so/README.md` (IO Client Integration example and
  the `IO_SERVER_URL` row -> 9000), `examples/rti-demo/README.md` (`io` row `9000`, IO URL, *IO API Server*
  commands - one port now), `docs/rti-demo/RTI_DEMO.adoc` (three IO rows -> 9000)

**Interfaces:**
- Produces: IO REST on `http://localhost:9000` in every way of running it; FSP/SO reach it at `IO_URL` /
  `IO_SERVER_URL` = `http://rti-io:9000` (Docker) or `http://localhost:9000` (local)

- [ ] **Step 1: Make the edits**

```bash
cd examples/rti-demo/modules
sed -i 's/os.getenv("PORT", "8080")/os.getenv("PORT", "9000")/' io/io_api_server/main.py io/io_api_server/api_endpoint.py
sed -i '/On Windows, port 8000 might be reserved, so we use 8080 as default/d' io/io_api_server/main.py io/io_api_server/api_endpoint.py
sed -i 's#http://localhost:8080#http://localhost:9000#g' io/io_client/async_client_io.py io/io_client/io_router.py io/io_api_server/test_imports.py
sed -i 's#http://demo-io:8080#http://rti-io:9000#; s/(default port 8080)/(default port 9000)/' io/io_client/io_router.py io/io_api_server/test_imports.py
sed -i 's#http://localhost:8000#http://localhost:9000#g' fsp/src/fsp/bff_endpoint.py so/src/so/bff_endpoint.py
sed -i 's/^    PORT=8000 \\$/    PORT=9000 \\/; s/^EXPOSE 8000$/EXPOSE 9000/; s#curl -f http://localhost:8000/api/io/health#curl -f http://localhost:$PORT/api/io/health#' io/docker/Dockerfile
cd ../../..
```

Edit `main.py`'s docstring, `docker-compose.yml`, `launch.py` and the docs by hand.

- [ ] **Step 2: Check no IO 8000/8080 default is left**

```bash
git grep -n -E "8000|8080" -- 'examples/rti-demo/modules/io/*.py' examples/rti-demo/modules/io/docker \
  'examples/rti-demo/modules/fsp/src/*.py' 'examples/rti-demo/modules/so/src/*.py'
```

Expected: no matches. (Task 3 already fixed the SO health response's hardcoded `"port": 8080`.)

- [ ] **Step 3: Run the checks**

Run: `uv run pytest tests/unit/test_rti_demo_ports.py -q -k io` - Expected: PASS.
Run: `for m in fsp so; do uv run --package $m pytest examples/rti-demo/modules/$m/tests -q; done` - Expected: pass.
Run: `docker build -q -t io-port-check examples/rti-demo/modules/io -f examples/rti-demo/modules/io/docker/Dockerfile && docker run --rm -d --name io-port-check io-port-check && sleep 25 && docker inspect -f '{{.State.Health.Status}}' io-port-check; docker rm -f io-port-check; docker rmi io-port-check`
Expected: `healthy` (the health check now follows `PORT=9000`; without Pi hardware the IO server runs in mock mode).

- [ ] **Step 4: Commit**

```bash
git add examples/rti-demo/modules/io examples/rti-demo/modules/fsp examples/rti-demo/modules/so \
  examples/rti-demo/docker-compose.yml examples/rti-demo/launch.py examples/rti-demo/README.md docs/rti-demo/RTI_DEMO.adoc
git commit -m "rti-demo: IO on port 9000, the same for a direct run, launch.py and Docker"
```

---

### Task 7: Docs and upgrade notes

**Files (replace the old defaults; leave fixed test-fixture ports alone):**
- `examples/rti-demo/README.md`: Services table (`bff 3000`, `so 5000, WebSocket 8765`, HMI `8080 (npm run dev and
  Docker)`), Access URLs, Docker/BFF-persistence examples, and a new "Upgrading from the old ports" subsection under
  *Docker* with:

```markdown
### Upgrading from the old ports

The defaults changed: HMI 3000/3001 -> 8080, BFF 5000 -> 3000, SO 5002 -> 5000, IO 8000/8080 -> 9000
(Keycloak HTTP 8080 -> 8081).

- A browser that saved a BFF address on the HMI's Settings page keeps it - and port 5000 is now the SO. Set the BFF
  port to 3000 there, or clear the site data.
- The BFF copies its seed connections only on first start, so an existing `bff-config` volume still has the SO on
  5002. Edit the SO connection's port to 5000 on the Connections page, or reset the volume:
  `docker compose down && docker volume rm rti-demo_bff-config && docker compose up -d`.
```

- `docs/rti-demo/RTI_DEMO.adoc`: components table (HMI 8080, BFF 3000, SO 5000), communication matrix, HTTP/REST
  table, workflow line "SO (REST 5000)"
- `examples/rti-demo/modules/bff/README.md`: "Port: 3000", compose `3000:3000`, all `curl http://localhost:3000/...`,
  "Frontend ... (port 3000)", "Backend ... (ports 5000, 5001, ...)"
- `examples/rti-demo/modules/so/README.md`: every 5002 -> 5000 (ASCII box, docker run, curl, PORT examples)
- `examples/rti-demo/modules/hmi/README.md`: dev server `http://localhost:8080`, Docker `http://localhost:8080`,
  built-in default `localhost:3000`, OpenAPI URLs (BFF 3000, SO 5000), the BFF-address example
  `HMI_BFF_PORT=3000`, the upgrade note's first bullet
- `examples/rti-demo/modules/io/io_client/README_IO.md`: SO port 5000 (IO URLs are done in Task 6)
- `examples/rti-demo/playbooks/README.md`: `--bff` default and the `bff:` example -> 3000
- `examples/rti-demo/modules/fsp/README.md:265`: troubleshooting suggests `PORT=5002` when 5001 is busy - change to
  `PORT=5011` (5002 is no longer special, but avoid suggesting a port next to the SO's old one)

- [ ] **Step 1: Edit**, then list what is left:

```bash
git grep -n -E "localhost:(5002|3001)\b|:5000/api|port 5000|5000:5000|3000:80|3001:80" -- examples docs ':!docs/archive' ':!**/node_modules/**' ':!*.test.*' ':!**/tests/**'
```

Expected: only lines that really mean the SO on 5000.

- [ ] **Step 2: Run the docs checks**

Run: `docker run --rm -v "$PWD":/input:ro -w /input lycheeverse/lychee:0.24.2 --config lychee.toml '**/*.md'`
Expected: 0 errors.
Run: `uvx reuse lint` - Expected: compliant (apart from untracked local files).

- [ ] **Step 3: Commit**

```bash
git add examples docs
git commit -m "docs: new rti-demo ports, and how to upgrade a running setup"
```

---

### Task 8: Full-stack verification

- [ ] **Step 1: Stop the old stack** (its containers hold the old ports and names):
  `cd examples/rti-demo && docker compose down`

- [ ] **Step 2: Build and start**

```bash
docker network create rti-network 2>/dev/null || true
docker compose build && docker compose up -d && sleep 40
docker compose ps --format '{{.Name}} {{.Status}} {{.Ports}}'
```

Expected: rti-hmi `0.0.0.0:8080->80`, rti-bff `3000->3000`, rti-so `5000->5000` and `8765->8765`, rti-fsp01
`5001->5001`, rti-fsp02 `5005->5005`, rti-io `9000->9000`; all `healthy` (rti-io may fail to start without the
Raspberry Pi devices it maps - then probe it with the Task 6 image check instead).

- [ ] **Step 3: Probe every port**

```bash
curl -fsS http://localhost:3000/api/health && echo BFF ok
curl -fsS http://localhost:5000/api/status && echo SO ok
curl -fsS http://localhost:5001/api/status && echo FSP ok
curl -fsS http://localhost:9000/api/io/health && echo IO ok
curl -fsS -o /dev/null http://localhost:8080/ && echo HMI ok
curl -fsS http://localhost:8080/api/health && echo "HMI -> BFF proxy ok"
```

Expected: six "ok" lines.

- [ ] **Step 4: HMI in a browser** - open `http://localhost:8080`, Settings shows BFF `localhost:3000` (clear site
  data first if an old value is saved), Overview shows the SO and both FSPs connected.

- [ ] **Step 5: Full test suites**

```bash
uv run ruff check . && uv run ruff format --check .
uv run pytest tests/unit -q
for m in bff fsp so; do uv run --package $m pytest examples/rti-demo/modules/$m/tests -q; done
(cd examples/rti-demo/modules/hmi && npm test)
uv run pytest examples/rti-demo/tests/integration -q   # needs the stack from Step 2
```

Expected: all pass.
