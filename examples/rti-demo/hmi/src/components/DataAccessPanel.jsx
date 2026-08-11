import React, { useState, useEffect, useCallback, useMemo } from 'react';
import { executeApiCall, buildTargetValue } from '../services/apiService';

/**
 * DataAccessPanel - A reusable component for reading and writing data from ACSI endpoints
 * 
 * Features:
 * - Dropdown to select connected endpoint
 * - Cascading dropdowns for LD (Logical Devices), LN (Logical Nodes), DO (Data Objects), DA (Data Attributes)
 * - Read button to fetch data value
 * - Write button to write data value
 * - Displays results of operations
 * 
 * @param {Object} props
 * @param {Object[]} props.connections - Array of connection objects with host, port, name, type, status
 * @param {Function} props.getModel - Function to retrieve cached model by endpoint target
 * @param {Object} props.settings - BFF settings with bffHost and bffPort
 * @param {string} props.cp - The control point/access point identifier
 */
function DataAccessPanel({ connections, getModel, settings, cp = 'cp1' }) {
  // State for selections
  const [selectedTarget, setSelectedTarget] = useState('');
  const [selectedLD, setSelectedLD] = useState('');
  const [selectedLN, setSelectedLN] = useState('');
  const [selectedDO, setSelectedDO] = useState('');
  const [selectedDA, setSelectedDA] = useState('');
  const [selectedFC, setSelectedFC] = useState('');
  
  // State for available options (populated from model)
  const [availableLDs, setAvailableLDs] = useState([]);
  const [availableLNs, setAvailableLNs] = useState([]);
  const [availableDOs, setAvailableDOs] = useState([]);
  const [availableDAs, setAvailableDAs] = useState([]);
  
  // State for data operations
  const [readResult, setReadResult] = useState(null);
  const [writeResult, setWriteResult] = useState(null);
  const [writeValue, setWriteValue] = useState('');
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  
  // Local cache for fetched DAs (DO reference -> array of DA names)
  const [daCache, setDaCache] = useState({});

  // Get connected endpoints
  const connectedEndpoints = useMemo(() => {
    return connections.filter(conn => conn.status === 'connected');
  }, [connections]);

  // Extract hierarchy from model data
  const extractHierarchyFromModel = useCallback((modelData) => {
    const hierarchy = { lds: [], lns: {}, dos: {}, das: {} };
    
    if (!modelData) return hierarchy;
    
    try {
      // Handle different model structures - normalize to the actual model object
      let data = modelData;
      
      // The stored model could be:
      // 1. Full API response: { ok: true, result: { server: {...}, logicalDeviceMap: {...}, logicalNodeDetails: {...} } }
      // 2. Just the result: { server: {...}, logicalDeviceMap: {...}, logicalNodeDetails: {...} }
      // 3. Tree structure: { tree: {...} } or { kind: 'Server', children: [...] }
      
      // Try to get to the actual model data
      if (data?.result?.server?.logicalDevices) {
        data = data.result;
      } else if (data?.result?.model?.server?.logicalDevices) {
        data = data.result.model;
      } else if (data?.result?.tree?.children) {
        data = data.result;
      } else if (data?.result?.model) {
        data = data.result.model;
      } else if (data?.model?.server?.logicalDevices) {
        data = data.model;
      } else if (data?.model?.tree?.children) {
        data = data.model;
      } else if (data?.model) {
        data = data.model;
      }
      
      // Extract from model.tree structure (ACSIServer format with kind/name/children)
      // This is the most complete format with full hierarchy including DAs
      if (data?.tree?.children) {
        // Extract from tree structure
        const tree = data.tree;
        if (tree.kind === 'IED' || tree.kind === 'Server' || tree.kind === 'server') {
          // Tree root is IED or Server, children are LDs
          tree.children.forEach(node => {
            if (node.kind === 'LD' || node.kind === 'LDevice') {
              hierarchy.lds.push(node.name);
              extractFromKindTree(node, node.name, 'LD', hierarchy);
            }
          });
        } else if (tree.kind === 'LD' || tree.kind === 'LDevice') {
          hierarchy.lds.push(tree.name);
          extractFromKindTree(tree, tree.name, 'LD', hierarchy);
        }
        return hierarchy;
      }
      
      // Also check if tree is at the root level (not under model)
      if (data?.children && (data.kind === 'IED' || data.kind === 'Server' || data.kind === 'server')) {
        data.children.forEach(node => {
          if (node.kind === 'LD' || node.kind === 'LDevice') {
            hierarchy.lds.push(node.name);
            extractFromKindTree(node, node.name, 'LD', hierarchy);
          }
        });
        return hierarchy;
      }
      
      // Extract from server.logicalDevices structure (ACSI Client model-tree)
      if (data?.server?.logicalDevices) {
        const lds = data.server.logicalDevices || [];
        const logicalDeviceMap = data.logicalDeviceMap || {};
        const logicalNodeDetails = data.logicalNodeDetails || {};
        
        hierarchy.lds = lds.map(ld => typeof ld === 'object' ? ld.name : String(ld));
        
        // Build LN, DO, DA maps
        lds.forEach(ld => {
          const ldName = typeof ld === 'object' ? ld.name : String(ld);
          const lns = logicalDeviceMap[ldName] || [];
          hierarchy.lns[ldName] = lns.map(ln => typeof ln === 'object' ? ln.name : String(ln));
          
          lns.forEach(ln => {
            const lnName = typeof ln === 'object' ? ln.name : String(ln);
            const lnRef = `${ldName}/${lnName}`;
            const details = logicalNodeDetails[lnRef] || {};
            
            // Get DOs from dataObjects
            const dos = details.dataObjects || ln.dataObjects || ln.do || [];
            hierarchy.dos[lnRef] = dos.map(doObj => typeof doObj === 'object' ? doObj.name : String(doObj));
            
            // Try to get DAs from dataAttributes array (if available)
            const daList = details.dataAttributes || [];
            if (daList.length > 0) {
              // dataAttributes is an array of strings like "DOName.DAName"
              const daByDo = {};
              daList.forEach(daRef => {
                const parts = String(daRef).split('.');
                if (parts.length >= 2) {
                  const doName = parts[0];
                  const daName = parts.slice(1).join('.');
                  if (!daByDo[doName]) daByDo[doName] = [];
                  daByDo[doName].push(daName);
                }
              });
              
              // Store DAs by DO
              dos.forEach(doObj => {
                const doName = typeof doObj === 'object' ? doObj.name : String(doObj);
                const doRef = `${lnRef}.${doName}`;
                hierarchy.das[doRef] = daByDo[doName] || [];
              });
            } else {
              // Fallback: try to extract from dataObjects if they have da/daList
              dos.forEach(doObj => {
                const doName = typeof doObj === 'object' ? doObj.name : String(doObj);
                const doRef = `${lnRef}.${doName}`;
                const das = (doObj.data_attributes || doObj.dataAttributes || doObj.da || []).map(da => 
                  typeof da === 'object' ? da.name : String(da)
                );
                hierarchy.das[doRef] = das;
              });
            }
          });
        });
      }
      // Extract from tree structure (if model was transformed to tree with type/name/children)
      else if (data?.children) {
        data.children.forEach(node => {
          const nodeKind = node.kind || node.type;
          const nodeType = node.type || node.kind;
          
          if (nodeKind === 'LDevice' || nodeKind === 'LD' || nodeType === 'LDevice' || nodeType === 'server' || nodeType === 'Server') {
            // Handle root server node
            if (nodeType === 'server' || nodeType === 'Server' || nodeKind === 'Server') {
              node.children?.forEach(child => {
                const childKind = child.kind || child.type;
                const childType = child.type || child.kind;
                if (childKind === 'LDevice' || childKind === 'LD' || childType === 'LDevice') {
                  hierarchy.lds.push(child.name);
                  extractChildrenFromTree(child, child.name, 'LD', hierarchy);
                }
              });
            } else {
              hierarchy.lds.push(node.name);
              extractChildrenFromTree(node, node.name, 'LD', hierarchy);
            }
          } else if (nodeKind === 'IED' || nodeKind === 'Server' || nodeType === 'IED' || nodeType === 'Server') {
            // Also check for IED type nodes
            if (node.name && !hierarchy.lds.includes(node.name)) {
              hierarchy.lds.push(node.name);
            }
            // Extract children as LNs
            if (node.children) {
              node.children.forEach(child => {
                const childKind = child.kind || child.type;
                const childType = child.type || child.kind;
                if (childKind === 'LDevice' || childKind === 'LD' || childType === 'LDevice' || childType === 'LN' || childType === 'LogicalNode') {
                  const lnName = child.name || '';
                  if (lnName && !hierarchy.lns[node.name]) {
                    hierarchy.lns[node.name] = [];
                  }
                  if (lnName) {
                    hierarchy.lns[node.name].push(lnName);
                  }
                  extractChildrenFromTree(child, `${node.name}/${lnName}`, 'LN', hierarchy);
                }
              });
            }
          }
        });
      }
      // Extract from iedName/accessPoints structure
      else if (data?.accessPoints) {
        data.accessPoints.forEach(ap => {
          const apName = typeof ap === 'object' ? ap.name : String(ap);
          hierarchy.lds.push(apName);
          // Check for ldevices in access point
          if (ap.ldevices) {
            ap.ldevices.forEach(ld => {
              const ldName = typeof ld === 'object' ? ld.name : String(ld);
              // Add LNs if available
              if (ld.lnodes || ld.LN) {
                const lns = ld.lnodes || ld.LN || [];
                hierarchy.lns[ldName] = lns.map(ln => {
                  const lnName = typeof ln === 'object' ? ln.name : String(ln);
                  // Extract DOs and DAs from LNode
                  if (ln.dataObjects || ln.do || ln.DO) {
                    const lnRef = `${ldName}/${lnName}`;
                    const dos = (ln.dataObjects || ln.do || ln.DO || []).map(doObj => {
                      const doName = typeof doObj === 'object' ? doObj.name : String(doObj);
                      return doName;
                    });
                    hierarchy.dos[lnRef] = dos;
                    
                    dos.forEach((doName, idx) => {
                      const doObj = (ln.dataObjects || ln.do || ln.DO || [])[idx];
                      const doRef = `${lnRef}.${doName}`;
                      const das = (doObj.data_attributes || doObj.dataAttributes || doObj.da || []).map(da => 
                        typeof da === 'object' ? da.name : String(da)
                      );
                      hierarchy.das[doRef] = das;
                    });
                  }
                  return lnName;
                });
              }
            });
          }
        });
      }
      // Also try to extract from result.model.server structure (BFF response)
      else if (data?.result?.model?.server?.logicalDevices) {
        data = data.result.model;
        // Recursively process
        return extractHierarchyFromModel(data);
      }
    } catch (e) {
      // Silent error handling - model structure not recognized
    }
    
    return hierarchy;
  }, []);

  // Helper to extract from tree structure with kind/name/children (Server format)
  const extractFromKindTree = useCallback((node, parentRef, parentType, hierarchy) => {
    if (!node.children) return;
    
    node.children.forEach(child => {
      if (!child.name) return;
      
      const childRef = parentType === 'LD' ? `${parentRef}/${child.name}` : parentRef;
      
      if (child.kind === 'LN' || child.kind === 'LogicalNode') {
        // Add LN under parent (which should be LD)
        if (!hierarchy.lns[parentRef]) {
          hierarchy.lns[parentRef] = [];
        }
        if (!hierarchy.lns[parentRef].includes(child.name)) {
          hierarchy.lns[parentRef].push(child.name);
        }
        
        // Extract DOs and DAs from LN children
        const lnRef = parentType === 'LD' ? `${parentRef}/${child.name}` : parentRef;
        child.children?.forEach(doNode => {
          if (doNode.kind === 'DO' || doNode.kind === 'DataObject' || doNode.kind === 'SDO') {
            // Store DO under LN
            if (!hierarchy.dos[lnRef]) {
              hierarchy.dos[lnRef] = [];
            }
            if (!hierarchy.dos[lnRef].includes(doNode.name)) {
              hierarchy.dos[lnRef].push(doNode.name);
            }
            
            // Extract DAs from DO children
            const doRef = `${lnRef}.${doNode.name}`;
            const das = [];
            doNode.children?.forEach(daNode => {
              if (daNode.kind === 'DA' || daNode.kind === 'DataAttribute' || daNode.kind === 'SDA') {
                das.push(daNode.name);
              }
            });
            hierarchy.das[doRef] = das;
          }
        });
        
        // Recurse into LN
        extractFromKindTree(child, lnRef, 'LN', hierarchy);
      }
      else if (child.kind === 'LD' || child.kind === 'LDevice') {
        // Handle nested LDs
        if (!hierarchy.lds.includes(child.name)) {
          hierarchy.lds.push(child.name);
        }
        extractFromKindTree(child, child.name, 'LD', hierarchy);
      }
    });
  }, []);

  // Helper to extract children from tree nodes
  const extractChildrenFromTree = useCallback((node, parentRef, parentType, hierarchy) => {
    if (!node.children) return;
    
    node.children.forEach(child => {
      if (!child.name) return;
      
      const childType = child.type || child.kind;
      const childKind = child.kind || child.type;
      
      // Handle LogicalNode
      if (childType === 'LogicalNode' || childType === 'LN' || childKind === 'LN' || childKind === 'LogicalNode') {
        // Add to LNs under current LD
        if (!hierarchy.lns[parentRef]) {
          hierarchy.lns[parentRef] = [];
        }
        hierarchy.lns[parentRef].push(child.name);
        extractChildrenFromTree(child, `${parentRef}/${child.name}`, 'LN', hierarchy);
      }
      // Handle LDevice (can be nested under Server)
      else if (childType === 'LDevice' || childKind === 'LDevice' || childKind === 'LD') {
        // Add to LDs
        if (!hierarchy.lds.includes(child.name)) {
          hierarchy.lds.push(child.name);
        }
        // Extract children for this LD
        extractChildrenFromTree(child, child.name, 'LD', hierarchy);
      }
      // Handle DO, DataObject, SDO
      else if (childType === 'DO' || childType === 'DataObject' || childType === 'SDO' || childKind === 'DO' || childKind === 'DataObject' || childKind === 'SDO') {
        // Determine the parent reference for storing DOs
        // parentRef should be LD/LN for DO under LN, or LD for DO under LD
        const doParentRef = parentType === 'LN' ? parentRef : (parentType === 'LD' ? parentRef : parentRef);
        
        if (!hierarchy.dos[doParentRef]) {
          hierarchy.dos[doParentRef] = [];
        }
        hierarchy.dos[doParentRef].push(child.name);
        
        // For DO reference, use dot notation: LD/LN.DO or LD.DO
        const currentRef = parentType === 'LN' ? `${parentRef}.${child.name}` : `${parentRef}.${child.name}`;
        extractChildrenFromTree(child, currentRef, 'DO', hierarchy);
      }
      // Handle DA, DataAttribute, SDA
      else if (childType === 'DA' || childType === 'DataAttribute' || childType === 'SDA' || childKind === 'DA' || childKind === 'DataAttribute' || childKind === 'SDA') {
        // Store DAs under the DO reference (parentRef)
        const doRef = parentRef || '';
        if (!hierarchy.das[doRef]) {
          hierarchy.das[doRef] = [];
        }
        hierarchy.das[doRef].push(child.name);
      }
      // Handle Group nodes - recurse but keep parent type
      else if (childType === 'Group' || childType === 'DataSet' || childType === 'ReportControl' || childKind === 'Group' || childKind === 'DataSet' || childKind === 'ReportControl') {
        extractChildrenFromTree(child, parentRef, parentType, hierarchy);
      }
      // For other types (Server, etc.) - recurse with appropriate type
      else {
        // If it's a server node with children, extract LDs
        if (childType === 'Server' || childType === 'server' || childKind === 'Server' || childKind === 'server') {
          child.children?.forEach(c => {
            const cType = c.type || c.kind;
            const cKind = c.kind || c.type;
            if (cType === 'LDevice' || cKind === 'LDevice' || cKind === 'LD') {
              if (!hierarchy.lds.includes(c.name)) {
                hierarchy.lds.push(c.name);
              }
              extractChildrenFromTree(c, c.name, 'LD', hierarchy);
            }
          });
        }
        extractChildrenFromTree(child, parentRef, parentType, hierarchy);
      }
    });
  }, []);

  // Populate dropdowns when endpoint or parent selection changes
  useEffect(() => {
    const updateDropdowns = () => {
      if (!selectedTarget) {
        setAvailableLDs([]);
        setAvailableLNs([]);
        setAvailableDOs([]);
        setAvailableDAs([]);
        return;
      }
      
      // Get model for this endpoint
      const modelData = getModel ? getModel(selectedTarget) : null;
      
      const hierarchy = extractHierarchyFromModel(modelData);
      
      setAvailableLDs(hierarchy.lds);
      
      // Reset selections when endpoint changes
      setSelectedLD('');
      setSelectedLN('');
      setSelectedDO('');
      setSelectedDA('');
    };
    
    updateDropdowns();
  }, [selectedTarget, getModel, extractHierarchyFromModel]);

  // Update LN dropdown when LD changes
  useEffect(() => {
    if (!selectedLD || !selectedTarget) {
      setAvailableLNs([]);
      setSelectedLN('');
      setSelectedDO('');
      setSelectedDA('');
      return;
    }
    
    const modelData = getModel ? getModel(selectedTarget) : null;
    const hierarchy = extractHierarchyFromModel(modelData);
    
    setAvailableLNs(hierarchy.lns[selectedLD] || []);
  }, [selectedLD, selectedTarget, getModel, extractHierarchyFromModel]);

  // Update DO dropdown when LN changes
  useEffect(() => {
    if (!selectedLN || !selectedLD || !selectedTarget) {
      setAvailableDOs([]);
      setSelectedDO('');
      setSelectedDA('');
      return;
    }
    
    const lnRef = `${selectedLD}/${selectedLN}`;
    const modelData = getModel ? getModel(selectedTarget) : null;
    const hierarchy = extractHierarchyFromModel(modelData);
    
    setAvailableDOs(hierarchy.dos[lnRef] || []);
  }, [selectedLN, selectedLD, selectedTarget, getModel, extractHierarchyFromModel]);

  // Update DA dropdown when DO changes
  useEffect(() => {
    if (!selectedDO || !selectedLN || !selectedLD || !selectedTarget) {
      setAvailableDAs([]);
      setSelectedDA('');
      setSelectedFC('');
      return;
    }
    
    const doRef = `${selectedLD}/${selectedLN}.${selectedDO}`;
    const modelData = getModel ? getModel(selectedTarget) : null;
    const hierarchy = extractHierarchyFromModel(modelData);
    
    // Check hierarchy first (from model tree structure)
    const cachedDas = hierarchy.das[doRef] || [];
    if (cachedDas.length > 0) {
      setAvailableDAs(cachedDas);
      return;
    }
    
    // Check local DA cache
    if (daCache[doRef]) {
      setAvailableDAs(daCache[doRef].map(d => d.name));
      return;
    }
    
    // Otherwise, fetch DA definition from API
    const fetchDAsForDO = async () => {
      try {
        // Extract path components for API call
        const ldName = selectedLD;
        const lnName = selectedLN;
        const doPath = selectedDO;
        
        // Try to get cp from the selected connection, fall back to prop or default
        const selectedConnection = connectedEndpoints.find(conn => buildTargetValue(conn.host, conn.port) === selectedTarget);
        const effectiveCp = selectedConnection?.cp || cp || 'cp1';
        
        // Use the standard BFF execute endpoint - it will add method, path, target automatically
        const result = await executeApiCall('data-definition', selectedTarget, {
          cp: effectiveCp,
          ld_inst: ldName,
          ln_inst: lnName,
          do_path: doPath,
        });
        
        if (result?.ok && result.payload) {
          // Extract DAs from various possible response structures
          let dataAttributes = [];
          
          // Debug logging
          console.log('[DataAccessPanel] DA definition API response:', result.payload);
          console.log('[DataAccessPanel] Full result:', result);
          
          // Try different paths for dataAttributeDefinition
          const payload = result.payload;
          
          // Path 1: payload.result.value.dataAttributeDefinition
          if (payload.result?.value?.dataAttributeDefinition) {
            dataAttributes = payload.result.value.dataAttributeDefinition;
          }
          // Path 2: payload.value.dataAttributeDefinition
          else if (payload.value?.dataAttributeDefinition) {
            dataAttributes = payload.value.dataAttributeDefinition;
          }
          // Path 3: payload.dataAttributeDefinition (direct at payload level)
          else if (payload.dataAttributeDefinition) {
            dataAttributes = payload.dataAttributeDefinition;
          }
          // Path 4: payload.result.dataAttributeDefinition
          else if (payload.result?.dataAttributeDefinition) {
            dataAttributes = payload.result.dataAttributeDefinition;
          }
          // Path 5: payload.data (sometimes the data is wrapped in a data field)
          else if (payload.data?.dataAttributeDefinition) {
            dataAttributes = payload.data.dataAttributeDefinition;
          }
          // Path 6: payload.value is an array of DA objects
          else if (Array.isArray(payload.value)) {
            dataAttributes = payload.value;
          }
          // Path 7: payload is an array of DA objects
          else if (Array.isArray(payload)) {
            dataAttributes = payload;
          }
          // Path 8: Check if payload.value has a different structure
          else if (payload.value && typeof payload.value === 'object' && !Array.isArray(payload.value)) {
            // Maybe the DAs are in a different field
            dataAttributes = payload.value.dataAttributes || 
                           payload.value.daList || 
                           payload.value.das || 
                           payload.value.attributes || [];
          }
          // Path 9: Check payload.result.value as array
          else if (Array.isArray(payload.result?.value)) {
            dataAttributes = payload.result.value;
          }
          
          console.log('[DataAccessPanel] Extracted dataAttributes:', dataAttributes);
          
          // Extract DA names and types
          const das = dataAttributes.map(da => {
            if (typeof da === 'string') return { name: da, daType: null };
            if (typeof da === 'object' && da !== null) {
              const daName = da.name || da.daRef?.split('.').pop() || da.id || 'DA';
              const daType = Array.isArray(da.daType) ? da.daType[0] : da.daType;
              return { name: daName, daType: daType || null };
            }
            return { name: 'DA', daType: null };
          });
          
          console.log('[DataAccessPanel] Extracted DAs:', das);
          
          // Cache the DAs locally with type information
          setDaCache(prev => ({ ...prev, [doRef]: das }));
          setAvailableDAs(das.map(d => d.name));
        } else {
          console.log('[DataAccessPanel] API call failed or no payload');
          setAvailableDAs([]);
        }
      } catch (error) {
        setAvailableDAs([]);
      }
    };
    
    fetchDAsForDO();
  }, [selectedDO, selectedLN, selectedLD, selectedTarget, getModel, extractHierarchyFromModel, cp, connectedEndpoints, daCache]);

  // Update FC when DA changes
  useEffect(() => {
    if (!selectedDA || !selectedDO || !selectedLN || !selectedLD || !selectedTarget) {
      setSelectedFC('');
      return;
    }
    
    const modelData = getModel ? getModel(selectedTarget) : null;
    if (!modelData) {
      setSelectedFC('');
      return;
    }
    
    // Try to find the DA node in the model and extract its fc
    const fc = findNodeFC(modelData, selectedLD, selectedLN, selectedDO, selectedDA);
    setSelectedFC(fc || '');
  }, [selectedDA, selectedDO, selectedLN, selectedLD, selectedTarget, getModel]);

  // Helper to find the fc of a specific DA in the model tree
  const findNodeFC = useCallback((modelData, ldName, lnName, doName, daName) => {
    if (!modelData) return null;
    
    try {
      let data = modelData;
      
      // Normalize to the actual model object
      if (data?.result?.model) {
        data = data.result.model;
      } else if (data?.model) {
        data = data.model;
      } else if (data?.tree) {
        data = data.tree;
      }
      
      // Handle tree structure with children
      if (data?.children) {
        // Find the LD
        const ldNode = data.children?.find(n => (n.name === ldName) || (n.kind === 'LD' && n.name === ldName));
        if (ldNode) {
          // Find the LN under LD
          const lnNode = ldNode.children?.find(n => n.name === lnName);
          if (lnNode) {
            // Find the DO under LN
            const doNode = lnNode.children?.find(n => n.name === doName);
            if (doNode) {
              // Find the DA under DO
              const daNode = doNode.children?.find(n => n.name === daName);
              if (daNode) {
                return daNode.fc || daNode.Fc || daNode.FC || '';
              }
            }
          }
        }
        
        // Also try if the root is the IED/Server directly
        if (data.name === ldName || data.kind === 'IED') {
          const lnNode = data.children?.find(n => n.name === lnName);
          if (lnNode) {
            const doNode = lnNode.children?.find(n => n.name === doName);
            if (doNode) {
              const daNode = doNode.children?.find(n => n.name === daName);
              if (daNode) {
                return daNode.fc || daNode.Fc || daNode.FC || '';
              }
            }
          }
        }
      }
      
      // Handle server.logicalDevices structure
      if (data?.server?.logicalDevices) {
        const ld = data.server.logicalDevices.find(ld => ld.name === ldName || ld === ldName);
        if (ld) {
          const ldNameActual = typeof ld === 'object' ? ld.name : ld;
          const logicalDeviceMap = data.logicalDeviceMap || {};
          const logicalNodeDetails = data.logicalNodeDetails || {};
          const lns = logicalDeviceMap[ldNameActual] || [];
          const ln = lns.find(ln => ln.name === lnName || ln === lnName);
          if (ln) {
            const lnNameActual = typeof ln === 'object' ? ln.name : ln;
            const lnRef = `${ldNameActual}/${lnNameActual}`;
            const details = logicalNodeDetails[lnRef] || {};
            const dos = details.dataObjects || ln.dataObjects || ln.do || [];
            const doObj = dos.find(doItem => doItem.name === doName || doItem === doName);
            if (doObj) {
              const das = doObj.dataAttributes || doObj.data_attributes || doObj.da || [];
              const daObj = das.find(daItem => daItem.name === daName || daItem === daName);
              if (daObj) {
                return daObj.fc || daObj.Fc || daObj.FC || '';
              }
            }
          }
        }
      }
    } catch (e) {
      console.error('Failed to find node FC:', e);
      return null;
    }
    
    return null;
  }, []);

  // Format values for display
  const formatValuesForDisplay = useCallback((result) => {
    if (!result) return null;
    
    // Extract values from various possible locations
    let values = result?.result?.values || result?.values || result?.payload?.result?.values || result?.payload?.values;
    
    if (!values || !Array.isArray(values)) {
      // If it's not an array, try to display it as-is
      if (result?.result?.value !== undefined) {
        return { type: typeof result.result.value, value: result.result.value };
      }
      if (result?.value !== undefined) {
        return { type: typeof result.value, value: result.value };
      }
      return result;
    }
    
    // If there's only one value, return it directly
    if (values.length === 1) {
      return values[0];
    }
    
    // If multiple values, return the array
    return values;
  }, []);

  // Build object reference from selections
  const buildObjectRef = useCallback(() => {
    if (!selectedLD || !selectedLN || !selectedDO || !selectedDA) {
      return '';
    }
    return `${selectedLD}/${selectedLN}.${selectedDO}.${selectedDA}`;
  }, [selectedLD, selectedLN, selectedDO, selectedDA]);

  // Handle read operation
  const handleRead = useCallback(async () => {
    if (!selectedTarget) {
      setError('Please select an endpoint first');
      return;
    }
    
    const objRef = buildObjectRef();
    if (!objRef) {
      setError('Please select LD, LN, DO, and DA first');
      return;
    }
    
    setLoading(true);
    setError(null);
    setReadResult(null);
    
    try {
      // Get cp from the selected connection if it's an ACSI client
      const selectedConnection = connectedEndpoints.find(conn => buildTargetValue(conn.host, conn.port) === selectedTarget);
      const effectiveCp = selectedConnection?.cp || cp || 'cp1';
     
      // Add cp to body for ACSI client endpoints
      const isAcsiClient = selectedConnection?.acsi === 'client';
      const body = {
        objRef: objRef,
        fc: selectedFC.toLowerCase() || 'st'
      };
      if (isAcsiClient) {
        body.cp = effectiveCp;
      }
      
      const result = await executeApiCall('read', selectedTarget, body);
      
      if (result?.ok) {
        setReadResult(result.payload);
      } else {
        setError(result?.payload?.error || result?.rawText || 'Failed to read value');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [selectedTarget, buildObjectRef, selectedFC, connections, cp]);

  // Handle write operation
  const handleWrite = useCallback(async () => {
    if (!selectedTarget) {
      setError('Please select an endpoint first');
      return;
    }
    
    const objRef = buildObjectRef();
    if (!objRef) {
      setError('Please select LD, LN, DO, and DA first');
      return;
    }
    
    if (!writeValue) {
      setError('Please enter a value to write');
      return;
    }
    
    setLoading(true);
    setError(null);
    setWriteResult(null);
    
    try {
      // Get cp from the selected connection if it's an ACSI client
      const selectedConnection = connectedEndpoints.find(conn => buildTargetValue(conn.host, conn.port) === selectedTarget);
      const effectiveCp = selectedConnection?.cp || cp || 'cp1';
      
      // Add cp to body for ACSI client endpoints
      const isAcsiClient = selectedConnection?.acsi === 'client';
      
      // Get the daType for the selected DA
      const doRef = `${selectedLD}/${selectedLN}.${selectedDO}`;
      const daInfo = daCache[doRef]?.find(da => da.name === selectedDA);
      const valueType = daInfo?.daType;
      
      const body = {
        objRef: objRef,
        value: writeValue,
        fc: selectedFC.toLowerCase() || 'st'
      };
      if (valueType) {
        body.dataType = valueType;
      }
      if (isAcsiClient) {
        body.cp = effectiveCp;
      }
      
      const result = await executeApiCall('write', selectedTarget, body);
      
      if (result?.ok) {
        setWriteResult(result.payload);
      } else {
        setError(result?.payload?.error || result?.rawText || 'Failed to write value');
      }
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  }, [selectedTarget, buildObjectRef, writeValue, selectedFC, connections, cp, daCache, selectedLD, selectedLN, selectedDO, selectedDA]);

  // Reset selections and results
  const handleReset = useCallback(() => {
    setSelectedTarget('');
    setSelectedLD('');
    setSelectedLN('');
    setSelectedDO('');
    setSelectedDA('');
    setWriteValue('');
    setReadResult(null);
    setWriteResult(null);
    setError(null);
  }, []);

  return (
    <div style={{ 
      border: '1px solid var(--border-color)', 
      borderRadius: '8px', 
      padding: '16px',
      background: 'var(--bg-card)'
    }}>
      <h3 style={{ margin: 0, marginBottom: '16px', color: 'var(--text-secondary)' }}>
        {selectedTarget ? (
          connectedEndpoints.find(c => buildTargetValue(c.host, c.port) === selectedTarget)?.acsi === 'client' 
            ? 'ACSI Client - Read or write to ACSI Server'
            : 'Read or write to ACSI Server'
        ) : 'Data Access'}
      </h3>
      
      {/* Endpoint Selection */}
      <div style={{ marginBottom: '12px' }}>
        <label style={{ display: 'block', marginBottom: '4px', fontSize: '12px', color: 'var(--text-muted)' }}>
          Endpoint
        </label>
        <select
          value={selectedTarget}
          onChange={(e) => setSelectedTarget(e.target.value)}
          style={{ width: '100%', padding: '8px', borderRadius: '4px', background: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}
          disabled={connectedEndpoints.length === 0}
        >
          <option value="">Select connected endpoint...</option>
          {connectedEndpoints.map(conn => (
            <option key={buildTargetValue(conn.host, conn.port)} value={buildTargetValue(conn.host, conn.port)}>
              {conn.name || `${conn.host}:${conn.port}`} ({conn.type})
            </option>
          ))}
        </select>
        {selectedTarget && (
          <div style={{ 
            marginTop: '4px', 
            fontSize: '11px', 
            color: 'var(--text-muted)',
            fontStyle: 'italic'
          }}>
            ACSI: {connectedEndpoints.find(c => buildTargetValue(c.host, c.port) === selectedTarget)?.acsi || 'Unknown'}
          </div>
        )}
      </div>
      
      {/* Cascading Dropdowns */}
      <div style={{ display: 'grid', gridTemplateColumns: 'repeat(4, 1fr)', gap: '12px', marginBottom: '12px' }}>
        {/* LD - Logical Device */}
        <div>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: '12px', color: 'var(--text-muted)' }}>
            LD (Logical Device)
          </label>
          <select
            value={selectedLD}
            onChange={(e) => setSelectedLD(e.target.value)}
            style={{ width: '100%', padding: '8px', borderRadius: '4px', background: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}
            disabled={!selectedTarget || availableLDs.length === 0}
          >
            <option value="">Select LD...</option>
            {availableLDs.map(ld => (
              <option key={String(ld)} value={ld}>{ld}</option>
            ))}
          </select>
        </div>
        
        {/* LN - Logical Node */}
        <div>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: '12px', color: 'var(--text-muted)' }}>
            LN (Logical Node)
          </label>
          <select
            value={selectedLN}
            onChange={(e) => setSelectedLN(e.target.value)}
            style={{ width: '100%', padding: '8px', borderRadius: '4px', background: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}
            disabled={!selectedLD || availableLNs.length === 0}
          >
            <option value="">Select LN...</option>
            {availableLNs.map(ln => (
              <option key={String(ln)} value={ln}>{ln}</option>
            ))}
          </select>
        </div>
        
        {/* DO - Data Object */}
        <div>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: '12px', color: 'var(--text-muted)' }}>
            DO (Data Object)
          </label>
          <select
            value={selectedDO}
            onChange={(e) => setSelectedDO(e.target.value)}
            style={{ width: '100%', padding: '8px', borderRadius: '4px', background: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}
            disabled={!selectedLN || availableDOs.length === 0}
          >
            <option value="">Select DO...</option>
            {availableDOs.map(doObj => (
              <option key={String(doObj)} value={doObj}>{doObj}</option>
            ))}
          </select>
        </div>
        
        {/* DA - Data Attribute */}
        <div>
          <label style={{ display: 'block', marginBottom: '4px', fontSize: '12px', color: 'var(--text-muted)' }}>
            DA (Data Attribute)
          </label>
          <select
            value={selectedDA}
            onChange={(e) => setSelectedDA(e.target.value)}
            style={{ width: '100%', padding: '8px', borderRadius: '4px', background: 'var(--bg-hover)', border: '1px solid var(--border-color)' }}
            disabled={!selectedDO || availableDAs.length === 0}
          >
            <option value="">Select DA...</option>
            {availableDAs.map(da => (
              <option key={String(da)} value={da}>{da}</option>
            ))}
          </select>
        </div>
      </div>
      
      {/* Object Reference Display */}
      {selectedLD && selectedLN && selectedDO && selectedDA && (
        <div style={{ 
          marginBottom: '16px', 
          padding: '8px 12px', 
          background: 'var(--bg-hover)', 
          borderRadius: '4px',
          fontFamily: 'monospace',
          fontSize: '13px',
          color: 'var(--text-secondary)'
        }}>
          Object Reference: {buildObjectRef()}
        </div>
      )}
      
      {/* Write Value Input */}
      <div style={{ marginBottom: '16px' }}>
        <label style={{ display: 'block', marginBottom: '4px', fontSize: '12px', color: 'var(--text-muted)' }}>
          Value to Write
        </label>
        <input
          type="text"
          value={writeValue}
          onChange={(e) => setWriteValue(e.target.value)}
          placeholder="Enter value (e.g., true, 100, 'text')"
          style={{ 
            width: '100%', 
            padding: '8px', 
            borderRadius: '4px', 
            background: 'var(--bg-hover)', 
            border: '1px solid var(--border-color)'
          }}
        />
      </div>
      
      {/* Action Buttons */}
      <div style={{ display: 'flex', gap: '8px', marginBottom: '16px' }}>
        <button
          onClick={handleRead}
          disabled={!selectedDA || loading}
          className="btn-primary"
          style={{ flex: 1 }}
        >
          {loading ? 'Reading...' : 'Read'}
        </button>
        <button
          onClick={handleWrite}
          disabled={!selectedDA || !writeValue || loading}
          className="btn-secondary"
          style={{ flex: 1 }}
        >
          {loading ? 'Writing...' : 'Write'}
        </button>
        <button
          onClick={handleReset}
          disabled={loading}
          className="btn-secondary"
          style={{ padding: '8px 12px' }}
          title="Clear selections"
        >
          <i className="fas fa-times"></i>
        </button>
      </div>
      
      {/* Results Display */}
      {error && (
        <div style={{ 
          padding: '12px', 
          background: 'var(--danger-bg)', 
          color: 'var(--danger-color)', 
          borderRadius: '4px',
          marginBottom: '12px',
          fontSize: '13px'
        }}>
          <i className="fas fa-exclamation-circle" style={{ marginRight: '8px' }}></i>
          {error}
        </div>
      )}
      
      {readResult && (
        <div style={{ 
          padding: '12px', 
          background: 'var(--info-bg)', 
          color: 'var(--info-color)', 
          borderRadius: '4px',
          marginBottom: '12px'
        }}>
          <strong style={{ display: 'block', marginBottom: '4px' }}>Read Result:</strong>
          <div style={{ fontFamily: 'monospace', fontSize: '12px' }}>
            {(() => {
              const formatted = formatValuesForDisplay(readResult);
              if (!formatted) return null;
              
              if (Array.isArray(formatted)) {
                return formatted.map((v, i) => (
                  <div key={i} style={{ marginBottom: '4px' }}>
                    Type: <strong>{v.type}</strong>, Value: <strong>{JSON.stringify(v.value)}</strong>
                  </div>
                ));
              }
              
              // Single value object
              return <div>
                Type: <strong>{formatted.type}</strong>, Value: <strong>{JSON.stringify(formatted.value)}</strong>
              </div>;
            })()}
          </div>
        </div>
      )}
      
      {writeResult && (
        <div style={{ 
          padding: '12px', 
          background: 'var(--success-bg)', 
          color: 'var(--success-color)', 
          borderRadius: '4px',
          marginBottom: '12px'
        }}>
          <strong style={{ display: 'block', marginBottom: '4px' }}>Write Result:</strong>
          <div style={{ fontFamily: 'monospace', fontSize: '12px' }}>
            {(() => {
              const success = writeResult?.result?.success ?? writeResult?.payload?.result?.success ?? writeResult?.success;
              const value = writeResult?.result?.value ?? writeResult?.payload?.result?.value ?? writeResult?.value;
              return <div>
                Status: <strong style={{ color: success ? 'var(--success-color)' : 'var(--danger-color)' }}>
                  {success ? 'Success' : 'Failed'}
                </strong>
                {value !== undefined && <>, Value: <strong>{JSON.stringify(value)}</strong></>}
              </div>;
            })()}
          </div>
        </div>
      )}
    </div>
  );
}

export default DataAccessPanel;
