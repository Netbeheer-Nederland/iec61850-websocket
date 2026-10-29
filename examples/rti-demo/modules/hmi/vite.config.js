/*
 * SPDX-FileCopyrightText: 2025-2026 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 *
 * Copyright 2025-2026 Netbeheer Nederland
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

import { createLogger, defineConfig } from 'vite'
import react from '@vitejs/plugin-react'
import { buildLogLevel, cliLogLevel, viteLogLevel } from './vite.log-level.js'

// The HMI's log level (spec 0008): --log-level, else LOG_LEVEL, becomes
// VITE_LOG_LEVEL, which Vite reads from the environment after this file.
const hmiLogLevel = buildLogLevel(process.argv, process.env)
if (hmiLogLevel !== undefined) {
  process.env.VITE_LOG_LEVEL = hmiLogLevel
}

export default defineConfig({
  plugins: [react()],
  // --log-level also reached Vite as its own --logLevel; keep Vite's.
  customLogger: cliLogLevel(process.argv) !== undefined ? createLogger(viteLogLevel(process.argv)) : undefined,
  server: {
    port: 8080,
    open: true
  },
  test: {
    environment: 'jsdom',
    setupFiles: ['./src/setupTests.js'],
    globals: true
  }
})
