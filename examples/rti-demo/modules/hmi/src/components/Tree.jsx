/*
 * SPDX-FileCopyrightText: 2025 Netbeheer Nederland
 * SPDX-License-Identifier: Apache-2.0
 *
 * Copyright 2025 Netbeheer Nederland
 *
 * Licensed under the Apache License, Version 2.0 (the "License");
 * you may not use this file except in compliance with the License.
 * You may obtain a copy of the License at
 *
 *     http://www.apache.org/licenses/LICENSE-2.0
 *
 * Unless required by applicable law or agreed to in writing, software
 * distributed under the License is distributed on an "AS IS" BASIS,
 * WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
 * See the License for the specific language governing permissions and
 * limitations under the License.
 */

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

// FA icon per node type, colored to match that type's existing
// .scl-tree-tag.{Type} color (see styles.css) so the icon reinforces the
// tag rather than introducing a second, uncoordinated color scheme.
const NODE_ICONS = {
  LDevice: 'fa-folder',
  LogicalNode: 'fa-microchip',
  DO: 'fa-cube',
  DA: 'fa-circle',
  SDA: 'fa-circle',
  SDO: 'fa-cube',
  DataSet: 'fa-list-ul',
  ReportControl: 'fa-satellite-dish',
  BRCB: 'fa-satellite-dish',
  URCB: 'fa-satellite-dish',
  FCDA: 'fa-link',
};

// Group nodes (e.g. "DataSets", "ReportControls") have no tag at all today
// (see the `!isGroupNode` guard below) - an icon keyed by name is the only
// way to tell them apart at a glance, inspired by scd-visualizer's
// per-category icons in its IED tree.
const GROUP_ICONS = {
  DataSets: 'fa-layer-group',
  ReportControls: 'fa-broadcast-tower',
};

const nodeIconClass = (node) => {
  if (node.type === 'Group') return GROUP_ICONS[node.name] || 'fa-folder-open';
  return NODE_ICONS[node.type] || null;
};

const TreeNode = React.memo(({
  node,
  depth = 0,
  onNodeClick,
  onContextMenu,
  selectedRef,
  endpoint,
  cp,
  expandedNodes,
  onExpandToggle,
}) => {
  const hasChildren = node.children && node.children.length > 0;
  const isGroupNode = node.type === 'Group';
  const displayName = node.name || node.ref || 'Unknown';
  const isSelected = selectedRef === node.ref;

  // A node is expanded only if explicitly marked so - no depth-based
  // default. Every page resets expandedNodes to {} on each fresh fetch/load
  // (see ACSIServer.jsx's loadServerModel, ACSIClient.jsx's loadClientTree),
  // so a freshly loaded model always starts fully collapsed; explicit
  // clicks (or Expand/Collapse All) are the only thing that opens a node.
  //
  // This used to default depth-0 nodes (LDevices - Tree's top-level map
  // renders data.children at depth 0) to expanded via `depth < 1`, which
  // also made the LD collapse toggle non-functional (clicking it flipped
  // the chevron but renderChildren() below never saw isExpanded turn
  // false, since `|| depth < 1` won unconditionally at depth 0).
  const isExpanded = !!expandedNodes[node.ref];

  const handleToggle = useCallback(
    (e) => {
      e.stopPropagation();
      onExpandToggle(node.ref, !isExpanded);
    },
    [isExpanded, onExpandToggle, node.ref]
  );

  const handleClick = useCallback(
    (e) => {
      if (e.button === 2) return;
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
            expandedNodes={expandedNodes}
            onExpandToggle={onExpandToggle}
          />
        ))}
      </ul>
    );
  };

  const iconClass = nodeIconClass(node);

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
        {iconClass && (
          <i className={`fas ${iconClass} scl-tree-icon ${node.type}`} aria-hidden="true"></i>
        )}
        {!isGroupNode && node.type && (
          <span className={`scl-tree-tag ${node.type}`}>{nodeTypeLabel(node.type)}</span>
        )}
        <span className={`scl-tree-value scl-node-${normalizeNodeType(node.type)}`}>
          {displayName}
        </span>
        {isGroupNode && hasChildren && (
          <span className="scl-tree-count">{node.children.length}</span>
        )}
        {!isGroupNode && (
          <>
            {node.bType && <span className="tree-btype-tag">({node.bType})</span>}
            {node.fc && <span className="tree-fc-tag">[{node.fc.toUpperCase()}]</span>}
            {node.cdc && <span className="tree-cdc-tag">({node.cdc})</span>}
            {node.value !== undefined && <span className="tree-value-display" data-obj-ref={node.ref} style={{ color: node.valueColor || 'var(--text-muted)' }}>{node.value}</span>}
          </>
        )}
      </div>
      {renderChildren()}
    </li>
  );
});

// Collects the ref of every node in the subtree that has children (i.e.
// every node the toggle button would actually apply to), for Expand/
// Collapse All. Nodes without a ref (currently: Group nodes like
// "DataSets"/"ReportControls") are skipped - the same nodes whose
// individual toggle already can't be addressed reliably today, since
// TreeNode's own handleToggle keys expandedNodes by node.ref too.
function collectExpandableRefs(node, acc) {
  if (node?.children?.length) {
    if (node.ref) acc.push(node.ref);
    node.children.forEach((child) => collectExpandableRefs(child, acc));
  }
  return acc;
}

const Tree = ({ data, onNodeClick, onContextMenu, endpoint, cp, className = '', expandedNodes = {}, onExpandToggle }) => {
  const [selectedRef, setSelectedRef] = useState(null);

  const handleNodeClick = useCallback(
    (nodeInfo) => {
      setSelectedRef(nodeInfo.ref);
      if (onNodeClick) onNodeClick(nodeInfo);
    },
    [onNodeClick]
  );

  const setAllExpanded = useCallback(
    (expanded) => {
      if (!onExpandToggle || !data?.children) return;
      const refs = [];
      data.children.forEach((child) => collectExpandableRefs(child, refs));
      refs.forEach((ref) => onExpandToggle(ref, expanded));
    },
    [data, onExpandToggle]
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
      {onExpandToggle && data.children?.length > 0 && (
        <div className="scl-tree-toolbar">
          <button type="button" className="scl-tree-toolbar-btn" onClick={() => setAllExpanded(true)}>
            Expand All
          </button>
          <button type="button" className="scl-tree-toolbar-btn" onClick={() => setAllExpanded(false)}>
            Collapse All
          </button>
        </div>
      )}
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
            expandedNodes={expandedNodes}
            onExpandToggle={onExpandToggle}
          />
        ))}
      </ul>
    </div>
  );
};

export default Tree;

