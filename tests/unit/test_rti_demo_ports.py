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
