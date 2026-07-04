// @ts-nocheck
const statusElement = document.getElementById("tofStatus");
const gridElement = document.getElementById("tofGrid");
const resolutionElement = document.getElementById("tofResolutionValue");
const validZonesElement = document.getElementById("tofValidZonesValue");
const lastUpdateElement = document.getElementById("tofLastUpdateValue");
const outlierThresholdInput = document.getElementById("outlierThresholdMm");
const outlierEnabledInput = document.getElementById("outlierEnabled");
const showStatusCodeInput = document.getElementById("tofShowStatusCode");
const hideInvalidDistanceInput = document.getElementById("tofHideInvalidDistance");
const viewEnabledHeader = document.getElementById("tof2dViewHeader");
const sectionBody = document.getElementById("tof2dSectionBody");
const pauseButton = document.getElementById("pauseTofButton");

if (!statusElement || !gridElement || !resolutionElement || !validZonesElement || !lastUpdateElement || !outlierThresholdInput || !outlierEnabledInput || !showStatusCodeInput || !hideInvalidDistanceInput || !viewEnabledHeader || !sectionBody || !pauseButton) {
	throw new Error("ToF sensor page elements are missing");
}

const storageKeyShowStatusCode = "tofSensor.showStatusCode";
const storageKeyHideInvalidDistance = "tofSensor.hideInvalidDistance";
const storageKeyViewEnabled = "tofSensor.view2dEnabled";

let socket = null;
let reconnectTimer = null;
let latestGridSide = 4;
let latestZoneCount = latestGridSide * latestGridSide;
let latestZones = new Array(latestZoneCount).fill(null);
let latestResolution = "4x4";
let latestMillis = null;
let mapPaused = false;
let mapManualPause = false;
let mapViewEnabled = true;

function readStoredShowStatusCode() {
	try {
		return localStorage.getItem(storageKeyShowStatusCode) === "true";
	} catch (error) {
		return false;
	}
}

function storeShowStatusCode(showStatusCode) {
	try {
		localStorage.setItem(storageKeyShowStatusCode, showStatusCode ? "true" : "false");
	} catch (error) {
		// Ignore storage failures.
	}
}

function readStoredHideInvalidDistance() {
	try {
		return localStorage.getItem(storageKeyHideInvalidDistance) === "true";
	} catch (error) {
		return false;
	}
}

function storeHideInvalidDistance(hideInvalidDistance) {
	try {
		localStorage.setItem(storageKeyHideInvalidDistance, hideInvalidDistance ? "true" : "false");
	} catch (error) {
		// Ignore storage failures.
	}
}

function shouldShowStatusCode() {
	return Boolean(showStatusCodeInput.checked);
}

function applyShowStatusCodeSetting() {
	storeShowStatusCode(shouldShowStatusCode());
	renderGrid();
}

function shouldHideInvalidDistance() {
	return Boolean(hideInvalidDistanceInput.checked);
}

function applyHideInvalidDistanceSetting() {
	storeHideInvalidDistance(shouldHideInvalidDistance());
	renderGrid();
}

function zoneIsValid(zone) {
	return Boolean(zone && zone.targetCount > 0 && zone.valid);
}

function parseOutlierThresholdInput() {
	const parsed = Number(outlierThresholdInput.value.trim());
	if (!Number.isFinite(parsed) || parsed <= 0) {
		return 350;
	}

	return Math.min(2000, Math.max(20, Math.round(parsed)));
}

function zoneWithinOutlierDistance(zone) {
	if (!outlierEnabledInput.checked) {
		return true;
	}

	if (!zone || zone.targetCount <= 0) {
		return false;
	}

	const distanceMm = Number(zone.distanceMm);
	if (!Number.isFinite(distanceMm) || distanceMm <= 0) {
		return false;
	}

	return distanceMm <= parseOutlierThresholdInput();
}

function zoneAcceptedFor2d(zone) {
	return zoneIsValid(zone) && zoneWithinOutlierDistance(zone);
}

function zoneHasDisplayableStatus(zone) {
	return zone && zone.status !== null && zone.status !== undefined;
}

function setStatus(text, isError) {
	statusElement.textContent = text;
	statusElement.classList.toggle("error", Boolean(isError));
}

function readStoredViewEnabled() {
	try {
		const stored = localStorage.getItem(storageKeyViewEnabled);
		if (stored === null) {
			return true;
		}
		return stored === "true";
	} catch (error) {
		return true;
	}
}

function storeViewEnabled(enabled) {
	try {
		localStorage.setItem(storageKeyViewEnabled, enabled ? "true" : "false");
	} catch (error) {
		// Ignore storage failures.
	}
}

function applyPauseState() {
	mapPaused = mapManualPause;
	pauseButton.textContent = mapManualPause ? "Resume all" : "Pause all";
	if (socket && socket.readyState === WebSocket.OPEN) {
		setStatus(mapPaused ? "Connected (paused)" : "Connected (20 Hz)", false);
	}
}

function setViewEnabled(enabled) {
	mapViewEnabled = Boolean(enabled);
	viewEnabledHeader.setAttribute("aria-expanded", mapViewEnabled ? "true" : "false");
	sectionBody.classList.toggle("tof-section-collapsed", !mapViewEnabled);
	storeViewEnabled(mapViewEnabled);
	applyPauseState();
}

function scheduleReconnect() {
	if (reconnectTimer) {
		return;
	}

	reconnectTimer = setTimeout(function () {
		reconnectTimer = null;
		connectSocket();
	}, 1000);
}

function formatDistance(distanceMm) {
	if (distanceMm === null || distanceMm === undefined) {
		return "--";
	}

	const parsed = Number(distanceMm);
	if (!Number.isFinite(parsed)) {
		return "--";
	}

	return String(Math.round(parsed));
}

