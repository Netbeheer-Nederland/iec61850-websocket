#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
cd "$SCRIPT_DIR"

command -v cfssl >/dev/null 2>&1 || {
  echo "❌ cfssl not installed"
  echo "Install with:"
  echo "  https://github.com/cloudflare/cfssl"
  echo "  go install github.com/cloudflare/cfssl/cmd/cfssl@latest"
  echo "  go install github.com/cloudflare/cfssl/cmd/cfssljson@latest"
  exit 1
}

SERVER_HOSTNAMES="${SERVER_HOSTNAMES:-localhost,127.0.0.1}"

echo "🔐 Generating CA..."
cfssl gencert -initca ca-csr.json | cfssljson -bare ca

echo "🔐 Generating server certificate..."
cfssl gencert \
  -ca=ca.pem \
  -ca-key=ca-key.pem \
  -config=ca-config.json \
  -profile=server \
  -hostname="${SERVER_HOSTNAMES}" \
  server-csr.json | cfssljson -bare server

echo "🔐 Generating client certificate..."
cfssl gencert \
  -ca=ca.pem \
  -ca-key=ca-key.pem \
  -config=ca-config.json \
  -profile=client \
  -hostname="${SERVER_HOSTNAMES}" \
  client-csr.json | cfssljson -bare client

chmod 600 *-key.pem

echo
echo "✅ Certificates generated:"
ls -1 *.pem
