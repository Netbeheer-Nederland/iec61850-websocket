console.log('tree.js loading...');

function parseSclXml(xmlText) {
  const parser = new DOMParser();
  const doc = parser.parseFromString(xmlText, 'application/xml');
  const parseError = doc.querySelector('parsererror');
  if (parseError) {
    throw new Error('Invalid XML/SCL file.');
  }
  return doc;
}

function directChildren(node, localName) {
  return Array.from(node.children || []).filter(function (child) {
    return child.localName === localName;
  });
}

function attr(node, name) {
  return (node && node.getAttribute(name)) || '';
}

function buildLnName(lnNode) {
  const lnClass = attr(lnNode, 'lnClass') || 'LN';
  const inst = attr(lnNode, 'inst');
  const prefix = attr(lnNode, 'prefix');
  return `${prefix}${lnClass}${inst}`;
}

function buildDoTypeMap(doc) {
  const map = {};
  const dtt = directChildren(doc.documentElement, 'DataTypeTemplates')[0] || null;
  if (!dtt) {
    return map;
  }

  directChildren(dtt, 'DOType').forEach(function (doTypeNode) {
    const id = attr(doTypeNode, 'id');
    if (!id) return;
    map[id] = {
      cdc: attr(doTypeNode, 'cdc'),
      das: directChildren(doTypeNode, 'DA').map(function (daNode) {
        return {
          name: attr(daNode, 'name'),
          bType: attr(daNode, 'bType'),
          fc: attr(daNode, 'fc')
        };
      }),
      sdos: directChildren(doTypeNode, 'SDO').map(function (sdoNode) {
        return {
          name: attr(sdoNode, 'name'),
          type: attr(sdoNode, 'type')
        };
      })
    };
  });

  return map;
}

function buildLnTypeMap(doc) {
  const map = {};
  const dtt = directChildren(doc.documentElement, 'DataTypeTemplates')[0] || null;
  if (!dtt) {
    return map;
  }

  directChildren(dtt, 'LNodeType').forEach(function (lnTypeNode) {
    const id = attr(lnTypeNode, 'id');
    if (!id) return;
    map[id] = directChildren(lnTypeNode, 'DO').map(function (doNode) {
      return {
        name: attr(doNode, 'name'),
        type: attr(doNode, 'type')
      };
    });
  });

  return map;
}

function buildDaTypeMap(doc) {
  const map = {};
  const dtt = directChildren(doc.documentElement, 'DataTypeTemplates')[0] || null;
  if (!dtt) {
    return map;
  }

  directChildren(dtt, 'DAType').forEach(function (daTypeNode) {
    const id = attr(daTypeNode, 'id');
    if (!id) return;
    map[id] = directChildren(daTypeNode, 'BDA').map(function (bdaNode) {
      return {
        name: attr(bdaNode, 'name'),
        bType: attr(bdaNode, 'bType'),
        fc: attr(bdaNode, 'fc'),
        type: attr(bdaNode, 'type')
      };
    });
  });

  return map;
}

function resolveDataAttributeTree(daDef, daTypeMap, visitedDaTypes) {
  const node = {
    name: daDef.name,
    bType: daDef.bType,
    fc: daDef.fc,
    type: daDef.type,
    subDataAttributes: []
  };

  const isStruct = daDef.bType === 'Struct' && daDef.type;
  if (!isStruct) {
    return node;
  }

  if (visitedDaTypes.has(daDef.type)) {
    return node;
  }

  visitedDaTypes.add(daDef.type);
  const bdas = daTypeMap[daDef.type] || [];
  node.subDataAttributes = bdas.map(function (bdaDef) {
    return resolveDataAttributeTree(bdaDef, daTypeMap, new Set(visitedDaTypes));
  });
  return node;
}

function resolveDoTypeTree(doTypeId, doTypeMap, daTypeMap, visitedDoTypes) {
  const doType = doTypeMap[doTypeId] || null;
  if (!doType) {
    return {
      cdc: '',
      dataAttributes: [],
      subDataObjects: []
    };
  }

  const dataAttributes = (doType.das || []).map(function (daDef) {
    return resolveDataAttributeTree(daDef, daTypeMap, new Set());
  });

  const subDataObjects = (doType.sdos || []).map(function (sdoDef) {
    const nextVisitedDoTypes = new Set(visitedDoTypes);
    const sdoNode = {
      name: sdoDef.name,
      type: sdoDef.type,
      cdc: '',
      dataAttributes: [],
      subDataObjects: []
    };

    if (!sdoDef.type || nextVisitedDoTypes.has(sdoDef.type)) {
      return sdoNode;
    }

    nextVisitedDoTypes.add(sdoDef.type);
    const resolved = resolveDoTypeTree(sdoDef.type, doTypeMap, daTypeMap, nextVisitedDoTypes);
    sdoNode.cdc = resolved.cdc;
    sdoNode.dataAttributes = resolved.dataAttributes;
    sdoNode.subDataObjects = resolved.subDataObjects;
    return sdoNode;
  });

  return {
    cdc: doType.cdc || '',
    dataAttributes,
    subDataObjects
  };
}

