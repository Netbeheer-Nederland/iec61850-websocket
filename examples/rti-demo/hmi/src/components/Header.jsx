import React from 'react';
import { useLocation } from 'react-router-dom';

function Header({ bffStatus }) {
  const location = useLocation();

  // Get breadcrumb text based on current path
  const getBreadcrumbText = () => {
    const path = location.pathname;
    switch (path) {
      case '/':
      case '/setup':
        return 'Setup';
      case '/connections':
        return 'Setup';
      case '/connections':
        return 'Connections';
      case '/model':
        return 'IEC 61850 Model Tree';
      case '/traffic':
        return 'Traffic';
      case '/data':
        return 'Read / Write Data';
      case '/reports':
        return 'Reports';
      case '/diagnostics':
        return 'Diagnostics';
      case '/tools':
        return 'Tools';
      case '/monitoring':
        return 'Monitoring';
      case '/settings':
        return 'Settings';
      case '/acsi-client':
        return 'ACSI Client';
      case '/acsi-server':
        return 'ACSI Server';
      default:
        return 'Setup';
    }
  };

  return (
    <header className="header">
      <div className="breadcrumb">
        <span id="breadcrumb-text">{getBreadcrumbText()}</span>
      </div>
      <div className="header-actions">
        {/* Hidden buttons from original HTML */}
        <button className="btn-icon" id="discovery-btn" title="Discover Endpoints" style={{ display: 'none' }}>
          <i className="fas fa-magnifying-glass"></i>
        </button>
        <button className="btn-icon" id="refresh-btn" title="Refresh" style={{ display: 'none' }}>
          <i className="fas fa-sync-alt"></i>
        </button>
        <button className="btn-icon" id="notification-btn" title="Notifications" style={{ display: 'none' }}>
          <i className="fas fa-bell"></i>
          <span className="badge">2</span>
        </button>
        
        {/* BFF Status Indicator - hidden on ACSI Client page */}
        {/*
        {location.pathname !== '/acsi-client' && (
          <div className="bff-connection-indicator" aria-live="polite">
            <span className={`bff-status-dot ${bffStatus.connected ? 'connected' : ''}`}></span>
            <span className="bff-status-text">{bffStatus.text}</span>
          </div>
        )}
        */}
      </div>
    </header>
  );
}

export default Header;
