/**
 * Model utilities for transforming model data into tree structures
 * Used by both Model.jsx and ACSIServer.jsx pages
 */

/**
 * Transforms model data into a tree structure compatible with the Tree component.
 * Handles various model formats: new hierarchical format, legacy server/logicalDevices format,
 * and legacy iedName with object properties.
 * 
 * @param {Object} model - The model data to transform
 * @param {string} [path=''] - The current path in the tree (used for building refs)
 * @returns {Object|null} - Tree structure with name, type, children, and other metadata
 */
export function transformModelToTree(model, path = '') {
  if (!model) return null;
  
  // If model already has children array (new format with IED/LD/LN/DA hierarchy)
  if (model.children && Array.isArray(model.children)) {
    const name = model.name || model.iedName || 'Root';
    const nodePath = path ? `${path}/${name}` : name;
    const node = {
      name: name,
      type: model.type || model.kind || 'IED',
      children: model.children.map(child => transformModelToTree(child, nodePath))
    };
    // Preserve ref, fc, cdc, bType, value and other Tree component properties
    if (model.ref !== undefined) node.ref = model.ref;
    else node.ref = nodePath;
    if (model.fc !== undefined) node.fc = model.fc;
    if (model.cdc !== undefined) node.cdc = model.cdc;
    if (model.bType !== undefined) node.bType = model.bType;
    if (model.value !== undefined) node.value = model.value;
    return node;
  }
  
  // Legacy server/logicalDevices format
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
  
  // Legacy iedName with object properties (old format)
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
}

export default { transformModelToTree };
