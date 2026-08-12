// src/components/Tree.jsx
import React, { useState, useCallback } from 'react';

const normalizeNodeType = (type) => (type || '').replace(/[^a-zA-Z0-9]/g, '-').toLowerCase();

const nodeTypeLabel = (type) => {
  const labels = {
    LDevice: 'LD',
    LogicalNode: 'LN',
    DO: 'DO',
    DA: 'DA',
    SDA: 'SDA',
    SDO: 'SDO',
    DataSet: 'DataSet',
    ReportControl: 'RC',
    BRCB: 'BRCB',
    URCB: 'URCB',
    Group: '',
    FCDA: 'FCDA',
  };
  return labels[type] || type || '';
};

const TreeNode = ({
  node,
  depth = 0,
  onNodeClick,
  onContextMenu,
  selectedRef,
  endpoint,
  cp,
  expandedNodes, // Receive expandedNodes from parent
  onExpandToggle, // Receive toggle handler from parent
}) => {
  const hasChildren = node.children && node.children.length > 0;
  const isGroupNode = node.type === 'Group';
  const displayName = node.name || node.ref || 'Unknown';
  const isSelected = selectedRef === node.ref;

  // Use the expandedNodes state to determine if this node is expanded
  const isExpanded = expandedNodes[node.ref] || depth < 1;

  const handleToggle = useCallback(
    (e) => {
      e.stopPropagation();
      onExpandToggle(node.ref, !isExpanded); // Toggle expansion state
    },
    [isExpanded, onExpandToggle, node.ref]
  );

  const handleClick = useCallback(
    (e) => {
      // Skip if this is a right-click (context menu)
      if (e.button === 2) return;  // Right-click (button 2)
      e.stopPropagation();
      if (onNodeClick) onNodeClick({ ref: node.ref, fc: node.fc, nodeType: node.type, endpoint, cp });
    },
    [node.ref, node.fc, node.type, onNodeClick, endpoint, cp]
  );

  const handleContextMenu = useCallback(
    (e) => {
      if (!node.ref || !onContextMenu) return;
      e.preventDefault();
      e.stopPropagation();
      onContextMenu(e, {
        ref: node.ref,
        fc: node.fc,
        nodeType: node.type,
        cdc: node.cdc,
        bType: node.bType,
        rcbType: node.rcbType,
        endpoint,
        cp,
      });
    },
    [node.ref, node.fc, node.type, node.cdc, node.bType, node.rcbType, onContextMenu, endpoint, cp]
  );

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
            onContextMenu={onContextMenu}
            selectedRef={selectedRef}
            endpoint={endpoint}
            cp={cp}
            expandedNodes={expandedNodes} // Pass expandedNodes to children
            onExpandToggle={onExpandToggle} // Pass toggle handler to children
          />
        ))}
      </ul>
    );
  };

  return (
    <li className={`scl-tree-item ${hasChildren ? 'has-children' : ''} ${isExpanded ? 'expanded' : 'collapsed'}`}>
      <div
        className={`scl-tree-row ${isSelected ? 'lm-selected' : ''}`}
        style={{ cursor: hasChildren || node.ref ? 'pointer' : 'default' }}
        onClick={handleClick}
        onContextMenu={handleContextMenu}
      >
        {hasChildren && (
          <button className="scl-tree-toggle" onClick={handleToggle}>
            {isExpanded ? '▾' : '▸'}
          </button>
        )}
        {!isGroupNode && node.type && (
          <span className={`scl-tree-tag ${node.type}`}>{nodeTypeLabel(node.type)}</span>
        )}
        <span className={`scl-tree-value scl-node-${normalizeNodeType(node.type)}`}>
          {displayName}
        </span>
        {!isGroupNode && (
          <>
            {node.bType && <span className="tree-btype-tag">[{node.bType}]</span>}
            {node.fc && <span className="tree-fc-tag">[{node.fc.toUpperCase()}]</span>}
            {node.cdc && <span className="tree-cdc-tag">({node.cdc})</span>}
            {node.value !== undefined && <span className="tree-value-display" data-obj-ref={node.ref} style={{ color: node.valueColor || 'var(--text-muted)' }}>{node.value}</span>}
          </>
        )}
      </div>
      {renderChildren()}
    </li>
  );
};

const Tree = ({ data, onNodeClick, onContextMenu, endpoint, cp, className = '', expandedNodes = {}, onExpandToggle }) => {
  const [selectedRef, setSelectedRef] = useState(null);

  const handleNodeClick = useCallback(
    (nodeInfo) => {
      setSelectedRef(nodeInfo.ref);
      if (onNodeClick) onNodeClick(nodeInfo);
    },
    [onNodeClick]
  );

  if (!data) {
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
        {data.children?.map((child, index) => (
          <TreeNode
            key={child.ref || child.name || index}
            node={child}
            depth={0}
            onNodeClick={handleNodeClick}
            onContextMenu={onContextMenu}
            selectedRef={selectedRef}
            endpoint={endpoint}
            cp={cp}
            expandedNodes={expandedNodes} // Pass expandedNodes to root TreeNode
            onExpandToggle={onExpandToggle} // Pass toggle handler to root TreeNode
          />
        ))}
      </ul>
    </div>
  );
};

export default Tree;