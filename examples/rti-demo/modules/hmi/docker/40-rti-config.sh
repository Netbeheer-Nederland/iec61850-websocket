#!/bin/sh
# SPDX-FileCopyrightText: 2026 Netbeheer Nederland
# SPDX-License-Identifier: Apache-2.0
#
# Runs at container start (the nginx image executes /docker-entrypoint.d/*.sh)
# and writes the HMI's runtime configuration from the environment:
#
#   BFF_HOST   BFF host as the user's browser reaches it (not a container name)
#   BFF_PORT   BFF port
#   LOG_LEVEL  what the HMI logs in the browser console (src/utils/log.js),
#              and nginx's error log level (spec 0008)
#
# Unset or empty variables are left out, so the build-time (VITE_BFF_*,
# VITE_LOG_LEVEL) or built-in defaults apply. See src/config.js.
#
# RTI_CONFIG_JS and RTI_NGINX_LOG_CONF move the two files it writes (tests).
set -eu

out=${RTI_CONFIG_JS:-/usr/share/nginx/html/config.js}
nginx_log_conf=${RTI_NGINX_LOG_CONF:-/etc/nginx/conf.d/00-rti-log-level.conf}

# A JavaScript string literal: escape backslashes and double quotes.
js_string() {
  printf '"%s"' "$(printf '%s' "$1" | sed 's/\\/\\\\/g; s/"/\\"/g')"
}

# nginx's error log level for a LOG_LEVEL, with the names and fallback of
# resolve_log_level: nginx's debug needs a debug build, so debug is info;
# info is notice (nginx's default); unknown is info, so notice.
nginx_level() {
  name=$(printf '%s' "$1" | tr '[:upper:]' '[:lower:]' | tr -d '[:space:]')
  case "$name" in
    debug|trace|notset) echo info ;;
    info) echo notice ;;
    warning|warn) echo warn ;;
    error|critical|fatal) echo error ;;
    ''|*[!0-9]*) echo notice ;;
    *)
      if [ "$name" -le 10 ]; then echo info
      elif [ "$name" -le 20 ]; then echo notice
      elif [ "$name" -le 30 ]; then echo warn
      else echo error
      fi ;;
  esac
}

entries=""
if [ -n "${BFF_HOST:-}" ]; then
  entries="bffHost: $(js_string "$BFF_HOST")"
fi
if [ -n "${BFF_PORT:-}" ]; then
  entries="${entries:+$entries, }bffPort: $(js_string "$BFF_PORT")"
fi
if [ -n "${LOG_LEVEL:-}" ]; then
  entries="${entries:+$entries, }logLevel: $(js_string "$LOG_LEVEL")"
fi

printf 'window.RTI_CONFIG = { %s };\n' "$entries" > "$out"
echo "40-rti-config.sh: wrote $out: { $entries }"

# The error log at http level; the access log stays on at every level.
if [ -n "${LOG_LEVEL:-}" ]; then
  level=$(nginx_level "$LOG_LEVEL")
  printf 'error_log /var/log/nginx/error.log %s;\n' "$level" > "$nginx_log_conf"
  echo "40-rti-config.sh: nginx error log at $level ($nginx_log_conf)"
else
  rm -f "$nginx_log_conf"
fi
