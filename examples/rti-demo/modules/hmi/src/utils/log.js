// SPDX-FileCopyrightText: 2026 Netbeheer Nederland
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The HMI's log level (spec 0008), with the names and fallback of the FSP's,
 * SO's and BFF's resolve_log_level: case-insensitive, a number, `trace` as
 * debug; an unknown or empty value is info.
 *
 * Highest first:
 *  1. the URL - ?log=<level>, read once when the page loads, so it lasts
 *     while the page is open and a reload without it drops it
 *  2. the Settings page - kept in localStorage (rti-hmi-log-level)
 *  3. runtime config - window.RTI_CONFIG.logLevel, written from the
 *     container's LOG_LEVEL (docker/40-rti-config.sh)
 *  4. build time - VITE_LOG_LEVEL; vite.config.js sets it from --log-level
 *     or LOG_LEVEL of `npm run dev` / `npm run build`
 *  5. info
 *
 * Every console call in src/ goes through `log`.
 */

export const LOG_LEVEL_NAMES = ['critical', 'error', 'warning', 'info', 'debug', 'trace'];

// Python's logging levels, with its aliases.
const LEVELS = {
  critical: 50, fatal: 50, error: 40, warning: 30, warn: 30, info: 20, debug: 10, trace: 10, notset: 0,
};
const INFO = LEVELS.info;

export const LOG_LEVEL_STORAGE_KEY = 'rti-hmi-log-level';

const isSet = (value) => value !== undefined && value !== null && String(value).trim() !== '';

/** A level name or number as its number; null when unknown. */
export function parseLogLevel(value) {
  const name = String(value).trim().toLowerCase();
  if (/^\d+$/.test(name)) return Number(name);
  return Object.hasOwn(LEVELS, name) ? LEVELS[name] : null;
}

/**
 * The first source with a value wins, even an unknown one (which is info),
 * as --log-level wins over LOG_LEVEL in the Python services.
 * Returns { level, name, from, value, unknown }.
 */
export function resolveLogLevel(sources) {
  for (const { value, from } of sources) {
    if (!isSet(value)) continue;
    const level = parseLogLevel(value);
    if (level === null) return { level: INFO, name: 'info', from, value: String(value), unknown: true };
    return { level, name: String(value).trim().toLowerCase(), from, value: String(value), unknown: false };
  }
  return { level: INFO, name: 'info', from: 'default', value: undefined, unknown: false };
}

const readUrlLevel = () => {
  try {
    return new URLSearchParams(window.location.search).get('log');
  } catch {
    return null;
  }
};

const urlLevel = readUrlLevel();

export const getUrlLogLevel = () => (isSet(urlLevel) ? urlLevel : null);

export const getStoredLogLevel = () => {
  try {
    return localStorage.getItem(LOG_LEVEL_STORAGE_KEY);
  } catch {
    return null;
  }
};

// The sources below the URL and the Settings page: what "From the server"
// on the Settings page stands for.
const serverSources = () => [
  { value: (typeof window !== 'undefined' && window.RTI_CONFIG?.logLevel) || undefined, from: 'LOG_LEVEL' },
  { value: import.meta.env.VITE_LOG_LEVEL, from: 'the build' },
];

export const resolveServerLogLevel = () => resolveLogLevel(serverSources());

const allSources = () => [
  { value: urlLevel, from: '?log=' },
  { value: getStoredLogLevel(), from: 'the Settings page' },
  ...serverSources(),
];

let active = resolveLogLevel(allSources());

export const getLogLevel = () => active;

/** Keeps a Settings page choice (null clears it) and applies it straight away. */
export function setStoredLogLevel(name) {
  try {
    if (isSet(name)) localStorage.setItem(LOG_LEVEL_STORAGE_KEY, name);
    else localStorage.removeItem(LOG_LEVEL_STORAGE_KEY);
  } catch {
    // No localStorage (private mode): the choice lasts until the page is reloaded.
  }
  active = resolveLogLevel(allSources());
  return active;
}

/** "debug (from LOG_LEVEL)", 'info ("loud" from LOG_LEVEL is unknown)', "info (default)". */
export function describeLogLevel(resolved = active) {
  if (resolved.unknown) return `${resolved.name} ("${resolved.value}" from ${resolved.from} is unknown)`;
  if (resolved.from === 'default') return `${resolved.name} (default)`;
  return `${resolved.name} (from ${resolved.from})`;
}

// critical shows errors only, like error.
const shows = (threshold) => threshold >= Math.min(active.level, LEVELS.error);

export const log = {
  error: (...args) => { if (shows(LEVELS.error)) console.error(...args); },
  warn: (...args) => { if (shows(LEVELS.warning)) console.warn(...args); },
  info: (...args) => { if (shows(LEVELS.info)) console.info(...args); },
  debug: (...args) => { if (shows(LEVELS.debug)) console.debug(...args); },
};

/** Logged once at start (main.jsx). */
export const logStartLevel = () => log.info(`HMI log level: ${describeLogLevel()}`);
