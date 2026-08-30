import React, { useState, useEffect, useCallback } from 'react';
import InstanceVisualization from '../components/InstanceVisualization';
import MessageMonitor from '../components/MessageMonitor';
import DataAccessPanel from '../components/DataAccessPanel';

function Traffic({ settings, getModel, updateModel, connections = [], loading = false, onReload }) {

  const [monitorsExpanded, setMonitorsExpanded] = useState(true);
  const [panelsExpanded, setPanelsExpanded] = useState(true);
  const [dataAccessPanels, setDataAccessPanels] = useState([1]);

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
          onReload={onReload}
          onConnectionClick={null}
          showLabels={true}
          showReload={true}
        />
      </div>
      
      {/* Collapsible Data Access Panels block */}
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
            justifyContent: 'space-between',
            cursor: 'pointer',
            marginBottom: '12px',
            padding: '4px 0'
          }}
          onClick={() => setPanelsExpanded(!panelsExpanded)}
        >
          <h3 style={{ margin: 0, color: 'var(--text-secondary)', flex: 1 }}>
            Data Access Panels
          </h3>
          <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
            <button
              className="btn-icon"
              onClick={(e) => {
                e.stopPropagation();
                setDataAccessPanels(prev => [...prev, prev.length + 1]);
              }}
              title="Add panel"
              style={{ padding: '4px 8px' }}
            >
              <i className="fas fa-plus" style={{ fontSize: '12px' }}></i>
            </button>
            <button
              className="btn-icon"
              onClick={(e) => {
                e.stopPropagation();
                if (dataAccessPanels.length > 1) {
                  setDataAccessPanels(prev => prev.slice(0, -1));
                }
              }}
              title="Remove panel"
              disabled={dataAccessPanels.length <= 1}
              style={{ padding: '4px 8px' }}
            >
              <i className="fas fa-minus" style={{ fontSize: '12px' }}></i>
            </button>
            <i 
              className={`fas ${panelsExpanded ? 'fa-chevron-up' : 'fa-chevron-down'}`}
              style={{ color: 'var(--text-muted)', fontSize: '14px' }}
            ></i>
          </div>
        </div>
        
        <div style={{ display: panelsExpanded ? 'block' : 'none' }}>
          <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fit, minmax(400px, 1fr))', gap: '16px' }}>
            {dataAccessPanels.map((id) => (
              <DataAccessPanel
                key={`data-access-panel-${id}`}
                connections={connections}
                getModel={getModel}
                updateModel={updateModel}
                settings={settings}
                cp={settings?.cp || 'cp1'}
              />
            ))}
          </div>
        </div>
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
