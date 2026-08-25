import React, { useState, useRef, useEffect, useCallback } from 'react';
import { generateModelPyCode } from '../utils/sclParser';

function Tools() {
  const [activeTab, setActiveTab] = useState('scl-model-factory');
  const [sclFile, setSclFile] = useState(null);
  const [sclContent, setSclContent] = useState('');
  const [iedNames, setIedNames] = useState([]);
  const [selectedIed, setSelectedIed] = useState('');
  const [apNames, setApNames] = useState([]);
  const [selectedAp, setSelectedAp] = useState('');
  const [modelTree, setModelTree] = useState(null);
  const [status, setStatus] = useState('Ready to process SCL files.');
  const [isLoading, setIsLoading] = useState(false);
  const [expandedNodes, setExpandedNodes] = useState({});
  const fileInputRef = useRef(null);

  // Tab switching
  const handleTabChange = (tabId) => {
    setActiveTab(tabId);
  };

  // Handle file selection
  const handleFileChange = useCallback((event) => {
    const file = event.target.files?.[0];
    if (!file) return;

    setSclFile(file);
    
    // Read file content
    const reader = new FileReader();
    reader.onload = (e) => {
      const content = e.target?.result;
      setSclContent(content);
      setStatus(`File loaded: ${file.name} (${(content?.length || 0).toLocaleString()} bytes)`);
    };
    reader.onerror = () => {
      setStatus('Error reading file.');
    };
    reader.readAsText(file);
  }, []);

  // Parse SCL file and extract IEDs and APs
  const parseSclMetadata = useCallback(async (content) => {
    if (!content) return;

    try {
      setIsLoading(true);
      setStatus('Parsing SCL file...');

      // Parse the XML
      const parser = new DOMParser();
      const doc = parser.parseFromString(content, 'application/xml');
      const parseError = doc.querySelector('parsererror');
      
      if (parseError) {
        setStatus('Error: Invalid XML/SCL file.');
        return;
      }

      // Extract IED names
      const iedNodes = Array.from(doc.querySelectorAll('IED'));
      const iedNamesList = iedNodes.map(node => node.getAttribute('name') || 'Unnamed');
      setIedNames(iedNamesList);
      
      if (iedNamesList.length > 0) {
        setSelectedIed(iedNamesList[0]);
      }

      // Extract AccessPoint names from first IED
      if (iedNodes.length > 0) {
        const firstIed = iedNodes[0];
        const apNodes = Array.from(firstIed.querySelectorAll('AccessPoint'));
        const apNamesList = apNodes.map(node => node.getAttribute('name') || 'cp1');
        setApNames(apNamesList);
        
        if (apNamesList.length > 0) {
          setSelectedAp(apNamesList[0]);
        }
      }

      setStatus(`Found ${iedNamesList.length} IED(s). Select IED and Access Point, then generate model.`);
    } catch (error) {
      console.error('Error parsing SCL:', error);
      setStatus(`Error parsing SCL: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  }, []);

  // Handle browse button click
  const handleBrowseClick = useCallback(() => {
    fileInputRef.current?.click();
  }, []);

  // Handle IED selection change
  const handleIedChange = (e) => {
    setSelectedIed(e.target.value);
  };

  // Handle AP selection change
  const handleApChange = (e) => {
    setSelectedAp(e.target.value);
  };

  // Trigger parsing when file content changes
  useEffect(() => {
    if (sclContent) {
      parseSclMetadata(sclContent);
      // Reset expanded nodes when new content is loaded
      setExpandedNodes({});
    } else {
      // Clear expanded nodes when content is cleared
      setExpandedNodes({});
    }
  }, [sclContent, parseSclMetadata]);

  // Download generated model.py
  const handleDownloadModel = useCallback(async () => {
    if (!sclContent) {
      setStatus('No SCL file loaded.');
      return;
    }

    try {
      setIsLoading(true);
      setStatus('Generating model.py for download...');

      // Use the utility to generate Python code
      const pythonCode = generateModelPyCode(
        sclContent,
        selectedIed,
        selectedAp,
        sclFile?.name || 'uploaded.scl'
      );
      
      // Create download
      const blob = new Blob([pythonCode], { type: 'text/plain' });
      const url = URL.createObjectURL(blob);
      const link = document.createElement('a');
      link.href = url;
      link.download = 'model.py';
      document.body.appendChild(link);
      link.click();
      document.body.removeChild(link);
      URL.revokeObjectURL(url);
      
      setStatus(`Downloaded model.py successfully`);
    } catch (error) {
      console.error('Error downloading model:', error);
      setStatus(`Error downloading model: ${error.message}`);
    } finally {
      setIsLoading(false);
    }
  }, [sclContent, selectedIed, selectedAp, sclFile]);

  // Toggle node expansion
  const toggleNode = useCallback((nodeKey) => {
    setExpandedNodes(prev => ({
      ...prev,
      [nodeKey]: !prev[nodeKey]
    }));
  }, []);

  // Check if node is expanded (defaults to true for first load)
  const isNodeExpanded = useCallback((nodeKey) => {
    return expandedNodes[nodeKey] !== false;
  }, [expandedNodes]);

  // Render tree view with collapse/expand
  const renderTree = (node, depth = 0, path = '') => {
    if (!node) return null;
    
    const nodeKey = path || node.name;
    const hasChildren = node.children && node.children.length > 0;
    const isExpanded = isNodeExpanded(nodeKey);
    const showToggle = hasChildren;
    
    // Get node class based on name for styling
    const getNodeClass = (name) => {
      const lower = (name || '').toLowerCase();
      if (lower.includes('ied')) return 'scl-node-IED';
      if (lower.includes('ldevice') || lower.includes('ld')) return 'scl-node-LDevice';
      if (lower.includes('lnode') || lower.includes('ln')) return 'scl-node-LogicalNode';
      if (lower.includes('do') || lower.includes('dataobject')) return 'scl-node-DO';
      if (lower.includes('da') || lower.includes('dataattribute')) return 'scl-node-DA';
      return '';
    };

    const nodeClass = getNodeClass(node.name);
    
    return (
      <div key={nodeKey} className="scl-tree-item" style={{ marginLeft: `${depth * 15}px` }}>
        <div 
          className={`scl-tree-row ${nodeClass}`}
          style={{ 
            padding: '4px 8px', 
            display: 'flex',
            alignItems: 'center',
            cursor: hasChildren ? 'pointer' : 'default'
          }}
          onClick={() => showToggle && toggleNode(nodeKey)}
        >
          {showToggle && (
            <button 
              className="scl-tree-toggle"
              onClick={(e) => { e.stopPropagation(); toggleNode(nodeKey); }}
            >
              <i className={`fas ${isExpanded ? 'fa-minus' : 'fa-plus'}`}></i>
            </button>
          )}
          <span className="scl-tree-value" style={{ color: 'var(--text-primary)' }}>{node.name}</span>
          {Object.keys(node.attributes).length > 0 && (
            <span style={{ color: 'var(--text-muted)', marginLeft: '8px', fontSize: '11px' }}>
              {Object.entries(node.attributes).map(([k, v]) => (`${k}="${v}"`)).join(' ')}
            </span>
          )}
          {node.text && node.text.trim() && (
            <span style={{ color: 'var(--text-secondary)', marginLeft: '8px', fontSize: '11px' }}>
              : "{node.text}"
            </span>
          )}
        </div>
        {hasChildren && isExpanded && (
          <ul className="scl-tree-list">
            {node.children.map((child, index) => renderTree(child, depth + 1, `${nodeKey}-${child.name}-${index}`))}
          </ul>
        )}
      </div>
    );
  };

  // Build tree from SCL
  const buildTreeFromScl = (content) => {
    try {
      const parser = new DOMParser();
      const doc = parser.parseFromString(content, 'application/xml');
      
      const buildNode = (xmlNode) => {
        if (!xmlNode || !xmlNode.children) return null;
        
        const attributes = {};
        if (xmlNode.attributes) {
          Array.from(xmlNode.attributes).forEach(attr => {
            attributes[attr.name] = attr.value;
          });
        }
        
        const children = Array.from(xmlNode.children || [])
          .map(child => buildNode(child))
          .filter(Boolean);
        
        return {
          name: xmlNode.localName || xmlNode.nodeName,
          attributes,
          text: xmlNode.textContent?.trim() || '',
          children
        };
      };
      
      return buildNode(doc.documentElement);
    } catch (error) {
      console.error('Error building tree:', error);
      return null;
    }
  };

  // Update tree when SCL content changes
  useEffect(() => {
    if (sclContent) {
      const tree = buildTreeFromScl(sclContent);
      setModelTree(tree);
    } else {
      setModelTree(null);
    }
  }, [sclContent]);

  return (
    <section className="page">
      <div className="page-header" style={{ marginBottom: '20px' }}>
        <h2>Tools</h2>
        <p style={{ color: 'var(--text-muted)', marginTop: '4px' }}>SCL Model Factory and API Testing</p>
      </div>

      <div className="acsi-log-tabs" role="tablist" aria-label="Tool tabs">
        <button 
          id="scl-model-factory-btn" 
          className={`acsi-log-tab ${activeTab === 'scl-model-factory' ? 'active' : ''}`} 
          type="button" 
          role="tab" 
          aria-selected={activeTab === 'scl-model-factory'}
          onClick={() => handleTabChange('scl-model-factory')}
        >
          SCL Model Factory
        </button>
        <button 
          id="api-btn" 
          className={`acsi-log-tab ${activeTab === 'api' ? 'active' : ''}`} 
          type="button" 
          role="tab" 
          aria-selected={activeTab === 'api'}
          onClick={() => handleTabChange('api')}
        >
          API
        </button>
      </div>

      {/* SCL Model Factory Tab */}
      <div 
        id="scl-model-factory-tab" 
        className={`acsi-log-tab-panel ${activeTab === 'scl-model-factory' ? 'active' : ''}`} 
        role="tabpanel"
        style={{ display: activeTab === 'scl-model-factory' ? 'block' : 'none' }}
      >
        <div style={{ padding: '20px 0' }}>
          <div className="tools-workspace">
            <div className="tools-control-panel">
              <h3>Actions</h3>
              <p className="tools-helper-text">Select an SCL file, inspect the parsed tree, and generate the Python model.</p>

              <input 
                id="tools-sclFile" 
                className="tools-file-input" 
                type="file" 
                accept=".scl,.scd,.cid,.icd,.xml"
                ref={fileInputRef}
                onChange={handleFileChange}
                style={{ display: 'none' }}
              />

              <div className="tools-action-buttons" style={{ marginBottom: '16px' }}>
                <button 
                  className="btn-action tools-action-btn" 
                  onClick={handleBrowseClick}
                  disabled={isLoading}
                >
                  <i className="fas fa-folder-open"></i>
                  <span>Browse SCL File</span>
                </button>

                <div id="tools-iedSelectWrap" className="tools-select-wrap">
                  <label htmlFor="tools-iedSelect">IED</label>
                  <select 
                    id="tools-iedSelect" 
                    className="tools-select"
                    value={selectedIed}
                    onChange={handleIedChange}
                    disabled={iedNames.length === 0 || isLoading}
                  >
                    {iedNames.length === 0 ? (
                      <option value="">No IEDs found</option>
                    ) : (
                      iedNames.map(name => (
                        <option key={name} value={name}>{name}</option>
                      ))
                    )}
                  </select>
                </div>

                <div id="tools-apSelectWrap" className="tools-select-wrap">
                  <label htmlFor="tools-apSelect">Access Point</label>
                  <select 
                    id="tools-apSelect" 
                    className="tools-select"
                    value={selectedAp}
                    onChange={handleApChange}
                    disabled={apNames.length === 0 || isLoading}
                  >
                    {apNames.length === 0 ? (
                      <option value="">No Access Points found</option>
                    ) : (
                      apNames.map(name => (
                        <option key={name} value={name}>{name}</option>
                      ))
                    )}
                  </select>
                </div>

                <button 
                  id="tools-generateModelBtn" 
                  className="btn-action tools-action-btn" 
                  onClick={handleDownloadModel}
                  disabled={!sclContent || isLoading}
                >
                  <i className="fas fa-file-code"></i>
                  <span>Generate model.py</span>
                </button>
              </div>

              <div id="tools-statusInfo" className="tools-status-info">
                {isLoading ? (
                  <>
                    <span className="spinner"></span> {status}
                  </>
                ) : (
                  status
                )}
              </div>
            </div>

            <div className="tools-tree-panel">
              <h3>SCL Model Structure</h3>
              <div 
                id="tools-modelPanel" 
                className="panel-content tree"
                style={{ 
                  minHeight: '400px', 
                  maxHeight: 'calc(100vh - 350px)',
                  overflowY: 'auto',
                  border: '1px solid var(--border-color)',
                  borderRadius: '8px',
                  padding: '12px',
                  background: 'var(--bg-card)'
                }}
              >
                {!sclContent ? (
                  <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '40px' }}>
                    No SCL file loaded. Use the controls to load and explore SCL files.
                  </p>
                ) : !modelTree ? (
                  <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
                    Parsing SCL file...
                  </p>
                ) : (
                  <ul className="scl-tree-root">
                    {renderTree(modelTree)}
                  </ul>
                )}
              </div>
            </div>
          </div>
        </div>
      </div>

      {/* API Tab */}
      <div 
        id="api-tab" 
        className={`acsi-log-tab-panel ${activeTab === 'api' ? 'active' : ''}`} 
        role="tabpanel"
        style={{ display: activeTab === 'api' ? 'block' : 'none' }}
      >
        <section className="acsi-panel acsi-panel-main" id="acsi-api-tester">
          <div>
            <h2>API Tester</h2>
            <p style={{ color: 'var(--text-muted)', marginBottom: '16px' }}>
              Test API endpoints directly from the browser.
            </p>
          </div>
          <div className="acsi-api-controls">
            <div style={{ marginBottom: '16px' }}>
              <label className="acsi-label" htmlFor="acsi-api-select">Endpoint</label>
              <select id="endpoint-api-select" className="acsi-select" style={{ marginBottom: '12px', width: '100%' }}>
                <option value="">Select an endpoint</option>
              </select>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label className="acsi-label" htmlFor="acsi-api-select">API</label>
              <select id="api-select" className="acsi-select" style={{ marginBottom: '12px', width: '100%' }}>
                <option value="">Select an API</option>
              </select>
            </div>

            <div style={{ marginBottom: '16px' }}>
              <label className="acsi-label" htmlFor="acsi-api-body">Request Body (JSON, optional)</label>
              <textarea 
                id="acsi-api-body" 
                className="acsi-textarea" 
                rows="6" 
                placeholder={"{\n  \"objRef\": \"LD0.LLN0.Mod.stVal\",\n  \"fc\": \"ST\"\n}"}
                style={{ width: '100%', padding: '12px', borderRadius: '4px', border: '1px solid var(--border-color)' }}
              ></textarea>
            </div>

            <button id="acsi-api-run" className="btn-primary" type="button">
              <i className="fas fa-play"></i>
              Run API
            </button>
          </div>
        </section>
        
        <section className="acsi-panel acsi-panel-main" id="acsi-api-logs-panel">
          <h2>Log Messages</h2>
          <div className="acsi-log-tabs" role="tablist" aria-label="Log tabs">
            <button 
              id="acsi-log-tab-api-btn" 
              className="acsi-log-tab active" 
              type="button" 
              role="tab" 
              aria-selected="true"
            >
              API Logs
            </button>
          </div>
          <div id="acsi-log-tab-api" className="acsi-log-tab-panel active" role="tabpanel">
            <div 
              id="acsi-api-logs" 
              className="acsi-log-list"
              style={{ 
                border: '1px solid var(--border-color)', 
                borderRadius: '8px', 
                padding: '12px', 
                minHeight: '200px',
                background: 'var(--bg-card)'
              }}
            >
              <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
                API logs will appear here when you run API calls.
              </p>
            </div>
          </div>
        </section>
      </div>
    </section>
  );
}

export default Tools;

