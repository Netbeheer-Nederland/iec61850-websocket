/*
 * SPDX-FileCopyrightText: 2025 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 *
 * Copyright 2025 Netbeheer Nederland
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

import React, { useState } from 'react';

function Reports() {
  const [reports, setReports] = useState([]);

  const handleExport = () => {
    // Export reports logic
    alert('Export functionality will be implemented');
  };

  return (
    <section className="page">
      <div className="page-header">
        <h1>Reports</h1>
        <button className="btn-primary" id="btn-export-reports" onClick={handleExport}>
          <i className="fas fa-download"></i>
          Export
        </button>
      </div>
      <div className="reports-section" id="reports-container">
        {reports.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
            No reports available.
          </p>
        ) : (
          <div>
            {reports.map((report, index) => (
              <div key={index} className="endpoint-card">
                <div className="endpoint-card-icon">
                  <i className="fas fa-file-pdf"></i>
                </div>
                <div className="endpoint-card-info">
                  <div className="endpoint-card-name">{report.name}</div>
                  <div className="endpoint-card-desc">
                    Generated: {report.date}
                  </div>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

export default Reports;
