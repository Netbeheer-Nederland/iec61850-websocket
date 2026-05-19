import { generatePythonModelFromScl } from './dataModelFactory.js';

(function () {
  const toolsSclFile = document.getElementById('tools-sclFile');
  const toolsGenerateModelBtn = document.getElementById('tools-generateModelBtn');
  const toolsIedSelectWrap = document.getElementById('tools-iedSelectWrap');
  const toolsIedSelect = document.getElementById('tools-iedSelect');
  const toolsApSelectWrap = document.getElementById('tools-apSelectWrap');
  const toolsApSelect = document.getElementById('tools-apSelect');
  const toolsStatusInfo = document.getElementById('tools-statusInfo');
  const toolsModel = document.getElementById('tools-modelPanel');
  let loadedIedNames = [];
  let loadedApsForCurrentIed = [];
  let accessPointsByIed = {};

  if (!toolsSclFile || !toolsGenerateModelBtn || !toolsIedSelectWrap || !toolsIedSelect || !toolsApSelectWrap || !toolsApSelect || !toolsStatusInfo || !toolsModel) {
    return;
  }

  function setIedSelector(iedNames) {
    loadedIedNames = Array.isArray(iedNames) ? iedNames.filter(Boolean) : [];
    toolsIedSelect.innerHTML = '';
    loadedApsForCurrentIed = [];
    accessPointsByIed = {};
    toolsApSelect.innerHTML = '';
    toolsApSelectWrap.style.display = 'none';

    if (loadedIedNames.length <= 1) {
      toolsIedSelectWrap.style.display = 'none';
      if (loadedIedNames.length === 1) {
        const option = document.createElement('option');
        option.value = loadedIedNames[0];
        option.textContent = loadedIedNames[0];
        toolsIedSelect.appendChild(option);
      }
      return;
    }

    loadedIedNames.forEach(function (name) {
      const option = document.createElement('option');
      option.value = name;
      option.textContent = name;
      toolsIedSelect.appendChild(option);
    });
    toolsIedSelectWrap.style.display = '';
  }

  async function loadToolsScl(file) {
    if (!file) {
      toolsStatusInfo.textContent = 'Select an SCL file first.';
      return;
    }
    toolsStatusInfo.textContent = 'Loading SCL model...';

    try {
      const xmlText = await file.text();
      const parser = new DOMParser();
      const doc = parser.parseFromString(xmlText, 'application/xml');
      const parseError = doc.querySelector('parsererror');
      if (parseError) {
        throw new Error('Invalid XML/SCL file.');
      }

      const logicalDeviceMap = {};
      const logicalNodeDetails = {};
      const apsByIed = {};

      const iedNodes = Array.from(doc.getElementsByTagNameNS('*', 'IED'));
      const iedNames = iedNodes.map(function (iedNode) {
        return iedNode.getAttribute('name');
      }).filter(Boolean);
      const iedName = iedNames.length ? iedNames[0] : '';

      setIedSelector(iedNames);
      toolsStatusInfo.textContent = 'SCL model loaded successfully.';
    } catch (e) {
      setIedSelector([]);
      toolsStatusInfo.textContent = 'Load SCL failed: ' + e.message;
    }
  }

  toolsSclFile.addEventListener('change', async function () {
    const file = toolsSclFile.files && toolsSclFile.files[0];
    await loadToolsScl(file);
  });

  toolsGenerateModelBtn.addEventListener('click', async function () {
    const file = toolsSclFile.files && toolsSclFile.files[0];
    if (!file) {
      toolsStatusInfo.textContent = 'Select an SCL file first.';
      return;
    }

    toolsStatusInfo.textContent = 'Generating model.py...';
    toolsGenerateModelBtn.disabled = true;

    try {
      const sourceFromLoadedFile = file.path || file.webkitRelativePath || file.name;
      const selectedIed = toolsIedSelect.value || (loadedIedNames.length === 1 ? loadedIedNames[0] : '');
      const selectedAp = toolsApSelect.value || (loadedApsForCurrentIed.length === 1 ? loadedApsForCurrentIed[0] : '');
      await generatePythonModelFromScl(file, sourceFromLoadedFile, selectedIed, selectedAp);

      toolsStatusInfo.textContent = 'model.py generated and downloaded.';
    } catch (error) {
      toolsStatusInfo.textContent = 'Generate model.py failed: ' + error.message;
    } finally {
      toolsGenerateModelBtn.disabled = false;
    }
  });
})();