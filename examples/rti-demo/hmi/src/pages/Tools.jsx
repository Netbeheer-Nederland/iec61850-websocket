import React from 'react';

function Tools() {
  return (
    <section className="page">
      <div id="tool-page-root">
        <div className="tools-workspace">
          <div className="tools-control-panel">
            <h3>HMI Tools</h3>
            <p className="tools-helper-text">Load SCL files and perform operations on the IEC 61850 model.</p>
            <div className="tools-action-buttons">
              <button className="btn-action tools-action-btn">
                <i className="fas fa-file-import"></i>
                Load SCL
              </button>
              <button className="btn-action tools-action-btn" disabled>
                <i className="fas fa-save"></i>
                <span id="tools-browseBtnText">No file selected</span>
              </button>
              <button className="btn-action tools-action-btn" disabled>
                <i className="fas fa-play"></i>
                Send
              </button>
            </div>
            <div className="tools-select-wrap">
              <label>Select Command</label>
              <select className="tools-select">
                <option value="">Select a command</option>
              </select>
            </div>
            <div className="tools-status-info">
              Ready to process SCL files.
            </div>
          </div>
          <div className="tools-tree-panel">
            <h3>SCL Model Tree</h3>
            <p className="tools-helper-text">Browse the loaded SCL model structure.</p>
            <div className="tree" style={{ minHeight: '520px', maxHeight: 'calc(100vh - 290px)' }}>
              <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
                No SCL file loaded. Use the controls to load and explore SCL files.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default Tools;
