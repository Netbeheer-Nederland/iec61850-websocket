import React, { useState } from 'react';

function Diagnostics() {
  const [diagnostics, setDiagnostics] = useState([]);

  const handleClear = () => {
    setDiagnostics([]);
  };

  return (
    <section className="page">
      <div className="page-header">
        <h1>Diagnostics</h1>
        <button className="btn-primary" id="btn-clear-diagnostics" onClick={handleClear}>
          <i className="fas fa-trash"></i>
          Clear
        </button>
      </div>
      <div className="diagnostics-section" id="diagnostics-container">
        {diagnostics.length === 0 ? (
          <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
            No diagnostic information available.
          </p>
        ) : (
          <div>
            {diagnostics.map((item, index) => (
              <div key={index} className="endpoint-card">
                <div className="endpoint-card-icon">
                  <i className="fas fa-exclamation-triangle"></i>
                </div>
                <div className="endpoint-card-info">
                  <div className="endpoint-card-name">{item.timestamp}</div>
                  <div className="endpoint-card-desc">{item.message}</div>
                  <span className="endpoint-card-status" style={{ background: item.severity === 'error' ? 'var(--danger-color)' : 'var(--warning-color)' }}>
                    {item.severity}
                  </span>
                </div>
              </div>
            ))}
          </div>
        )}
      </div>
    </section>
  );
}

export default Diagnostics;
