/**
 * Model utilities for transforming model data into tree structures
 * Used by both Model.jsx and ACSIServer.jsx pages
 */

/**
 * Determine which separator joins a child's ref onto its parent's ref,
 * per IEC 61850 ACSI object reference rules:
 *   IED            -> contributes nothing (root, not part of the ref)
 *   LD  (child of IED) -> just the LD name, no prefix
 *   LN  (child of LD)  -> `${ldRef}/${lnName}`   (slash)
 *   DO  (child of LN)  -> `${lnRef}.${doName}`   (dot)
 *   DA/SDA/SDO (child of DO/DA/SDO) -> `${parentRef}.${childName}` (dot)
 *
 * @param {string} parentRef - the already-computed ref of the parent node ('' for IED root)
 * @param {string} parentType - the parent's node type/kind (IED, LDevice/LD, LogicalNode/LN, DO, DA, SDA, SDO, ...)
 * @param {string} childName - the child's own name
 * @returns {string} the ref to assign to the child
 */
function buildChildRef(parentRef, parentType, childName) {
  const normalizedParentType = (parentType || '').toString();

  // Root / IED: child (an LD) gets no prefix at all
  if (!parentRef || normalizedParentType === 'IED' || normalizedParentType === 'Server' || normalizedParentType === 'server') {
    return childName;
  }

  // Parent is an LD: child (an LN) is joined with '/'
  if (normalizedParentType === 'LDevice' || normalizedParentType === 'LD') {
    return `${parentRef}/${childName}`;
  }

  // Parent is LN, DO, DA, SDA, SDO, or anything deeper: joined with '.'
  return `${parentRef}.${childName}`;
}

/**
 * Transforms model data into a tree structure compatible with the Tree component.
 * Handles various model formats: new hierarchical format, legacy server/logicalDevices format,
 * and legacy iedName with object properties.
 *
 * @param {Object} model - The model data to transform
 * @param {string} [parentRef=''] - The ref of the parent node (used to build this node's ref)
 * @param {string} [parentType=''] - The type/kind of the parent node (used to pick the right separator)
 * @returns {Object|null} - Tree structure with name, type, children, ref, and other metadata
 */
export function transformModelToTree(model, parentRef = '', parentType = '') {
  if (!model) return null;

  // If model already has children array (new format with IED/LD/LN/DA hierarchy)
  if (model.children && Array.isArray(model.children)) {
    const name = model.name || model.iedName || 'Root';
    const type = model.type || model.kind || 'IED';

    // Preserve an explicit ref if the payload already provides one; otherwise
    // build it ourselves using ACSI-correct separators.
    const ref = model.ref !== undefined ? model.ref : buildChildRef(parentRef, parentType, name);

    const node = {
      name,
      type,
      ref,
      children: model.children.map(child => transformModelToTree(child, ref, type)),
    };

    // Preserve fc, cdc, bType, value and other Tree component properties
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
      children: model.server.logicalDevices.map(ld => {
        const ldName = typeof ld === 'object' ? ld.name : ld;
        return {
          name: ldName,
          type: 'LDevice',
          ref: ldName, // LD ref is just its own name, no IED prefix
          children: [],
        };
      }),
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
        children: typeof value === 'object' ? Object.keys(value).map(k => ({ name: k, type: 'Data' })) : [],
      })),
    };
  }

  return model;
}

export default { transformModelToTree };