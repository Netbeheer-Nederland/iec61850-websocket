import React, { useState, useEffect } from 'react';

function Model() {
  const [treeData, setTreeData] = useState([]);
  const [loading, setLoading] = useState(true);
  const [expandedNodes, setExpandedNodes] = useState({});

  // Sample tree data structure
  useEffect(() => {
    // This would be replaced with actual API call to fetch the SCL model
    const sampleData = [
      {
        name: 'IED1',
        type: 'ied',
        children: [
          {
            name: 'AccessPoint',
            type: 'accesspoint',
            children: [
              {
                name: 'LD0',
                type: 'ldevice',
                children: [
                  {
                    name: 'LLN0',
                    type: 'logicalnode',
                    children: [
                      { name: 'Mod', type: 'do' },
                      { name: 'Health', type: 'do' },
                    ]
                  }
                ]
              }
            ]
          }
        ]
      }
    ];
    setTreeData(sampleData);
    setLoading(false);
  }, []);

  const toggleNode = (nodePath) => {
    setExpandedNodes(prev => ({
      ...prev,
      [nodePath]: !prev[nodePath]
    }));
  };

  const renderTree = (nodes, depth = 0, path = '') => {
    if (!nodes || nodes.length === 0) return null;

    return (
      <ul className={depth === 0 ? 'scl-tree-root' : 'scl-tree-list'}>
        {nodes.map((node, index) => {
          const nodePath = path ? `${path}.${index}` : `${index}`;
          const hasChildren = node.children && node.children.length > 0;
          const isExpanded = expandedNodes[nodePath];
          const nodeClass = `scl-node-${node.type || 'default'}`;

          return (
            <li key={nodePath} className="scl-tree-item">
              <div className="scl-tree-row" onClick={() => hasChildren && toggleNode(nodePath)}>
                {hasChildren && (
                  <button className={`scl-tree-toggle ${!hasChildren ? 'hidden' : ''}`}>
                    <i className={`fas ${isExpanded ? 'fa-minus' : 'fa-plus'}`}></i>
                  </button>
                )}
                <span className={`scl-tree-value ${nodeClass}`}>
                  {node.name}
                </span>
                <span className={`scl-tree-tag ${node.type || 'hidden'}`}>
                  {node.type ? node.type.toUpperCase() : ''}
                </span>
                {node.value !== undefined && (
                  <span className="tree-value-display">
                    = {JSON.stringify(node.value)}
                  </span>
                )}
              </div>
              {hasChildren && isExpanded && (
                <div className="tree">
                  {renderTree(node.children, depth + 1, nodePath)}
                </div>
              )}
            </li>
          );
        })}
      </ul>
    );
  };

  return (
    <section className="page">
      <div className="page-header">
        <h1>IEC 61850 Model Tree</h1>
      </div>
      <div className="model-tree" id="model-tree-container">
        {loading ? (
          <div className="endpoints-loading">
            <span className="spinner"></span>
            Loading model...
          </div>
        ) : (
          <div className="tree">
            {renderTree(treeData)}
          </div>
        )}
      </div>
    </section>
  );
}

export default Model;
