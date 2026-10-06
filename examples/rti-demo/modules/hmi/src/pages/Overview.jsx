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

import React from 'react';
import InstanceVisualization from '../components/InstanceVisualization';

// Read-only: just the graphical SO/FSP overview. The instance table and
// registering, editing and deleting instances all live on the Connections
// page - this page never lists or mutates a connection, so it doesn't need
// ConnectionModal, useNavigate (InstanceVisualization does its own
// navigation for the FSP/SO circle clicks), or any of the add/edit/delete
// plumbing the old combined Setup page used to carry.
function Overview({ connections = [], loading = false }) {
  return (
    <section className="page">
      <div className="page-header" style={{ marginBottom: '20px' }}>
        <h2>Overview</h2>
        <p style={{ color: 'var(--text-muted)', marginTop: '4px' }}>Live status of all registered instances</p>
      </div>

      <React.Fragment>
        {/* SO-FSP Graphic Visualization */}
        <div style={{ marginBottom: '40px' }}>
          {loading ? (
            <div className="endpoints-loading">
              <span className="spinner"></span>
              Loading...
            </div>
          ) : (
            <InstanceVisualization
              connections={connections}
              loading={loading}
              onConnectionClick={null}
            />
          )}
        </div>

        {!loading && connections.length === 0 && (
          <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
            No instances registered. Register one from the Connections page to get started.
          </p>
        )}
      </React.Fragment>
    </section>
  );
}

export default Overview;
