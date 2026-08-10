import React, { useState, useCallback } from 'react';

const normalizeNodeType = (nodeType) => {
  return String(nodeType || 'node').toLowerCase().replace(/[^a-z0-9]+/g, '-');
};

const getNodeTypeLabel = (nodeType) => {
  const labels = {
    IED: 'IED',
    AccessPoint: 'Access Point',
    LDevice: 'Logical Device',
    LogicalNode: 'Logical Node',
    DO: 'Data Object',
    DA: 'Data Attribute',
    SDO: 'Sub Data Object',
    SDA: 'Sub Data Attribute',
    Group: 'Group',
    DataSet: 'Data Set',
    ReportControl: 'Report Control',
    Server: 'Server'
  };
  return labels[nodeType] || nodeType;
};

const transformToTreeNode = (node, parentRef = '') => {
  if (!node) return null;

  const nodeType = node.type || node.kind || 'node';
  const nodeName = node.name || node.iedName || node.ldName || node.lnName || node.doName || node.daName || 'Unknown';
  const ref = parentRef ? `${parentRef}.${nodeName}` : nodeName;

  const children = [];

  if (node.ieds) {
    children.push(...node.ieds.map(ied => transformToTreeNode(ied, ref)));
  }
  else if (node.accessPoints) {
    children.push(...node.accessPoints.map(ap => {
      const apName = typeof ap === 'object' ? ap.name : ap;
      const apRef = parentRef ? `${parentRef}/${apName}` : apName;
      return {
        type: 'AccessPoint',
        name: apName,
        ref: apRef,
        children: (ap.ldevices || []).map(ld => transformToTreeNode(ld, apRef))
      };
    }));
  }
  else if (node.ldevices) {
    children.push(...node.ldevices.map(ld => transformToTreeNode(ld, ref)));
  }
  else if (node.logical_nodes || node.lnodes || node.ln) {
    const lns = node.logical_nodes || node.lnodes || node.ln || [];
    children.push(...lns.map(ln => transformToTreeNode(ln, ref)));
  }
  else if (node.data_objects || node.dataObjects || node.do) {
    const dos = node.data_objects || node.dataObjects || node.do || [];
    children.push(...dos.map(doObj => transformToTreeNode(doObj, ref)));
  }
  else if (node.data_attributes || node.dataAttributes || node.da) {
    const das = node.data_attributes || node.dataAttributes || node.da || [];
    children.push(...das.map(da => transformToTreeNode(da, ref)));
  }
  else if (node.sub_data_objects || node.subDataObjects) {
    const sdos = node.sub_data_objects || node.subDataObjects || [];
    children.push(...sdos.map(sdo => transformToTreeNode(sdo, ref)));
  }
  else if (node.subDataAttributes) {
    children.push(...node.subDataAttributes.map(sda => transformToTreeNode(sda, ref)));
  }
  else if (node.children) {
    children.push(...node.children.map(child => transformToTreeNode(child, ref)));
  }

  return {
    type: nodeType,
    name: nodeName,
    ref: ref,
    fc: node.fc || null,
    cdc: node.cdc || null,
    bType: node.bType || null,
    value: node.value,
    children: children
  };
};

const TreeNode = ({ node, depth = 0, onNodeClick, selectedRef }) => {
  const [isExpanded, setIsExpanded] = useState(depth < 2);
  const hasChildren = node.children && node.children.length > 0;
  const nodeClass = `scl-node-${normalizeNodeType(node.type || 'default')}`;
  const displayName = node.name || node.ref || 'Unknown';
  const isSelected = selectedRef === (node.ref || node.name);

  const handleToggle = useCallback((e) => {
    e.stopPropagation();
    setIsExpanded(!isExpanded);
  }, [isExpanded]);

  const handleClick = useCallback((e) => {
    if (node.ref && onNodeClick) {
      onNodeClick({ ref: node.ref, fc: node.fc, nodeType: node.type });
    }
  }, [node.ref, node.fc, node.type, onNodeClick]);

  const handleRowClick = useCallback((e) => {
    if (e.target.classList.contains('scl-tree-toggle')) return;
    handleClick(e);
  }, [handleClick]);

  const renderChildren = () => {
    if (!hasChildren || !isExpanded) return null;
    return (
      <ul className="scl-tree-list">
        {node.children.map((child, index) => (
          <TreeNode
            key={child.ref || child.name || index}
            node={child}
            depth={depth + 1}
            onNodeClick={onNodeClick}
            selectedRef={selectedRef}
          />
        ))}
      </ul>
    );
  };

  return (
    <li className={`scl-tree-item ${hasChildren ? 'has-children' : ''} ${isExpanded ? 'expanded' : 'collapsed'}`}>
      <div
        className={`scl-tree-row ${isSelected ? 'lm-selected' : ''}`}
        style={{ cursor: node.ref || hasChildren ? 'pointer' : 'default' }}
        onClick={handleRowClick}
      >
        {hasChildren && (
          <button className="scl-tree-toggle" onClick={handleToggle}>
            <i className={`fas ${isExpanded ? 'fa-minus' : 'fa-plus'}`} />
          </button>
        )}
        <span className={`scl-tree-value ${nodeClass}`}>{displayName}</span>
        {node.type && node.type !== 'Group' && (
          <span className={`scl-tree-tag ${node.type}`}>{getNodeTypeLabel(node.type)}</span>
        )}
        {node.fc && <span className="tree-fc-tag">[{node.fc.toUpperCase()}]</span>}
        {node.cdc && <span className="tree-cdc-tag">({node.cdc})</span>}
        {node.value !== undefined && <span className="tree-value-display">= {JSON.stringify(node.value)}</span>}
      </div>
      {renderChildren()}
    </li>
  );
};

const Tree = ({ data, onNodeClick, className = '' }) => {
  const [selectedRef, setSelectedRef] = useState(null);

  const handleNodeClick = useCallback((nodeInfo) => {
    setSelectedRef(nodeInfo.ref);
    if (onNodeClick) onNodeClick(nodeInfo);
  }, [onNodeClick]);

  if (!data) {
    return (
      <div className={`model-tree ${className}`}>
        <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
          No model data available
        </p>
      </div>
    );
  }

  let treeRoot = data;
  
  if (!treeRoot.children) {
    treeRoot = transformToTreeNode(data);
  }

  if (!treeRoot || !treeRoot.children || treeRoot.children.length === 0) {
    return (
      <div className={`model-tree ${className}`}>
        <p style={{ color: 'var(--text-muted)', textAlign: 'center', padding: '20px' }}>
          No model data available
        </p>
      </div>
    );
  }

  return (
    <div className={`model-tree ${className}`}>
      <ul className="scl-tree-root">
        {treeRoot.children.map((child, index) => (
          <TreeNode
            key={child.ref || child.name || index}
            node={child}
            depth={0}
            onNodeClick={handleNodeClick}
            selectedRef={selectedRef}
          />
        ))}
      </ul>
    </div>
  );
};

export default Tree;
