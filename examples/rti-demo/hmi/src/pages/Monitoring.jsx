import React from 'react';

function Monitoring() {
  return (
    <section className="page">
      <div id="monitoring-page-root">
        <div className="monitoring-workspace">
          <div className="monitor-block">
            <div className="monitor-header">
              <h3>WebSocket Messages</h3>
              <div className="monitor-controls">
                <select className="monitor-endpoint-select" disabled>
                  <option value="">Select endpoint...</option>
                </select>
                <select className="monitor-interval-select">
                  <option value="1000">1s</option>
                  <option value="5000">5s</option>
                  <option value="10000" selected>10s</option>
                  <option value="30000">30s</option>
                </select>
                <button className="btn-icon monitor-control-btn" title="Start Monitoring">
                  <i className="fas fa-play"></i>
                </button>
                <button className="btn-icon monitor-control-btn" title="Stop Monitoring" disabled>
                  <i className="fas fa-stop"></i>
                </button>
                <button className="btn-icon monitor-control-btn" title="Clear Messages">
                  <i className="fas fa-trash"></i>
                </button>
              </div>
            </div>
            <div className="monitor-status">
              Monitoring stopped
            </div>
            <div className="monitor-messages">
              <p className="monitor-no-messages">
                No messages. Start monitoring to see WebSocket traffic.
              </p>
            </div>
          </div>
          <div className="monitor-block">
            <div className="monitor-header">
              <h3>Command History</h3>
              <div className="monitor-controls">
                <button className="btn-icon monitor-control-btn" title="Clear History">
                  <i className="fas fa-trash"></i>
                </button>
              </div>
            </div>
            <div className="monitor-messages">
              <p className="monitor-no-messages">
                No commands in history.
              </p>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default Monitoring;