function buildSclTreeFromText(xmlText) {
  const doc = parseSclXml(xmlText);
  const lnTypeMap = buildLnTypeMap(doc);
  const doTypeMap = buildDoTypeMap(doc);
  const daTypeMap = buildDaTypeMap(doc);

  const iedNodes = Array.from(doc.getElementsByTagNameNS('*', 'IED'));
  const ieds = iedNodes.map(function (iedNode) {
    const ied = {
      name: attr(iedNode, 'name') || 'IED',
      accessPoints: []
    };

    directChildren(iedNode, 'AccessPoint').forEach(function (apNode) {
      const ap = {
        name: attr(apNode, 'name') || 'AccessPoint',
        ldevices: []
      };

      directChildren(apNode, 'Server').forEach(function (serverNode) {
        directChildren(serverNode, 'LDevice').forEach(function (ldNode) {
          const ldevice = {
            name: attr(ldNode, 'inst') || attr(ldNode, 'ldName') || 'LDevice',
            lnodes: []
          };

          const lnNodes = directChildren(ldNode, 'LN0').concat(directChildren(ldNode, 'LN'));
          lnNodes.forEach(function (lnNode) {
            const lnName = buildLnName(lnNode);
            const lnType = attr(lnNode, 'lnType');

            const ln = {
              name: lnName,
              lnType,
              dataObjects: [],
              dataSets: directChildren(lnNode, 'DataSet').map(function (dsNode) {
                return attr(dsNode, 'name') || 'DataSet';
              }),
              reportControls: directChildren(lnNode, 'ReportControl').map(function (rcNode) {
                return attr(rcNode, 'name') || 'ReportControl';
              })
            };

            (lnTypeMap[lnType] || []).forEach(function (lnDo) {
              const resolvedDoType = resolveDoTypeTree(lnDo.type, doTypeMap, daTypeMap, new Set([lnDo.type]));
              ln.dataObjects.push({
                name: lnDo.name,
                type: lnDo.type,
                cdc: resolvedDoType.cdc,
                dataAttributes: resolvedDoType.dataAttributes,
                subDataObjects: resolvedDoType.subDataObjects
              });
            });

            ldevice.lnodes.push(ln);
          });

          ap.ldevices.push(ldevice);
        });
      });

      ied.accessPoints.push(ap);
    });

    return ied;
  });

  return { ieds };
}

function normalizeNodeType(nodeType) {
  return String(nodeType || 'node').toLowerCase().replace(/[^a-z0-9]+/g, '-');
}

function nodeTypeLabel(nodeType) {
  const labels = {
    AccessPoint: 'Access Point',
    LDevice: 'Logical Device',
    LogicalNode: 'Logical Node',
    ReportControl: 'Report Control'
  };
  return labels[nodeType] || nodeType;
}

function createTreeNode(nodeType, value) {
  const li = document.createElement('li');
  li.className = `scl-tree-item scl-node-${normalizeNodeType(nodeType)}`;

  const row = document.createElement('div');
  row.className = 'scl-tree-row';

  const toggle = document.createElement('button');
  toggle.type = 'button';
  toggle.className = 'scl-tree-toggle';
  toggle.textContent = '';

  const isGroupNode = String(nodeType || '').toLowerCase() === 'group';
  const tag = document.createElement('span');
  tag.className = `scl-tree-tag${isGroupNode ? ' hidden' : ''}`;
  tag.textContent = isGroupNode ? '' : nodeTypeLabel(nodeType);

  const valueEl = document.createElement('span');
  valueEl.className = 'scl-tree-value';
  valueEl.textContent = value || '';

  row.appendChild(toggle);
  row.appendChild(tag);
  row.appendChild(valueEl);
  li.appendChild(row);
  return li;
}

function appendChildrenTree(parentLi, childrenLabels, childType) {
  if (!childrenLabels || childrenLabels.length === 0) {
    return;
  }

  const ul = document.createElement('ul');
  ul.className = 'scl-tree-list';
  childrenLabels.forEach(function (label) {
    ul.appendChild(createTreeNode(childType, label));
  });
  parentLi.appendChild(ul);
}

function appendDataAttributeNodes(parentLi, attributes, nodeLabel) {
  if (!attributes || attributes.length === 0) {
    return;
  }

  const ul = document.createElement('ul');
  ul.className = 'scl-tree-list';

  attributes.forEach(function (da) {
    const typeSuffix = da.bType ? ` [${da.bType}]` : '';
    const daLi = createTreeNode(nodeLabel, `${da.name}${typeSuffix}`);
    appendDataAttributeNodes(daLi, da.subDataAttributes || [], 'SDA');
    ul.appendChild(daLi);
  });

  parentLi.appendChild(ul);
}

