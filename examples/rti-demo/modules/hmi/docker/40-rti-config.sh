#!/bin/sh
# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Runs at container start (the nginx image executes /docker-entrypoint.d/*.sh)
# and writes the HMI's runtime configuration from the environment:
#
#   BFF_HOST  BFF host as the user's browser reaches it (not a container name)
#   BFF_PORT  BFF port
#
# Unset or empty variables are left out, so the build-time (VITE_BFF_*) or
# built-in defaults apply. See src/config.js.
set -eu

out=/usr/share/nginx/html/config.js

# A JavaScript string literal: escape backslashes and double quotes.
js_string() {
  printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"
}

entries=""
if [ -n "${BFF_HOST:-}" ]; then
  entries="bffHost: $(js_string "$BFF_HOST")"
fi
if [ -n "${BFF_PORT:-}" ]; then
  entries="${entries:+$entries, }bffPort: $(js_string "$BFF_PORT")"
fi

printf 'window.RTI_CONFIG = { %s };\n' "$entries" > "$out"
echo "40-rti-config.sh: wrote $out: { $entries }"
