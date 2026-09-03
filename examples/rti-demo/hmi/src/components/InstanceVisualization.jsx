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

  const soConnections = connections.filter(conn => conn.type === 'RTI-SO' && conn.status === 'connected');
  const fspConnections = connections.filter(conn => conn.type === 'RTI-FSP' && conn.status === 'connected');
  const hasConnected = connections.filter(conn => conn.status === 'connected').length > 0;

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
      ) : hasConnected ? (
        // alignItems defaults to 'stretch' here (removed 'flex-start') so the SO
        // column and the FSP column share the same height, letting the SO side
        // center itself against however tall the FSP stack ends up being.
        <div style={{ display: 'flex', justifyContent: 'center', gap: '40px', minHeight: '300px' }}>
          {/* SO (Client) Side - Left - centers vertically against FSP column height */}
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', alignItems: 'center', minWidth: '180px' }}>
            {soConnections.map((conn) => (
              <React.Fragment key={`so-${conn.name}`}>
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
                  <span style={{ color: 'var(--text-primary)', fontSize: '18px', fontWeight: '600' }}>{conn.name}</span>
                </div>
                {showLabels && (
                  <div style={{
                      padding: '6px 12px',
                      background: selectedConnection?.name === conn.name ? 'var(--primary-light)' : 'var(--bg-hover)',
                      borderRadius: '16px',
                      textAlign: 'center',
                      fontSize: '11px',
                      border: '1px solid var(--border-color)',
                      cursor: onConnectionClick ? 'pointer' : 'default'
                    }}
                    onClick={() => onConnectionClick?.(conn)}
                    title="Edit instance"
                  >
                    RTI-SO
                  </div>
                )}
              </React.Fragment>
            ))}
          </div>

          {/* FSP (Server) Side - Right - each FSP is its own row: line + circle/label,
              stacked vertically. This is what makes each line sit next to its own FSP
              instead of clustering separately at the top. */}
          <div style={{ display: 'flex', flexDirection: 'column', justifyContent: 'center', gap: '24px' }}>
            {fspConnections.map((conn) => (
              <div key={`fsp-row-${conn.name}`} style={{ display: 'flex', alignItems: 'center', gap: '0' }}>
                {/* Connection line - lives next to this specific FSP */}
                <div
                  style={{
                    height: '4px',
                    width: '40px',
                    background: (conn.connectedClients ?? 0) > 0
                      ? 'repeating-linear-gradient(to right, var(--success-color) 0, var(--success-color) 6px, transparent 6px, transparent 12px)'
                      : 'repeating-linear-gradient(to right, var(--border-color) 0, var(--border-color) 6px, transparent 6px, transparent 12px)',
                    flexShrink: 0
                  }}
                ></div>

                {/* FSP circle + label */}
                <div style={{ display: 'flex', flexDirection: 'column', alignItems: 'center', minWidth: '180px', marginLeft: '16px' }}>
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
                      cursor: onConnectionClick ? 'pointer' : 'default'
                    }}
                    onClick={() => onConnectionClick?.(conn)}
                    title="Edit instance"
                   >
                      RTI-FSP
                    </div>
                  )}
                </div>
              </div>
            ))}
            {fspConnections.length === 0 && (
              <div
                style={{
                  height: '4px',
                  width: '40px',
                  background: 'repeating-linear-gradient(to right, var(--border-color) 0, var(--border-color) 6px, transparent 6px, transparent 12px)'
                }}
              ></div>
            )}
          </div>
        </div>
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