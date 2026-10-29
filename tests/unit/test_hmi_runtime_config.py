# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
"""The HMI container's 40-rti-config.sh: /config.js and nginx's error log.

It runs at container start and writes window.RTI_CONFIG from BFF_HOST,
BFF_PORT and LOG_LEVEL, and nginx's error log level from LOG_LEVEL
(decision 0014, spec 0008).
"""

import os
import shutil
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = (
    ROOT / "examples" / "rti-demo" / "modules" / "hmi" / "docker" / "40-rti-config.sh"
)

pytestmark = [
    pytest.mark.unit,
    pytest.mark.skipif(shutil.which("sh") is None, reason="needs a POSIX sh"),
]


def _run(tmp_path: Path, **env: str) -> tuple[str, str | None]:
    config_js = tmp_path / "config.js"
    log_conf = tmp_path / "00-rti-log-level.conf"
    subprocess.run(
        ["sh", str(SCRIPT)],
        env={
            "PATH": os.environ["PATH"],
            "RTI_CONFIG_JS": str(config_js),
            "RTI_NGINX_LOG_CONF": str(log_conf),
            **env,
        },
        check=True,
        capture_output=True,
    )
    return config_js.read_text(), log_conf.read_text() if log_conf.exists() else None


def test_nothing_set_writes_an_empty_config_and_leaves_nginx_as_it_is(tmp_path):
    config_js, log_conf = _run(tmp_path)
    assert config_js == "window.RTI_CONFIG = {  };\n"
    assert log_conf is None


def test_bff_address_and_log_level(tmp_path):
    config_js, _ = _run(
        tmp_path, BFF_HOST="192.168.100.10", BFF_PORT="3000", LOG_LEVEL="debug"
    )
    assert config_js == (
        'window.RTI_CONFIG = { bffHost: "192.168.100.10", bffPort: "3000", logLevel: "debug" };\n'
    )


def test_empty_log_level_is_left_out(tmp_path):
    config_js, log_conf = _run(tmp_path, BFF_HOST="bff", LOG_LEVEL="")
    assert config_js == 'window.RTI_CONFIG = { bffHost: "bff" };\n'
    assert log_conf is None


def test_log_level_is_escaped_as_bff_host_is(tmp_path):
    config_js, _ = _run(tmp_path, LOG_LEVEL='de"bug\\')
    assert config_js == 'window.RTI_CONFIG = { logLevel: "de\\"bug\\\\" };\n'


@pytest.mark.parametrize(
    ("log_level", "nginx"),
    [
        ("debug", "info"),
        ("TRACE", "info"),
        ("info", "notice"),
        ("warning", "warn"),
        ("error", "error"),
        ("critical", "error"),
        ("10", "info"),
        ("30", "warn"),
        ("50", "error"),
        ("loud", "notice"),
    ],
)
def test_nginx_error_log_follows_log_level(tmp_path, log_level, nginx):
    _, log_conf = _run(tmp_path, LOG_LEVEL=log_level)
    assert log_conf == f"error_log /var/log/nginx/error.log {nginx};\n"


def test_unsetting_log_level_removes_the_nginx_setting(tmp_path):
    _run(tmp_path, LOG_LEVEL="debug")
    _, log_conf = _run(tmp_path)
    assert log_conf is None
