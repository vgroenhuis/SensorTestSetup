// @ts-nocheck
const statusElement = document.getElementById("tofStatus");
const gridElement = document.getElementById("tofGrid");
const resolutionElement = document.getElementById("tofResolutionValue");
const validZonesElement = document.getElementById("tofValidZonesValue");
const lastUpdateElement = document.getElementById("tofLastUpdateValue");
const thresholdInput = document.getElementById("tofThresholdMm");
const showStatusCodeInput = document.getElementById("tofShowStatusCode");
const hideInvalidDistanceInput = document.getElementById("tofHideInvalidDistance");
const pauseButton = document.getElementById("pauseTofButton");

if (!statusElement || !gridElement || !resolutionElement || !validZonesElement || !lastUpdateElement || !thresholdInput || !showStatusCodeInput || !hideInvalidDistanceInput || !pauseButton) {
	throw new Error("ToF sensor page elements are missing");
}

const zoneCount = 16;
const zoneSide = 4;
const defaultThresholdMm = 3500;
const maxThresholdMm = 10000;
const storageKeyThresholdMm = "tofSensor.thresholdMm";
const storageKeyShowStatusCode = "tofSensor.showStatusCode";
const storageKeyHideInvalidDistance = "tofSensor.hideInvalidDistance";

let socket = null;
let reconnectTimer = null;
let latestZones = new Array(zoneCount).fill(null);
let latestResolution = "4x4";
let latestMillis = null;
let mapPaused = false;

function parseThresholdInput() {
	const parsed = Number(thresholdInput.value.trim());
	if (!Number.isFinite(parsed) || parsed < 0) {
		return defaultThresholdMm;
	}

	return Math.min(maxThresholdMm, Math.max(0, Math.round(parsed)));
}

function readStoredThreshold() {
	try {
		const raw = localStorage.getItem(storageKeyThresholdMm);
		if (raw === null) {
			return defaultThresholdMm;
		}

		const parsed = Number(raw);
		if (!Number.isFinite(parsed) || parsed < 0) {
			return defaultThresholdMm;
		}

		return Math.min(maxThresholdMm, Math.max(0, Math.round(parsed)));
	} catch (error) {
		return defaultThresholdMm;
	}
}

function storeThreshold(thresholdMm) {
	try {
		localStorage.setItem(storageKeyThresholdMm, String(thresholdMm));
	} catch (error) {
		// Ignore storage failures.
	}
}

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

function applyThresholdFromInput() {
	const thresholdMm = parseThresholdInput();
	thresholdInput.value = String(thresholdMm);
	storeThreshold(thresholdMm);
	renderSummary();
	renderGrid();
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

function zonePassesThreshold(zone) {
	if (!zone || zone.targetCount <= 0 || !zone.valid) {
		return false;
	}

	const distanceMm = Number(zone.distanceMm);
	if (!Number.isFinite(distanceMm)) {
		return false;
	}

	return distanceMm <= parseThresholdInput();
}

function zoneHasDisplayableStatus(zone) {
	return zone && zone.status !== null && zone.status !== undefined;
}

function setStatus(text, isError) {
	statusElement.textContent = text;
	statusElement.classList.toggle("error", Boolean(isError));
}

function setMapPaused(paused) {
	mapPaused = paused;
	pauseButton.textContent = mapPaused ? "Resume map" : "Pause map";
	if (socket && socket.readyState === WebSocket.OPEN) {
		setStatus(mapPaused ? "Connected (paused)" : "Connected (20 Hz)", false);
	}
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

	if (shouldHideInvalidDistance() && !zonePassesThreshold(zone)) {
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
		return count + (zonePassesThreshold(zone) ? 1 : 0);
	}, 0);

	resolutionElement.textContent = latestResolution;
	validZonesElement.textContent = String(validCount) + " / " + String(zoneCount);
	lastUpdateElement.textContent = formatUpdateTime(latestMillis);
}

function renderGrid() {
	gridElement.innerHTML = "";

	for (let index = 0; index < zoneCount; index += 1) {
		const row = Math.floor(index / zoneSide);
		const col = index % zoneSide;
		const sourceIndex = (zoneSide - 1 - row) * zoneSide + col;
		const zone = latestZones[sourceIndex];
		const tile = document.createElement("div");
		tile.className = "tof-tile";

		if (zonePassesThreshold(zone)) {
			tile.classList.add("valid");
		} else if (zoneHasDisplayableStatus(zone)) {
			if (shouldHideInvalidDistance()) {
				tile.classList.add("masked-invalid");
			} else {
				tile.classList.add("invalid");
			}
		} else if (zone && zone.targetCount > 0) {
			if (zonePassesThreshold(zone)) {
				tile.classList.add("valid");
			} else if (shouldHideInvalidDistance()) {
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
		setStatus(mapPaused ? "Connected (paused)" : "Connected (20 Hz)", false);
	});

	socket.addEventListener("message", function (event) {
		try {
			if (mapPaused) {
				return;
			}

			const payload = JSON.parse(event.data);
			if (!Array.isArray(payload.zones)) {
				return;
			}

			latestZones = payload.zones.slice(0, zoneCount);
			while (latestZones.length < zoneCount) {
				latestZones.push(null);
			}

			latestResolution = payload.resolution || "4x4";
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

thresholdInput.value = String(readStoredThreshold());
showStatusCodeInput.checked = readStoredShowStatusCode();
hideInvalidDistanceInput.checked = readStoredHideInvalidDistance();
thresholdInput.addEventListener("change", applyThresholdFromInput);
thresholdInput.addEventListener("blur", applyThresholdFromInput);
showStatusCodeInput.addEventListener("change", applyShowStatusCodeSetting);
hideInvalidDistanceInput.addEventListener("change", applyHideInvalidDistanceSetting);
pauseButton.addEventListener("click", function () {
	setMapPaused(!mapPaused);
});
applyThresholdFromInput();
applyShowStatusCodeSetting();
applyHideInvalidDistanceSetting();
setMapPaused(false);
renderSummary();
renderGrid();
connectSocket();