function appendSubDataObjectNodes(parentLi, subDataObjects) {
  if (!subDataObjects || subDataObjects.length === 0) {
    return;
  }

  const ul = document.createElement('ul');
  ul.className = 'scl-tree-list';

  subDataObjects.forEach(function (sdo) {
    const cdcSuffix = sdo.cdc ? ` [${sdo.cdc}]` : '';
    const sdoLi = createTreeNode('SDO', `${sdo.name}${cdcSuffix}`);
    appendDataAttributeNodes(sdoLi, sdo.dataAttributes || [], 'DA');
    appendSubDataObjectNodes(sdoLi, sdo.subDataObjects || []);
    ul.appendChild(sdoLi);
  });

  parentLi.appendChild(ul);
}

function appendDataObjectNodes(parentLi, dataObjects) {
  if (!dataObjects || dataObjects.length === 0) {
    return;
  }

  const ul = document.createElement('ul');
  ul.className = 'scl-tree-list';

  dataObjects.forEach(function (dobj) {
    const cdc = dobj.cdc ? ` [${dobj.cdc}]` : '';
    const doLi = createTreeNode('DO', `${dobj.name}${cdc}`);
    appendDataAttributeNodes(doLi, dobj.dataAttributes || [], 'DA');
    appendSubDataObjectNodes(doLi, dobj.subDataObjects || []);
    ul.appendChild(doLi);
  });

  parentLi.appendChild(ul);
}

function setupCollapsibleTree(container) {
  const treeItems = container.querySelectorAll('.scl-tree-item');

  treeItems.forEach(function (item) {
    const row = item.querySelector(':scope > .scl-tree-row');
    const toggle = row ? row.querySelector('.scl-tree-toggle') : null;
    const childList = item.querySelector(':scope > .scl-tree-list');

    if (!row || !toggle) {
      return;
    }

    if (!childList || childList.children.length === 0) {
      toggle.classList.add('hidden');
      return;
    }

    item.classList.add('has-children', 'expanded');
    toggle.textContent = '▾';

    const onToggle = function () {
      const isExpanded = item.classList.toggle('expanded');
      toggle.textContent = isExpanded ? '▾' : '▸';
      childList.style.display = isExpanded ? '' : 'none';
    };

    row.addEventListener('click', function (event) {
      if (event.target && event.target.classList.contains('scl-tree-toggle')) {
        return;
      }
      onToggle();
    });

    toggle.addEventListener('click', function (event) {
      event.stopPropagation();
      onToggle();
    });
  });
}

function renderSclTree(treeData, containerOrId) {
  const container = typeof containerOrId === 'string'
    ? document.getElementById(containerOrId)
    : containerOrId;

  if (!container) {
    throw new Error('Tree container not found.');
  }

  container.innerHTML = '';

  const root = document.createElement('ul');
  root.className = 'scl-tree-root';
  (treeData.ieds || []).forEach(function (ied) {
    const iedLi = createTreeNode('IED', ied.name);
    const apUl = document.createElement('ul');
    apUl.className = 'scl-tree-list';

    (ied.accessPoints || []).forEach(function (ap) {
      const apLi = createTreeNode('AccessPoint', ap.name);
      const ldUl = document.createElement('ul');
      ldUl.className = 'scl-tree-list';

      (ap.ldevices || []).forEach(function (ld) {
        const ldLi = createTreeNode('LDevice', ld.name);
        const lnUl = document.createElement('ul');
        lnUl.className = 'scl-tree-list';

        (ld.lnodes || []).forEach(function (ln) {
          const lnLi = createTreeNode('LogicalNode', ln.name);
          const lnDetailsUl = document.createElement('ul');
          lnDetailsUl.className = 'scl-tree-list';

          const dsLi = createTreeNode('Group', 'DataSets');
          appendChildrenTree(dsLi, ln.dataSets || [], 'DataSet');

          const rcLi = createTreeNode('Group', 'Report Controls');
          appendChildrenTree(rcLi, ln.reportControls || [], 'ReportControl');

          const doLi = createTreeNode('Group', 'Data Objects');
          appendDataObjectNodes(doLi, ln.dataObjects || []);

          lnDetailsUl.appendChild(dsLi);
          lnDetailsUl.appendChild(rcLi);
          lnDetailsUl.appendChild(doLi);
          lnLi.appendChild(lnDetailsUl);
          lnUl.appendChild(lnLi);
        });

        ldLi.appendChild(lnUl);
        ldUl.appendChild(ldLi);
      });

      apLi.appendChild(ldUl);
      apUl.appendChild(apLi);
    });

    iedLi.appendChild(apUl);
    root.appendChild(iedLi);
  });

  container.appendChild(root);
  setupCollapsibleTree(container);
}

async function loadSclFileAndRender(file, containerOrId) {
  if (!file) {
    throw new Error('No SCL file provided.');
  }

  const xmlText = await file.text();
  const treeData = buildSclTreeFromText(xmlText);
  console.log('Tree data generated:', treeData);
  renderSclTree(treeData, containerOrId);
  return treeData;
}

window.SCLTree = {
  buildSclTreeFromText,
  renderSclTree,
  loadSclFileAndRender
};

console.log('tree.js loaded. window.SCLTree:', window.SCLTree);
