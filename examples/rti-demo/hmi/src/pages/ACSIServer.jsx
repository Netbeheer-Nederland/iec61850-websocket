import React from 'react';

function ACSIServer() {
  return (
    <section className="page">
      <div id="acsi-server-page-root">
        <div className="page-header">
          <h1>ACSI Server</h1>
        </div>
        <div className="acsi-connection-section" style={{ display: 'flex', alignItems: 'flex-end', gap: '16px', marginBottom: '24px' }}>
          <div className="form-group">
            <label>Host</label>
            <input type="text" placeholder="0.0.0.0" />
          </div>
          <div className="form-group">
            <label>Port</label>
            <input type="number" placeholder="102" />
          </div>
          <button className="btn-primary">
            Start Server
          </button>
        </div>
        <div>
          <p style={{ color: 'var(--text-muted)' }}>
            ACSI Server configuration and management interface.
          </p>
        </div>
      </div>
    </section>
  );
}

export default ACSIServer;
