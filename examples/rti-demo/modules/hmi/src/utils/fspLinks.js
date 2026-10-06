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

/**
 * Name the FSP behind each of an SO's associated cps - the HMI's copy of
 * bff_server.py's _link_so_to_fsps, used for first paint before the BFF's
 * "connections" push arrives. A cp is the WebSocket path the FSP dials the
 * SO on, so it shows up both in the SO's acsi_client_list and in the FSP's
 * own accessPoints.
 *
 * @param {string[]} cps - The SO's associated cps
 * @param {Object[]} fsps - RTI-FSP connections, with accessPoints / connectedClients
 * @returns {{cp: string, fsp: string|null}[]} fsp is null when no FSP reports the cp;
 *   if several do, one with a live WebSocket connection wins
 */
export function linkSoToFsps(cps = [], fsps = []) {
  return cps.map((cp) => {
    const candidates = fsps.filter((f) => (f.accessPoints || []).includes(cp));
    const match = candidates.find((f) => (f.connectedClients ?? 0) > 0) || candidates[0];
    return { cp, fsp: match ? match.name : null };
  });
}
