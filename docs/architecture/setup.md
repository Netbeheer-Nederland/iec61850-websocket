# Installation Guide

Detailed setup instructions for the `iec61850-websocket` project on Linux.  
Covers **Ubuntu 24.04 LTS** and **Fedora 41**.

---

## Table of contents

1. [System requirements](#1-system-requirements)
2. [Git](#2-git)
3. [Python 3.12](#3-python-312)
4. [UV](#4-uv)
5. [Docker and Docker Compose](#5-docker-and-docker-compose)
6. [cfssl](#6-cfssl)
7. [Doxygen (optional)](#7-doxygen-optional)
8. [Clone and set up the project](#8-clone-and-set-up-the-project)
9. [Verify the installation](#9-verify-the-installation)

---

## 1. System requirements

| Component | Minimum | Recommended |
|---|---|---|
| OS | Ubuntu 22.04 / Fedora 38 | Ubuntu 24.04 LTS / Fedora 41 |
| CPU | x86-64, 2 cores | x86-64, 4+ cores |
| RAM | 2 GB | 4 GB |
| Disk | 2 GB free | 5 GB free |

---

## 2. Git

Git is used to clone the repository.

**Ubuntu**

```bash
sudo apt update
sudo apt install -y git
```

**Fedora**

```bash
sudo dnf install -y git
```

Verify:

```bash
git --version
```

---

## 3. Python 3.12

Python 3.12 is the recommended interpreter. The build requires the development headers (`python3-dev` /
`python3-devel`) so that C-extension dependencies compile correctly.

**Ubuntu 24.04** (Python 3.12 is in the default repos)

```bash
sudo apt update
sudo apt install -y python3.12 python3.12-dev python3.12-venv
```

**Ubuntu 22.04** (requires the deadsnakes PPA)

```bash
sudo apt update
sudo apt install -y software-properties-common
sudo add-apt-repository -y ppa:deadsnakes/ppa
sudo apt update
sudo apt install -y python3.12 python3.12-dev python3.12-venv
```

**Fedora 41** (Python 3.12 is in the default repos)

```bash
sudo dnf install -y python3.12 python3.12-devel
```

Verify:

```bash
python3.12 --version
```

> **Note:** `bitstruct` is listed as a Python dependency in `pyproject.toml` and is installed automatically by
> `uv sync`. You do not need to install it manually via the system package manager.

---

## 4. UV

UV is the project's package and virtual-environment manager. It is installed per-user and does **not** require root.

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

After installation, reload your shell environment so the `uv` binary is on `PATH`:

```bash
source "$HOME/.local/bin/env"
```

Or restart your terminal. Verify:

```bash
uv --version
```

> UV manages the virtual environment and all Python dependencies. The steps below rely on it exclusively — you do
> not need to run `pip` directly.

---

## 5. Docker and Docker Compose

Docker is required to run support services such as the Keycloak identity provider used in the security test
scenarios. Docker Compose V2 (`docker compose`) is bundled as a plugin.

### Ubuntu

Add Docker's official APT repository, then install the packages:

```bash
# Install prerequisites
sudo apt update
sudo apt install -y ca-certificates curl

# Add Docker's GPG key
sudo install -m 0755 -d /etc/apt/keyrings
sudo curl -fsSL https://download.docker.com/linux/ubuntu/gpg \
     -o /etc/apt/keyrings/docker.asc
sudo chmod a+r /etc/apt/keyrings/docker.asc

# Add the repository
echo \
  "deb [arch=$(dpkg --print-architecture) signed-by=/etc/apt/keyrings/docker.asc] \
  https://download.docker.com/linux/ubuntu \
  $(. /etc/os-release && echo "$VERSION_CODENAME") stable" \
  | sudo tee /etc/apt/sources.list.d/docker.list > /dev/null

# Install Docker Engine and the Compose plugin
sudo apt update
sudo apt install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin
```

Enable and start the Docker daemon:

```bash
sudo systemctl enable --now docker
```

### Fedora

Add Docker's official DNF repository, then install the packages:

```bash
# Add the repository
sudo dnf config-manager --add-repo \
  https://download.docker.com/linux/fedora/docker-ce.repo

# Install Docker Engine and the Compose plugin
sudo dnf install -y \
  docker-ce \
  docker-ce-cli \
  containerd.io \
  docker-buildx-plugin \
  docker-compose-plugin
```

Enable and start the Docker daemon:

```bash
sudo systemctl enable --now docker
```

### Post-install: run Docker without sudo

To avoid prefixing every `docker` command with `sudo`, add your user to the `docker` group:

```bash
sudo usermod -aG docker "$USER"
```

Log out and back in (or run `newgrp docker`) for the group membership to take effect.

Verify:

```bash
docker --version
docker compose version
docker run --rm hello-world
```

---

## 6. cfssl

`cfssl` and `cfssljson` are Cloudflare's TLS certificate tools, used by the project scripts to generate test
certificates under `testing/certs/`.

Download the pre-built Linux binaries from the [cfssl GitHub releases](https://github.com/cloudflare/cfssl/releases)
page. The steps below fetch the latest release automatically (both distributions use the same procedure):

```bash
# Retrieve the latest version tag (requires curl and sed, available by default)
CFSSL_VERSION=$(
  curl -fsSL "https://api.github.com/repos/cloudflare/cfssl/releases/latest" \
  | grep '"tag_name"' \
  | sed -E 's/.*"v([^"]+)".*/\1/'
)

# Download the binaries
curl -fsSL \
  "https://github.com/cloudflare/cfssl/releases/download/v${CFSSL_VERSION}/cfssl_${CFSSL_VERSION}_linux_amd64" \
  -o cfssl

curl -fsSL \
  "https://github.com/cloudflare/cfssl/releases/download/v${CFSSL_VERSION}/cfssljson_${CFSSL_VERSION}_linux_amd64" \
  -o cfssljson

# Make executable and move to a directory on PATH
chmod +x cfssl cfssljson
sudo mv cfssl cfssljson /usr/local/bin/
```

> On ARM64 machines (e.g. Raspberry Pi, AWS Graviton), replace `linux_amd64` with `linux_arm64` in the URLs above.

Verify:

```bash
cfssl version
cfssljson --version
```

---

## 7. Doxygen (optional)

Doxygen is used to generate API reference documentation from source docstrings. It is not required to run the
project or its tests.

**Ubuntu**

```bash
sudo apt install -y doxygen
```

**Fedora**

```bash
sudo dnf install -y doxygen
```

Verify:

```bash
doxygen --version
```

To generate the docs after installation, run from the repository root:

```bash
doxygen docs/doxygen/Doxyfile
```

The output is written to `docs/doxygen/html/`. Open `docs/doxygen/html/index.html` in a browser to browse the
generated reference.

---

## 8. Clone and set up the project

With all prerequisites in place, clone the repository and let UV prepare the environment:

```bash
# 1. Clone the repository
git clone https://github.com/Netbeheer-Nederland/iec61850-websocket.git
cd iec61850-websocket

# 2. Create the virtual environment and install all dependencies
uv venv
uv sync

# 3. Build the project wheel (needed by some tests)
uv build
```

UV creates a `.venv/` directory inside the project root. All `uv run` commands automatically activate it — you do
not need to source it manually.

---

## 9. Verify the installation

Run the unit-test suite to confirm that the environment is configured correctly:

```bash
uv run pytest tests/unit -v
```

All tests should pass. If any test fails with an import error, re-run `uv sync` to ensure all dependencies were
installed.

To do a quick smoke-test of a complete message flow, start the example server in one terminal:

```bash
uv run python examples/server.py
```

Then connect a client in a second terminal:

```bash
uv run python examples/client.py
```

If both sides connect and exchange messages without errors, the installation is complete.

---

## Troubleshooting

| Symptom | Likely cause | Fix |
|---|---|---|
| `uv: command not found` | Shell env not reloaded after UV install | Run `source "$HOME/.local/bin/env"` or open a new terminal |
| `python3.12: command not found` on Ubuntu 22.04 | deadsnakes PPA not added | Follow the Ubuntu 22.04 path in [section 3](#3-python-312) |
| `cfssl: command not found` | Binary not on `PATH` | Confirm `/usr/local/bin` is on `PATH`; re-run the `sudo mv` step |
| `permission denied` running Docker | User not in `docker` group | Run `sudo usermod -aG docker "$USER"` then log out and back in |
| `uv sync` fails on a C extension | Python headers missing | Install `python3.12-dev` (Ubuntu) or `python3.12-devel` (Fedora) |
| TLS test failures | Certificates not generated | Follow the certificate-generation steps in the relevant test markdown file under `tests/` |
