// SPDX-FileCopyrightText: 2026 Netbeheer Nederland
//
// SPDX-License-Identifier: Apache-2.0

/**
 * Default BFF address, used until a user saves another one on the Settings
 * page (which is kept in localStorage and always wins).
 *
 * Highest first:
 *  1. runtime config - window.RTI_CONFIG from /config.js, written from the
 *     BFF_HOST / BFF_PORT environment variables when the Docker container
 *     starts (docker/40-rti-config.sh); empty outside Docker
 *  2. build time - VITE_BFF_HOST / VITE_BFF_PORT, baked in by Vite (an
 *     .env.local file for `npm run dev`, or Docker build args)
 *  3. localhost:5000
 */
const runtimeConfig =
  (typeof window !== 'undefined' && window.RTI_CONFIG) || {};

export const DEFAULT_BFF_HOST =
  runtimeConfig.bffHost || import.meta.env.VITE_BFF_HOST || 'localhost';

export const DEFAULT_BFF_PORT = String(
  runtimeConfig.bffPort || import.meta.env.VITE_BFF_PORT || '5000'
);
