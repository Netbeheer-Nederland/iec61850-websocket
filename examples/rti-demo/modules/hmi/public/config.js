// SPDX-FileCopyrightText: 2026 Netbeheer Nederland
//
// SPDX-License-Identifier: Apache-2.0

// Runtime configuration, loaded by index.html before the app (see
// src/config.js). Empty here, so the build-time / built-in defaults apply.
// The Docker image rewrites this file at container start from BFF_HOST and
// BFF_PORT (docker/40-rti-config.sh).
window.RTI_CONFIG = window.RTI_CONFIG || {};
