import React from 'react';
import { useNavigate } from 'react-router-dom';

/**
 * Reusable component for visualizing SO-FSP connections
 * 
 * @param {Object[]} connections - Array of connection objects
 * @param {Object|null} selectedConnection - Currently selected connection (for highlighting)
 * @param {Function|null} onConnectionClick - Click handler for connection items
 * @param {Function|null} onReload - Click handler for reload button
 * @param {boolean} showReload - Whether to show reload button
 * @param {boolean} showLabels - Whether to show type labels
 * @param {boolean} loading - Whether data is currently loading
 */
function InstanceVisualization({
  connections,
  selectedConnection = null,
  onConnectionClick = null,
  onReload = null,
  showReload = true,
  showLabels = true,
  loading = false
}) {
  const navigate = useNavigate();
  
  // Internal click handlers for SO and FSP circles
  const handleSoClick = () => {
    const soConnection = connections.find(conn => conn.type === 'RTI-SO' && conn.status === 'connected');
    navigate('/acsi-client', { state: { endpoint: soConnection || { host: '127.0.0.1', port: 102, name: 'Default' } } });
  };
  
  const handleFspClick = (conn) => {
    navigate('/acsi-server', { state: { endpoint: conn } });
  };
  return (
    <div style={{ marginBottom: '40px', position: 'relative' }}>
      {showReload && onReload && (
        <div style={{ position: 'absolute', top: '0', right: '0' }}>
          <button 
            className="btn-icon"
            onClick={onReload}
            title="Refresh Instances"
            disabled={loading}
          >
            <i className="fas fa-sync-alt"></i>
          </button>
        </div>
      )}
      {loading ? (
        <div className="endpoints-loading">
          <span className="spinner"></span>
          Loading...
        </div>
      ) : connections.filter(conn => conn.status === 'connected').length > 0 ? (
        <>
          {/* SO (Client) Side - Left */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: '180px' }}>
            <div
              style={{
                width: '140px',
                height: '140px',
                border: '2px solid var(--border-color)',
                borderRadius: '50%',
                display: 'flex',
                alignItems: 'center',
                justifyContent: 'center',
                marginBottom: '12px',
                background: 'var(--bg-card)',
                cursor: 'pointer'
              }}
              onClick={handleSoClick}
              title="Type: RTI-SO (Client)"
            >
              <span style={{ color: 'var(--text-primary)', fontSize: '18px', fontWeight: '600' }}>SO</span>
            </div>
            {showLabels && (
              <div style={{
                padding: '6px 12px',
                background: 'var(--bg-hover)',
                borderRadius: '16px',
                textAlign: 'center',
                fontSize: '11px',
                border: '1px solid var(--border-color)'
              }}>
                RTI-SO
              </div>
            )}
            {connections
              .filter(conn => conn.type === 'RTI-SO' && conn.status === 'connected')
              .map((conn) => (
                <div
                  key={`so-${conn.name}`}
                  style={{
                    padding: '6px 12px',
                    background: selectedConnection?.name === conn.name ? 'var(--primary-light)' : 'var(--bg-hover)',
                    borderRadius: '16px',
                    margin: '6px 0',
                    textAlign: 'center',
                    fontSize: '10px',
                    border: '1px solid var(--border-color)',
                    minWidth: '140px',
                    cursor: onConnectionClick ? 'pointer' : 'default'
                  }}
                  onClick={() => onConnectionClick?.(conn)}
                  title={`Type: ${conn.type}`}
                >
                  <span style={{ color: 'var(--text-primary)', fontWeight: '500' }}>{conn.name}</span>
                  <div style={{ color: 'var(--text-muted)', marginTop: '2px' }}>
                    RTI-SO
                  </div>
                  {conn.properties_info?.properties && (
                    <div style={{ color: 'var(--text-muted)', marginTop: '2px' }}>
                      {conn.properties_info.properties.acsi_role} · {conn.properties_info.properties.ws_mode}
                    </div>
                  )}
                </div>
              ))}
          </div>

          {/* Connection lines */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', marginTop: '60px' }}>
            {connections
              .filter(conn => conn.type === 'RTI-FSP' && conn.status === 'connected')
              .map((_, index) => (
                <div
                  key={`line-${index}`}
                  style={{
                    height: '1px',
                    width: '40px',
                    background: 'var(--border-color)',
                    margin: '6px 0',
                    borderStyle: 'dashed'
                  }}
                ></div>
              ))}
            {connections.filter(conn => conn.type === 'RTI-FSP' && conn.status === 'connected').length === 0 && (
              <div style={{
                height: '1px',
                width: '40px',
                background: 'var(--border-color)',
                margin: '6px 0',
                borderStyle: 'dashed'
              }}></div>
            )}
          </div>

          {/* FSP (Server) Side - Right */}
          <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: '180px' }}>
            {connections
              .filter(conn => conn.type === 'RTI-FSP' && conn.status === 'connected')
              .map((conn) => (
                <React.Fragment key={`fsp-${conn.name}`}>
                  <div
                    style={{
                      width: '120px',
                      height: '120px',
                      border: '2px solid var(--border-color)',
                      borderRadius: '50%',
                      display: 'flex',
                      alignItems: 'center',
                      justifyContent: 'center',
                      margin: '6px 0',
                      background: selectedConnection?.name === conn.name ? 'var(--primary-light)' : 'var(--bg-card)',
                      cursor: 'pointer'
                    }}
                    onClick={() => handleFspClick(conn)}
                    title={`Type: ${conn.type}`}
                  >
                    <span style={{ color: 'var(--text-primary)', fontSize: '14px', fontWeight: '600', textAlign: 'center' }}>
                      {conn.name}
                    </span>
                  </div>
                  {showLabels && (
                    <div style={{
                      padding: '6px 12px',
                      background: selectedConnection?.name === conn.name ? 'var(--primary-light)' : 'var(--bg-hover)',
                      borderRadius: '16px',
                      textAlign: 'center',
                      fontSize: '11px',
                      border: '1px solid var(--border-color)',
                      minWidth: '120px'
                    }}>
                      <div style={{ fontWeight: '500' }}>{conn.name}</div>
                      <div style={{ color: 'var(--text-muted)', marginTop: '2px' }}>
                        RTI-FSP
                      </div>
                      {conn.properties_info?.properties && (
                        <div style={{ color: 'var(--text-muted)', marginTop: '2px', fontSize: '9px' }}>
                          {conn.properties_info.properties.acsi_role} · {conn.properties_info.properties.ws_mode}
                        </div>
                      )}
                    </div>
                  )}
                </React.Fragment>
              ))}
          </div>
        </>
      ) : (
        <div style={{
          textAlign: 'center',
          color: 'var(--text-muted)',
          fontSize: '12px',
          padding: '40px'
        }}>
          No connected instances to visualize
        </div>
      )}
    </div>
  );
}

export default InstanceVisualization;
