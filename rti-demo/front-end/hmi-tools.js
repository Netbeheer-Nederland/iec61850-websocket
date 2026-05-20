import { generatePythonModelFromScl } from './dataModelFactory.js';

console.log('hmi-tools.js loaded');

(function () {
	const toolsSclFile = document.getElementById('tools-sclFile');
	const toolsGenerateModelBtn = document.getElementById('tools-generateModelBtn');
	const toolsStatusInfo = document.getElementById('tools-statusInfo');
	const toolsModelPanel = document.getElementById('tools-modelPanel');
	const toolsBrowseBtnText = document.getElementById('tools-browseBtnText');
	const toolsIedSelectWrap = document.getElementById('tools-iedSelectWrap');
	const toolsIedSelect = document.getElementById('tools-iedSelect');
	const toolsApSelectWrap = document.getElementById('tools-apSelectWrap');
	const toolsApSelect = document.getElementById('tools-apSelect');

	let loadedTreeData = null;

	console.log('DOM elements:', { toolsSclFile, toolsGenerateModelBtn, toolsStatusInfo, toolsModelPanel });

	if (!toolsSclFile || !toolsGenerateModelBtn || !toolsStatusInfo || !toolsModelPanel) {
		console.error('Missing required DOM elements');
		return;
	}

	function resetSelectionControls() {
		if (toolsIedSelectWrap) toolsIedSelectWrap.style.display = 'none';
		if (toolsApSelectWrap) toolsApSelectWrap.style.display = 'none';
		if (toolsIedSelect) toolsIedSelect.innerHTML = '';
		if (toolsApSelect) toolsApSelect.innerHTML = '';
	}

	function populateSelect(selectElement, values) {
		if (!selectElement) return;
		selectElement.innerHTML = '';
		values.forEach(function (value) {
			const option = document.createElement('option');
			option.value = value;
			option.textContent = value;
			selectElement.appendChild(option);
		});
	}

	function getIedsFromTree() {
		if (!loadedTreeData || !Array.isArray(loadedTreeData.ieds)) {
			return [];
		}
		return loadedTreeData.ieds;
	}

	function updateSelectionControls() {
		if (!toolsIedSelectWrap || !toolsIedSelect || !toolsApSelectWrap || !toolsApSelect) {
			return;
		}

		const ieds = getIedsFromTree();
		if (ieds.length === 0) {
			resetSelectionControls();
			return;
		}

		let selectedIedName = toolsIedSelect.value;
		if (!selectedIedName || !ieds.some(function (ied) { return ied.name === selectedIedName; })) {
			selectedIedName = ieds[0].name;
		}

		const needsIedSelection = ieds.length > 1;
		if (needsIedSelection) {
			populateSelect(toolsIedSelect, ieds.map(function (ied) { return ied.name; }));
			toolsIedSelect.value = selectedIedName;
			toolsIedSelectWrap.style.display = 'grid';
		} else {
			toolsIedSelectWrap.style.display = 'none';
			toolsIedSelect.innerHTML = '';
		}

		const selectedIed = ieds.find(function (ied) { return ied.name === selectedIedName; }) || ieds[0];
		const accessPoints = Array.isArray(selectedIed.accessPoints) ? selectedIed.accessPoints : [];

		let selectedApName = toolsApSelect.value;
		if (!selectedApName || !accessPoints.some(function (ap) { return ap.name === selectedApName; })) {
			selectedApName = accessPoints[0] ? accessPoints[0].name : '';
		}

		const needsApSelection = accessPoints.length > 1;
		if (needsApSelection) {
			populateSelect(toolsApSelect, accessPoints.map(function (ap) { return ap.name; }));
			toolsApSelect.value = selectedApName;
			toolsApSelectWrap.style.display = 'grid';
		} else {
			toolsApSelectWrap.style.display = 'none';
			toolsApSelect.innerHTML = '';
		}
	}

	if (toolsIedSelect) {
		toolsIedSelect.addEventListener('change', function () {
			updateSelectionControls();
		});
	}

	toolsSclFile.addEventListener('change', async function () {
		console.log('SCL file change event triggered');
		const file = toolsSclFile.files && toolsSclFile.files[0];
		if (!file) {
			loadedTreeData = null;
			resetSelectionControls();
			if (toolsBrowseBtnText) {
				toolsBrowseBtnText.textContent = 'Browse SCL File';
			}
			toolsStatusInfo.textContent = 'Select an SCL file first.';
			return;
		}

		if (toolsBrowseBtnText) {
			toolsBrowseBtnText.textContent = file.name;
		}

		console.log('File selected:', file.name);
		toolsStatusInfo.textContent = 'Loading SCL model...';
		try {
			console.log('window.SCLTree:', window.SCLTree);
			if (!window.SCLTree || typeof window.SCLTree.loadSclFileAndRender !== 'function') {
				throw new Error('SCL tree renderer not available.');
			}

			loadedTreeData = await window.SCLTree.loadSclFileAndRender(file, 'tools-modelPanel');
			updateSelectionControls();
			toolsStatusInfo.textContent = 'SCL model loaded successfully.';
		} catch (error) {
			console.error('Error loading SCL:', error);
			loadedTreeData = null;
			resetSelectionControls();
			toolsModelPanel.textContent = '';
			toolsStatusInfo.textContent = 'Load SCL failed: ' + error.message;
		}
	});

	toolsGenerateModelBtn.addEventListener('click', async function () {
		console.log('Generate button clicked');
		const file = toolsSclFile.files && toolsSclFile.files[0];
		if (!file) {
			toolsStatusInfo.textContent = 'Select an SCL file first.';
			return;
		}

		toolsStatusInfo.textContent = 'Generating model.py...';
		toolsGenerateModelBtn.disabled = true;

		try {
			const sourceFromLoadedFile = file.path || file.webkitRelativePath || file.name;
			const ieds = getIedsFromTree();
			let selectedIedName = '';
			let selectedApName = '';

			const iedFromSelect = toolsIedSelect && toolsIedSelect.value;
			const selectedIed = ieds.find(function (ied) { return ied.name === iedFromSelect; }) || ieds[0] || null;

			if (selectedIed) {
				const selectedIedAccessPoints = Array.isArray(selectedIed.accessPoints) ? selectedIed.accessPoints : [];

				if (ieds.length > 1 || selectedIedAccessPoints.length > 1) {
					selectedIedName = selectedIed.name;
				}

				if (selectedIedAccessPoints.length > 1) {
					selectedApName = (toolsApSelect && toolsApSelect.value) || '';
					if (!selectedApName) {
						toolsStatusInfo.textContent = 'Select an Access Point before generating.';
						return;
					}
				}
			}

			await generatePythonModelFromScl(file, sourceFromLoadedFile, selectedIedName, selectedApName);
			toolsStatusInfo.textContent = 'model.py generated and downloaded.';
		} catch (error) {
			toolsStatusInfo.textContent = 'Generate model.py failed: ' + error.message;
		} finally {
			toolsGenerateModelBtn.disabled = false;
		}
	});
})();
