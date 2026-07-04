// @ts-nocheck
const matrixTable = document.getElementById("matrixTable");
const matrixTableBody = document.getElementById("matrixTableBody");
const emptyState = document.getElementById("emptyState");
const matrixStatus = document.getElementById("matrixStatus");
const routeName = document.getElementById("routeName");
const inputTypeSelect = document.getElementById("inputType");
const inputPinInput = document.getElementById("inputPin");
const outputTypeSelect = document.getElementById("outputType");
const outputPinInput = document.getElementById("outputPin");
const invertInput = document.getElementById("invertInput");
const thresholdInput = document.getElementById("threshold");
const addRouteBtn = document.getElementById("addRouteBtn");
const clearAllBtn = document.getElementById("clearAllBtn");

const editModal = document.getElementById("editModal");
const editRouteName = document.getElementById("editRouteName");
const editInputType = document.getElementById("editInputType");
const editInputPin = document.getElementById("editInputPin");
const editOutputType = document.getElementById("editOutputType");
const editOutputPin = document.getElementById("editOutputPin");
const editInvertInput = document.getElementById("editInvertInput");
const editThreshold = document.getElementById("editThreshold");
const editSaveBtn = document.getElementById("editSaveBtn");
const editCancelBtn = document.getElementById("editCancelBtn");

let editingRouteId = null;

if (!matrixTable || !matrixTableBody || !emptyState || !matrixStatus || 
    !routeName || !inputTypeSelect || !inputPinInput || !outputTypeSelect || !outputPinInput || 
    !invertInput || !thresholdInput || !addRouteBtn || !clearAllBtn ||
    !editModal || !editRouteName || !editInputType || !editInputPin || 
    !editOutputType || !editOutputPin || !editInvertInput || !editThreshold || !editSaveBtn || !editCancelBtn) {
	throw new Error("Matrix page elements are missing");
}

function setStatus(text, isError) {
	matrixStatus.textContent = text;
	matrixStatus.classList.toggle("error", Boolean(isError));
}

function updateTableDisplay(routes) {
	matrixTableBody.innerHTML = "";
	
	if (routes.length === 0) {
		matrixTable.style.display = "none";
		emptyState.style.display = "block";
		return;
	}
	
	matrixTable.style.display = "table";
	emptyState.style.display = "none";
	
	for (const route of routes) {
		const row = document.createElement("tr");
		
		const idCell = document.createElement("td");
		idCell.textContent = String(route.id);
		row.appendChild(idCell);
		
		const nameCell = document.createElement("td");
		nameCell.textContent = route.name || "(unnamed)";
		row.appendChild(nameCell);
		
		const inputTypeCell = document.createElement("td");
		inputTypeCell.textContent = route.inputType;
		row.appendChild(inputTypeCell);
		
		const inputPinCell = document.createElement("td");
		inputPinCell.textContent = String(route.inputPin);
		row.appendChild(inputPinCell);
		
		const outputTypeCell = document.createElement("td");
		outputTypeCell.textContent = route.outputType;
		row.appendChild(outputTypeCell);
		
		const outputPinCell = document.createElement("td");
		outputPinCell.textContent = String(route.outputPin);
		row.appendChild(outputPinCell);
		
		const enabledCell = document.createElement("td");
		const enabledCheckbox = document.createElement("input");
		enabledCheckbox.type = "checkbox";
		enabledCheckbox.checked = route.enabled;
		enabledCheckbox.addEventListener("change", function () {
			toggleRouteEnabled(route.id, enabledCheckbox.checked);
		});
		enabledCell.appendChild(enabledCheckbox);
		row.appendChild(enabledCell);
		
		const invertCell = document.createElement("td");
		if (route.invert) {
			invertCell.textContent = "✓";
			invertCell.style.textAlign = "center";
		}
		row.appendChild(invertCell);
		
		const actionsCell = document.createElement("td");
		
		const editBtn = document.createElement("button");
		editBtn.className = "btn btn-small";
		editBtn.textContent = "Edit";
		editBtn.style.marginRight = "5px";
		editBtn.addEventListener("click", function () {
			openEditModal(route);
		});
		actionsCell.appendChild(editBtn);
		
		const deleteBtn = document.createElement("button");
		deleteBtn.className = "btn btn-small btn-danger";
		deleteBtn.textContent = "Delete";
		deleteBtn.addEventListener("click", function () {
			deleteRoute(route.id);
		});
		actionsCell.appendChild(deleteBtn);
		row.appendChild(actionsCell);
		
		matrixTableBody.appendChild(row);
	}
}

async function loadRoutes() {
	try {
		setStatus("Loading routes...", false);
		const response = await fetch("/api/matrix/routes");
		if (!response.ok) {
			throw new Error(`HTTP ${response.status}`);
		}
		const data = await response.json();
		updateTableDisplay(Array.isArray(data) ? data : []);
		setStatus("Routes loaded", false);
	} catch (error) {
		setStatus(`Failed to load routes: ${error.message}`, true);
		updateTableDisplay([]);
	}
}