function displayDistanceForZone(zone) {
	if (!zone || zone.targetCount <= 0) {
		return "--";
	}

	if (!zoneIsValid(zone) && !shouldHideInvalidDistance()) {
		return formatDistance(zone.distanceMm);
	}

	if (!zoneWithinOutlierDistance(zone)) {
		return "--";
	}

	if (shouldHideInvalidDistance() && !zoneIsValid(zone)) {
		return "--";
	}

	return formatDistance(zone.distanceMm);
}

function formatUpdateTime(millis) {
	const parsed = Number(millis);
	if (!Number.isFinite(parsed)) {
		return "--";
	}

	const date = new Date(parsed);
	return date.toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });
}

function renderSummary() {
	const validCount = latestZones.reduce(function (count, zone) {
		return count + (zoneAcceptedFor2d(zone) ? 1 : 0);
	}, 0);

	resolutionElement.textContent = latestResolution;
	validZonesElement.textContent = String(validCount) + " / " + String(latestZoneCount);
	lastUpdateElement.textContent = formatUpdateTime(latestMillis);
}

function renderGrid() {
	gridElement.innerHTML = "";
	gridElement.style.gridTemplateColumns = "repeat(" + String(latestGridSide) + ", minmax(0, 1fr))";

	for (let index = 0; index < latestZoneCount; index += 1) {
		const row = Math.floor(index / latestGridSide);
		const col = index % latestGridSide;
		const sourceIndex = (latestGridSide - 1 - row) * latestGridSide + col;
		const zone = latestZones[sourceIndex];
		const tile = document.createElement("div");
		tile.className = "tof-tile";

		if (zoneAcceptedFor2d(zone)) {
			tile.classList.add("valid");
		} else if (zoneHasDisplayableStatus(zone)) {
			if (shouldHideInvalidDistance()) {
				tile.classList.add("masked-invalid");
			} else {
				tile.classList.add("invalid");
			}
		} else if (zone && zone.targetCount > 0) {
			if (shouldHideInvalidDistance()) {
				tile.classList.add("masked-invalid");
			} else {
				tile.classList.add("invalid");
			}
		} else {
			tile.classList.add("empty");
		}

		const distance = document.createElement("div");
		distance.className = "tof-distance";

		const distanceNumber = document.createElement("span");
		distanceNumber.className = "tof-distance-number";
		distanceNumber.textContent = displayDistanceForZone(zone);

		distance.appendChild(distanceNumber);

		if (shouldShowStatusCode()) {
			const statusCode = document.createElement("div");
			statusCode.className = "tof-status-code";
			statusCode.textContent = zoneHasDisplayableStatus(zone) ? "S" + String(zone.status) : "--";
			tile.appendChild(statusCode);
		}

		tile.appendChild(distance);
		gridElement.appendChild(tile);
	}
}

function connectSocket() {
	const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
	const wsUrl = wsProtocol + "://" + window.location.host + "/ws/tofSensor";

	setStatus("Connecting...", false);
	socket = new WebSocket(wsUrl);

	socket.addEventListener("open", function () {
		applyPauseState();
	});

	socket.addEventListener("message", function (event) {
		try {
			const payload = JSON.parse(event.data);
			if (!Array.isArray(payload.zones)) {
				return;
			}

			window.dispatchEvent(new CustomEvent("tofSensorData", { detail: payload }));

			if (mapPaused) {
				return;
			}

			const gridSide = Number(payload.gridSide);
			latestGridSide = Number.isFinite(gridSide) && gridSide > 0 ? Math.round(gridSide) : 4;
			latestZoneCount = latestGridSide * latestGridSide;

			latestZones = payload.zones.slice(0, latestZoneCount);
			while (latestZones.length < latestZoneCount) {
				latestZones.push(null);
			}

			latestResolution = payload.resolution || (String(latestGridSide) + "x" + String(latestGridSide));
			latestMillis = payload.millis;
			renderSummary();
			renderGrid();
		} catch (error) {
			setStatus("Invalid data received", true);
		}
	});

	socket.addEventListener("close", function () {
		setStatus("Disconnected, retrying...", true);
		scheduleReconnect();
	});

	socket.addEventListener("error", function () {
		setStatus("WebSocket error", true);
		socket.close();
	});
}

showStatusCodeInput.checked = readStoredShowStatusCode();
hideInvalidDistanceInput.checked = readStoredHideInvalidDistance();
setViewEnabled(readStoredViewEnabled());
showStatusCodeInput.addEventListener("change", applyShowStatusCodeSetting);
hideInvalidDistanceInput.addEventListener("change", applyHideInvalidDistanceSetting);
outlierThresholdInput.addEventListener("change", function () {
	renderSummary();
	renderGrid();
});
outlierThresholdInput.addEventListener("blur", function () {
	renderSummary();
	renderGrid();
});
outlierEnabledInput.addEventListener("change", function () {
	renderSummary();
	renderGrid();
});
viewEnabledHeader.addEventListener("click", function () {
	setViewEnabled(!mapViewEnabled);
});
pauseButton.addEventListener("click", function () {
	mapManualPause = !mapManualPause;
	applyPauseState();
});

// Export pause state to window so 3D view can access it
window.tofMapPaused = () => mapPaused;
window.tof3dViewEnabled = () => !document.getElementById("tof3dSectionBody").classList.contains("tof-section-collapsed");
applyShowStatusCodeSetting();
applyHideInvalidDistanceSetting();
mapManualPause = false;
setViewEnabled(readStoredViewEnabled());
renderSummary();
renderGrid();
connectSocket();