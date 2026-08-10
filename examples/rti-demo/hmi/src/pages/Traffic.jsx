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
      
      <div style={{ marginBottom: '40px' }}>
        {connections
          .filter(conn => conn.status === 'connected')
          .map((endpoint) => (
            <MessageMonitor
              key={`monitor-${endpoint.host}-${endpoint.port}`}
              endpoints={[endpoint]}
              title={`Messages - ${endpoint.name || `${endpoint.host}:${endpoint.port}`}`}
              defaultInterval={10000}
              showEndpointSelect={false}
            />
          ))}
      </div>
    </section>
  );
}

export default Traffic;