async function addRoute() {
	const rName = routeName.value.trim();
	const inputType = inputTypeSelect.value;
	const inputPin = parseInt(inputPinInput.value, 10);
	const outputType = outputTypeSelect.value;
	const outputPin = parseInt(outputPinInput.value, 10);
	const invert = invertInput.checked;
	const threshold = parseFloat(thresholdInput.value);
	
	if (!Number.isFinite(inputPin) || !Number.isFinite(outputPin) || !Number.isFinite(threshold)) {
		setStatus("Invalid pin numbers or threshold", true);
		return;
	}
	
	if (threshold <= 0 || threshold > 1) {
		setStatus("Threshold must be between 0 and 1", true);
		return;
	}
	
	try {
		setStatus("Adding route...", false);
		const params = new URLSearchParams();
		if (rName) params.append("name", rName);
		params.append("inputType", inputType);
		params.append("inputPin", String(inputPin));
		params.append("outputType", outputType);
		params.append("outputPin", String(outputPin));
		params.append("enabled", "true");
		params.append("invert", invert ? "true" : "false");
		params.append("threshold", String(threshold));
		
		const response = await fetch("/api/matrix/routes", {
			method: "POST",
			body: params
		});
		
		if (!response.ok) {
			throw new Error(`HTTP ${response.status}`);
		}
		
		routeName.value = "";
		inputPinInput.value = "0";
		outputPinInput.value = "0";
		invertInput.checked = false;
		thresholdInput.value = "0.5";
		await loadRoutes();
	} catch (error) {
		setStatus(`Failed to add route: ${error.message}`, true);
	}
}

async function deleteRoute(id) {
	if (!confirm(`Delete route ${id}?`)) {
		return;
	}
	
	try {
		setStatus("Deleting route...", false);
		const response = await fetch(`/api/matrix/routes/${id}`, {
			method: "DELETE"
		});
		
		if (!response.ok) {
			throw new Error(`HTTP ${response.status}`);
		}
		
		await loadRoutes();
	} catch (error) {
		setStatus(`Failed to delete route: ${error.message}`, true);
	}
}

async function toggleRouteEnabled(id, enabled) {
	try {
		const params = new URLSearchParams();
		params.append("enabled", enabled ? "true" : "false");
		
		const response = await fetch(`/api/matrix/routes/${id}/enabled`, {
			method: "PUT",
			body: params
		});
		
		if (!response.ok) {
			throw new Error(`HTTP ${response.status}`);
		}
	} catch (error) {
		setStatus(`Failed to toggle route: ${error.message}`, true);
		await loadRoutes();
	}
}

async function clearAllRoutes() {
	if (!confirm("This will delete ALL routes. Are you sure?")) {
		return;
	}
	
	try {
		setStatus("Clearing all routes...", false);
		const response = await fetch("/api/matrix/routes", {
			method: "DELETE"
		});
		
		if (!response.ok) {
			throw new Error(`HTTP ${response.status}`);
		}
		
		await loadRoutes();
	} catch (error) {
		setStatus(`Failed to clear routes: ${error.message}`, true);
	}
}

function openEditModal(route) {
	editingRouteId = route.id;
	editRouteName.value = route.name || "";
	editInputType.value = route.inputType;
	editInputPin.value = String(route.inputPin);
	editOutputType.value = route.outputType;
	editOutputPin.value = String(route.outputPin);
	editInvertInput.checked = route.invert;
	editThreshold.value = String(route.threshold || 0.5);
	editModal.style.display = "block";
}

function closeEditModal() {
	editModal.style.display = "none";
	editingRouteId = null;
}

async function saveEditRoute() {
	if (editingRouteId === null) return;
	
	const rName = editRouteName.value.trim();
	const inputType = editInputType.value;
	const inputPin = parseInt(editInputPin.value, 10);
	const outputType = editOutputType.value;
	const outputPin = parseInt(editOutputPin.value, 10);
	const invert = editInvertInput.checked;
	const threshold = parseFloat(editThreshold.value);
	
	if (!Number.isFinite(inputPin) || !Number.isFinite(outputPin) || !Number.isFinite(threshold)) {
		setStatus("Invalid pin numbers or threshold", true);
		return;
	}
	
	if (threshold <= 0 || threshold > 1) {
		setStatus("Threshold must be between 0 and 1", true);
		return;
	}
	
	try {
		setStatus("Saving route...", false);
		const params = new URLSearchParams();
		if (rName) params.append("name", rName);
		params.append("inputType", inputType);
		params.append("inputPin", String(inputPin));
		params.append("outputType", outputType);
		params.append("outputPin", String(outputPin));
		params.append("invert", invert ? "true" : "false");
		params.append("threshold", String(threshold));
		
		const response = await fetch(`/api/matrix/routes/${editingRouteId}`, {
			method: "PUT",
			body: params
		});
		
		if (!response.ok) {
			throw new Error(`HTTP ${response.status}`);
		}
		
		closeEditModal();
		await loadRoutes();
	} catch (error) {
		setStatus(`Failed to save route: ${error.message}`, true);
	}
}

addRouteBtn.addEventListener("click", addRoute);
clearAllBtn.addEventListener("click", clearAllRoutes);
editSaveBtn.addEventListener("click", saveEditRoute);
editCancelBtn.addEventListener("click", closeEditModal);

// Close modal when clicking outside of it
editModal.addEventListener("click", function (event) {
	if (event.target === editModal) {
		closeEditModal();
	}
});

loadRoutes();
