import React, { useState, useEffect, useCallback, useRef } from 'react';
import { useNavigate } from 'react-router-dom';
import Tree from '../components/Tree';
import InstanceVisualization from '../components/InstanceVisualization';
import { executeApiCall, buildTargetValue } from '../services/apiService';
import { generateModelPyCode } from '../utils/sclParser';
import { transformModelToTree } from '../utils/modelUtils';

function Model({ settings }) {
  const navigate = useNavigate();
  const [connections, setConnections] = useState([]);
  const [loading, setLoading] = useState(true);
  const [treeData, setTreeData] = useState(null);
  const [selectedConnection, setSelectedConnection] = useState(null);
  const [uploadingModel, setUploadingModel] = useState(false);
  const [expandedNodes, setExpandedNodes] = useState({});
  const fileInputRef = useRef(null);
  const [uploadStatus, setUploadStatus] = useState('');
  
  const handleExpandToggle = useCallback((ref, expanded) => {
    setExpandedNodes(prev => ({
      ...prev,
      [ref]: expanded
    }));
  }, []);
  
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

  const handleNavigateToInstance = (conn) => {
    if (conn.type === 'RTI-SO') {
      navigate('/acsi-client', { state: { endpoint: conn } });
    } else if (conn.type === 'RTI-FSP') {
      navigate('/acsi-server', { state: { endpoint: conn } });
    }
  };

  // Handle model file upload for a specific connection
  const handleUpdateModel = useCallback(async (conn, file) => {
    if (!conn || !file) return;

    try {
      setUploadingModel(true);
      setUploadStatus(`Uploading model for ${conn.name}...`);

      // Read file content
      const reader = new FileReader();
      const content = await new Promise((resolve, reject) => {
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsText(file);
      });

      // Ensure content is valid
      if (!content || typeof content !== 'string') {
        throw new Error('Could not read file content');
      }

      // Check if content is empty
      if (!content.trim()) {
        throw new Error('File content is empty');
      }

      let modelPyContent = content;

      // If SCL file, convert to Python
      if (file.name.endsWith('.scl') || file.name.endsWith('.scd') || file.name.endsWith('.icd') || file.name.endsWith('.cid')) {
        modelPyContent = generateModelPyCode(content, null, null, file.name);
      }
      // If .py file, use content directly
      // Note: content already includes the file content as string

      // Validate connection has required fields
      if (!conn) {
        throw new Error('No connection provided');
      }
      if (!('host' in conn) || !('port' in conn)) {
        throw new Error(`Connection ${conn.name || 'unknown'} is missing host or port property`);
      }
      if (!conn.host || !conn.port) {
        throw new Error(`Connection ${conn.name || 'unknown'} has empty host or port (host: ${conn.host}, port: ${conn.port})`);
      }

      // Call the update-iedmodel endpoint through the main BFF's /api/execute
      const targetValue = buildTargetValue(conn.host, conn.port);
      if (!targetValue) {
        throw new Error(`Could not build target value from host: ${conn.host}, port: ${conn.port}`);
      }
      const result = await executeApiCall('update-iedmodel', targetValue, { modelPy: modelPyContent });

      if (result?.ok) {
        setUploadStatus(`Model updated successfully for ${conn.name}`);
        // Reload connections to get the updated model
        setTimeout(() => {
          fetchConnections();
          setUploadStatus('');
        }, 1000);
      } else {
        setUploadStatus(`Error updating model: ${result?.error || result?.payload?.error || 'Unknown error'}`);
      }
    } catch (error) {
      console.error('Failed to update model:', error);
      setUploadStatus(`Error: ${error.message}`);
    } finally {
      setUploadingModel(false);
      // Clear file input
      if (fileInputRef.current) {
        fileInputRef.current.value = '';
      }
    }
  }, [fetchConnections, setUploadingModel, setUploadStatus]);

  // Trigger file input click
  const handleUpdateModelClick = useCallback((conn) => {
    // Store the connection for later use
    const currentConn = conn;
    
    // Click the hidden file input
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.py,.scl,.scd,.icd,.cid';
    input.style.display = 'none';
    
    input.onchange = async (e) => {
      const file = e.target.files?.[0];
      if (file) {
        await handleUpdateModel(currentConn, file);
      }
      document.body.removeChild(input);
    };
    
    document.body.appendChild(input);
    input.click();
  }, [handleUpdateModel]);

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
          <InstanceVisualization
            connections={connections}
            selectedConnection={selectedConnection}
            loading={loading}
            onReload={fetchConnections}
            onConnectionClick={handleConnectionClick}
            showLabels={true}
            showReload={true}
          />
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
                        className="btn-secondary"
                        style={{ padding: '6px 12px', fontSize: '12px' }}
                        onClick={(e) => {
                          e.stopPropagation();
                          handleUpdateModelClick(conn);
                        }}
                        title="Upload model file (Python or SCL)"
                        disabled={uploadingModel}
                      >
                        {uploadingModel ? 'Uploading...' : 'Update Model'}
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
        {uploadStatus && (
          <div style={{ 
            marginTop: '12px', 
            padding: '10px 16px', 
            background: uploadStatus.includes('Error') ? 'var(--danger-bg)' : 'var(--success-bg)',
            borderRadius: '4px',
            color: uploadStatus.includes('Error') ? 'var(--danger-color)' : 'var(--success-color)',
            fontSize: '13px',
            display: 'flex',
            alignItems: 'center',
            gap: '8px'
          }}>
            {uploadingModel ? (
              <>
                <span className="spinner" style={{ width: '14px', height: '14px' }}></span>
                {uploadStatus}
              </>
            ) : (
              <>
                {uploadStatus.includes('Error') ? (
                  <i className="fas fa-exclamation-circle"></i>
                ) : (
                  <i className="fas fa-check-circle"></i>
                )}
                {uploadStatus}
              </>
            )}
          </div>
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
            <Tree data={treeData} expandedNodes={expandedNodes} onExpandToggle={handleExpandToggle} />
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

