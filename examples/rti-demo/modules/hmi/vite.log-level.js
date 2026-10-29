// SPDX-FileCopyrightText: 2026 Netbeheer Nederland
//
// SPDX-License-Identifier: Apache-2.0

/**
 * The HMI's build-time log level (spec 0008), for vite.config.js:
 * `npm run dev -- --log-level debug` wins over LOG_LEVEL in the environment,
 * as in the FSP, SO and BFF. Either becomes VITE_LOG_LEVEL in the bundle
 * (src/utils/log.js); without them, VITE_LOG_LEVEL is as Vite finds it
 * (the environment or an .env file).
 */

const optionValue = (argv, names) => {
  for (let i = 0; i < argv.length; i += 1) {
    for (const name of names) {
      if (argv[i] === name && i + 1 < argv.length) return argv[i + 1];
      if (argv[i].startsWith(`${name}=`)) return argv[i].slice(name.length + 1);
    }
  }
  return undefined;
};

/** The value of --log-level on the command line, or undefined. */
export const cliLogLevel = (argv) => optionValue(argv, ['--log-level']);

/** --log-level, else LOG_LEVEL; undefined when neither is set. */
export function buildLogLevel(argv, env) {
  const cli = cliLogLevel(argv);
  if (cli !== undefined) return cli;
  return env.LOG_LEVEL ? env.LOG_LEVEL : undefined;
}

/**
 * Vite's CLI reads --log-level as its own --logLevel (info, warn, error,
 * silent), and an HMI level such as debug would silence it. With --log-level
 * given, Vite's output keeps the level of its own --logLevel / -l, or info.
 */
export const viteLogLevel = (argv) => optionValue(argv, ['--logLevel', '-l']) ?? 'info';
