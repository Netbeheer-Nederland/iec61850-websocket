import React, { useState, useEffect, useCallback } from 'react';
import InstanceVisualization from '../components/InstanceVisualization';
import MessageMonitor from '../components/MessageMonitor';

function Traffic({ settings }) {
  const [connections, setConnections] = useState([]);
  const [loading, setLoading] = useState(true);

  // Fetch connections from BFF API
  const fetchConnections = useCallback(async () => {
    try {
      setLoading(true);
      const response = await fetch(`http://${settings?.bffHost || 'localhost'}:${settings?.bffPort || '5000'}/api/connections`);
      if (response.ok) {
        const data = await response.json();
        setConnections(data.connections || []);
      }
    } catch (error) {
      console.error('Failed to fetch connections:', error);
    } finally {
      setLoading(false);
    }
  }, [settings?.bffHost, settings?.bffPort]);

  useEffect(() => {
    fetchConnections();
  }, [fetchConnections]);

  const [monitorsExpanded, setMonitorsExpanded] = useState(true);

  return (
    <section className="page">
      <div className="page-header" style={{ marginBottom: '20px' }}>
        <h2>Traffic</h2>
        <p style={{ color: 'var(--text-muted)', marginTop: '4px' }}>SOs, FSP and Instances</p>
      </div>

      <div style={{ marginBottom: '40px' }}>
        <InstanceVisualization
          connections={connections}
          selectedConnection={null}
          loading={loading}
          onReload={fetchConnections}
          onConnectionClick={null}
          showLabels={true}
          showReload={true}
        />
      </div>
      
      {/* Collapsible monitors block */}
      <div style={{ 
        marginBottom: '20px',
        border: '1px solid var(--border-color)',
        borderRadius: '8px',
        padding: '12px',
        background: 'var(--bg-card)'
      }}>
        <div 
          style={{
            display: 'flex',
            alignItems: 'center',
            cursor: 'pointer',
            marginBottom: '12px',
            padding: '4px 0'
          }}
          onClick={() => setMonitorsExpanded(!monitorsExpanded)}
        >
          <h3 style={{ margin: 0, color: 'var(--text-secondary)', flex: 1 }}>
            Message Monitors
          </h3>
          <i 
            className={`fas ${monitorsExpanded ? 'fa-chevron-up' : 'fa-chevron-down'}`}
            style={{ color: 'var(--text-muted)', fontSize: '14px' }}
          ></i>
        </div>
        
        <div style={{ display: monitorsExpanded ? 'block' : 'none' }}>
          {/* ACSI Client endpoints (RTI-SO) - First row */}
          <div style={{ marginBottom: '30px' }}>
            <h4 style={{ marginBottom: '12px', color: 'var(--text-muted)' }}>
              ACSI Client Endpoints (RTI-SO)
            </h4>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '16px',
              width: '100%'
            }}>
              {connections
                .filter(conn => conn.status === 'connected' && conn.type === 'RTI-SO')
                .map((endpoint) => (
                  <MessageMonitor
                    key={`client-monitor-${endpoint.host}-${endpoint.port}`}
                    endpoints={[endpoint]}
                    title={`${endpoint.name || endpoint.host}:${endpoint.port}`}
                    defaultInterval={10000}
                    showEndpointSelect={false}
                  />
                ))}
            </div>
          </div>
          
          {/* ACSI Server endpoints (RTI-FSP) - Second row */}
          <div style={{ marginBottom: '0' }}>
            <h4 style={{ marginBottom: '12px', color: 'var(--text-muted)' }}>
              ACSI Server Endpoints (RTI-FSP)
            </h4>
            <div style={{
              display: 'grid',
              gridTemplateColumns: 'repeat(auto-fit, minmax(280px, 1fr))',
              gap: '16px',
              width: '100%'
            }}>
              {connections
                .filter(conn => conn.status === 'connected' && conn.type === 'RTI-FSP')
                .map((endpoint) => (
                  <MessageMonitor
                    key={`server-monitor-${endpoint.host}-${endpoint.port}`}
                    endpoints={[endpoint]}
                    title={`${endpoint.name || endpoint.host}:${endpoint.port}`}
                    defaultInterval={10000}
                    showEndpointSelect={false}
                  />
                ))}
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}

export default Traffic;
