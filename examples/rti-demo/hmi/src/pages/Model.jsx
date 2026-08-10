import React, { useState, useEffect, useCallback } from 'react';
import { useNavigate } from 'react-router-dom';
import Tree from '../components/Tree';
import InstanceVisualization from '../components/InstanceVisualization';
import { executeApiCall, buildTargetValue } from '../services/apiService';

function Model({ settings }) {
  const navigate = useNavigate();
  const [connections, setConnections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [treeData, setTreeData] = useState(null);
  const [selectedConnection, setSelectedConnection] = useState(null);
  
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

  const handleConnectionClick = (conn) => {
    setSelectedConnection(conn);
    loadModel(conn);
  };

  const loadModel = useCallback(async (conn) => {
    if (!conn) return;
    setLoading(true);
    try {
      const targetValue = buildTargetValue(conn.host, conn.port);
      const result = await executeApiCall('model', targetValue, {});
      
      if (result?.ok) {
        let modelData = result.payload;
        
        // Path 1: result.result.model (BFF wraps response in result)
        if (modelData?.result?.model) {
          modelData = modelData.result.model;
        }
        // Path 2: Direct model field
        else if (modelData?.model) {
          modelData = modelData.model;
        }
        // Path 3: The payload itself might be the model
        
        // Check if there's a tree field
        if (modelData?.tree) {
          modelData = modelData.tree;
        }
        
        // Handle case where model is a Python dict string
        if (typeof modelData === 'string') {
          // Try to parse as JSON first
          try {
            modelData = JSON.parse(modelData);
          } catch (e) {
            // If not JSON, try to parse as Python dict string
            const jsonStr = modelData
              .replace(/'/g, '"')
              .replace(/True/g, 'true')
              .replace(/False/g, 'false')
              .replace(/None/g, 'null');
            try {
              modelData = JSON.parse(jsonStr);
            } catch (e2) {
              console.error('Failed to parse model data:', e2);
            }
          }
        }
        
        // If we still have the full BFF response, try result field
        if (modelData === result.payload && modelData?.result) {
          modelData = modelData.result;
        }
        
        // If modelData has accessPoints but no children structure, create a simple tree
        if (modelData?.accessPoints && !modelData.children && !modelData.ieds && !modelData.kind) {
          modelData = {
            iedName: modelData.iedName || conn.name || 'Server',
            accessPoints: modelData.accessPoints.map(apName => ({
              name: apName,
              ldevices: []
            }))
          };
        }
        
        if (modelData && Object.keys(modelData).length > 0) {
          setTreeData(transformModelToTree(modelData));
        }
      }
    } catch (error) {
      console.error('Failed to load model:', error);
    } finally {
      setLoading(false);
    }
  }, []);

  const transformModelToTree = (model) => {
    if (!model) return null;
    if (model.server && model.server.logicalDevices) {
      return {
        name: model.server.iedName || 'Server',
        type: 'Server',
        children: model.server.logicalDevices.map(ld => ({
          name: ld,
          type: 'LDevice',
          children: []
        }))
      };
    }
    if (model.iedName) {
      return {
        name: model.iedName,
        type: 'IED',
        children: Object.entries(model).filter(([key]) => key !== 'iedName').map(([key, value]) => ({
          name: key,
          type: typeof value === 'object' ? 'Group' : 'Data',
          children: typeof value === 'object' ? Object.keys(value).map(k => ({ name: k, type: 'Data' })) : []
        }))
      };
    }
    return model;
  };

  const handleNavigateToInstance = (conn) => {
    if (conn.type === 'RTI-SO') {
      navigate('/acsi-client', { state: { endpoint: conn } });
    } else if (conn.type === 'RTI-FSP') {
      navigate('/acsi-server', { state: { endpoint: conn } });
    }
  };

  return (
    <section className="page">
      <div className="page-header" style={{ marginBottom: '20px' }}>
        <h2>Model</h2>
        <p style={{ color: 'var(--text-muted)', marginTop: '4px' }}>SOs, FSP and Instances</p>
      </div>

      <div style={{ marginBottom: '40px' }}>
        {loading ? (
          <div className="endpoints-loading">
            <span className="spinner"></span>
            Loading connections...
          </div>
        ) : (
          <div style={{
            display: 'flex',
            justifyContent: 'center',
            alignItems: 'flex-start',
            gap: '40px',
            minHeight: '300px'
          }}>
            <InstanceVisualization
              connections={connections}
              selectedConnection={selectedConnection}
              loading={loading}
              onReload={fetchConnections}
              onConnectionClick={handleConnectionClick}
              showLabels={true}
              showReload={true}
            />
          </div>
        )}
      </div>

      <div style={{ paddingTop: '20px', borderTop: '1px solid var(--border-color)', marginTop: '20px' }}>
        <h3 style={{ marginBottom: '12px' }}>Instances</h3>
        {connections && connections.filter(conn => conn.type === 'RTI-FSP').length > 0 ? (
          <div style={{ border: '1px solid var(--border-color)', borderRadius: '8px', overflow: 'hidden' }}>
            {connections.filter(conn => conn.type === 'RTI-FSP').map((conn, index) => (
              <div 
                key={conn.name || index} 
                style={{
                  display: 'flex',
                  alignItems: 'center',
                  justifyContent: 'space-between',
                  padding: '16px 20px',
                  borderBottom: index < connections.filter(conn => conn.type === 'RTI-FSP').length - 1 ? '1px solid var(--border-color)' : 'none',
                  background: index % 2 === 0 ? 'var(--bg-card)' : 'var(--bg-hover)',
                  cursor: 'pointer'
                }}
                onClick={() => handleConnectionClick(conn)}
              >
                <div style={{ display: 'flex', alignItems: 'center', gap: '24px' }}>
                  <span style={{ color: 'var(--text-secondary)', fontWeight: '500', minWidth: '100px' }}>
                    {conn.type}
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>·</span>
                  <span style={{ color: 'var(--text-primary)', fontWeight: '500', minWidth: '150px' }}>
                    {conn.name}
                  </span>
                  <span style={{ color: 'var(--text-muted)' }}>·</span>
                  <span style={{ color: 'var(--text-secondary)', minWidth: '150px' }}>
                    {conn.host}:{conn.port}
                  </span>
                </div>
                <div style={{ display: 'flex', alignItems: 'center', gap: '16px' }}>
                  <span 
                    className="bff-status-dot" 
                    style={{
                      background: conn.status === 'connected' ? 'var(--success-color)' : 'var(--danger-color)'
                    }}
                  ></span>
                  {conn.status === 'connected' && (
                    <>
                      <button 
                        className="btn-secondary"
                        style={{ padding: '6px 12px', fontSize: '12px' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleConnectionClick(conn);
                        }}
                        title="View Model"
                      >
                        View
                      </button>
                      <button 
                        className="btn-icon" 
                        style={{ padding: '6px', fontSize: '14px' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleNavigateToInstance(conn);
                        }}
                        title="Open instance"
                      >
                        <i className="fas fa-arrow-right"></i>
                      </button>
                    </>
                  )}
                </div>
              </div>
            ))}
          </div>
        ) : (
          <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
            No RTI-FSP (Server) instances found.
          </p>
        )}
      </div>

      <div style={{ paddingTop: '20px', borderTop: '1px solid var(--border-color)' }}>
        {selectedConnection && (
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '16px' }}>
            <h3 style={{ margin: 0 }}>Model for: {selectedConnection.name}</h3>
            <div style={{ display: 'flex', gap: '8px' }}>
              <button 
                className="btn-icon" 
                onClick={() => handleNavigateToInstance(selectedConnection)}
                title="Open instance"
              >
                <i className="fas fa-external-link-alt"></i>
              </button>
            </div>
          </div>
        )}
        
        <div id="model-tree-container" className="model-tree">
          {loading ? (
            <div className="endpoints-loading">
              <span className="spinner"></span>
              Loading model...
            </div>
          ) : treeData ? (
            <Tree data={treeData} />
          ) : selectedConnection ? (
            <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
              Click on a connection to load its model
            </p>
          ) : (
            <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
              Select a connected instance to view its model
            </p>
          )}
        </div>
      </div>
    </section>
  );
}

export default Model;

