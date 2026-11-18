import { connectDevice } from "./device.js";

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

let connected = false;
let lastHz = 0;
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
	if (connected) {
		setStatus(mapPaused ? "Connected (paused)" : `Connected (${lastHz.toFixed(0)} frames/s)`, false);
	}
}

function setViewEnabled(enabled) {
	mapViewEnabled = Boolean(enabled);
	viewEnabledHeader.setAttribute("aria-expanded", mapViewEnabled ? "true" : "false");
	sectionBody.classList.toggle("tof-section-collapsed", !mapViewEnabled);
	storeViewEnabled(mapViewEnabled);
	applyPauseState();
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

// The device sends {"t":"tof","side":8,"d":[mm..],"s":[status..],"n":[targets..],...}; the drawing code (and the
// 3D view, through the "tofSensorData" event) work with zone objects, as the PlatformIO firmware sent them.
function zonesFrom(payload) {
	const zones = [];
	for (let i = 0; i < payload.side * payload.side; i += 1) {
		const status = payload.s[i];
		const targetCount = payload.n[i];
		zones.push({
			index: i,
			row: Math.floor(i / payload.side),
			col: i % payload.side,
			targetCount,
			status,
			valid: targetCount > 0 && (status === 5 || status === 9),
			distanceMm: targetCount > 0 ? payload.d[i] : null
		});
	}
	return zones;
}

function connectSocket() {
	const dev = connectDevice(["tof"], function (payload) {
		if (payload.t !== "tof") {
			window.dispatchEvent(new CustomEvent("tofDeviceMessage", { detail: payload }));
			return;
		}
		window.dispatchEvent(new CustomEvent("tofSettingsData", { detail: payload }));
		if (!payload.ok) {
			setStatus("VL53L7CX not found (or starting: loading its firmware takes a few seconds)", true);
			return;
		}
		lastHz = payload.hz;
		const legacy = {
			resolution: payload.side + "x" + payload.side,
			gridSide: payload.side,
			millis: Date.now(),
			zones: zonesFrom(payload)
		};
		window.dispatchEvent(new CustomEvent("tofSensorData", { detail: legacy }));
		if (mapPaused) {
			return;
		}
		latestGridSide = payload.side;
		latestZoneCount = latestGridSide * latestGridSide;
		latestZones = legacy.zones;
		latestResolution = legacy.resolution;
		latestMillis = legacy.millis;
		applyPauseState();
		renderSummary();
		renderGrid();
	}, function (text, isError) {
		connected = !isError;
		setStatus(text, isError);
	});
	window.tofDevice = dev;
	window.dispatchEvent(new CustomEvent("tofDeviceReady", { detail: dev }));
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