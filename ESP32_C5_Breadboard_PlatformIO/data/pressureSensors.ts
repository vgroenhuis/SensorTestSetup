// @ts-nocheck
const statusElement = document.getElementById("pressureWsStatus");
const settingsStatusElement = document.getElementById("pressureSettingsStatus");
const pressureSensorsEnabledInput = document.getElementById("pressureSensorsEnabled");
const historyCanvas = document.getElementById("pressureHistoryCanvas");
const timeWindowInput = document.getElementById("pressureTimeWindowSec");
const pauseGraphButton = document.getElementById("pauseGraphButton");
const zeroCalibrateSensor0Button = document.getElementById("zeroCalibrateSensor0Button");
const zeroCalibrateSensor1Button = document.getElementById("zeroCalibrateSensor1Button");
const graphCaptionElement = document.getElementById("pressureGraphCaption");
const valuesElement = document.getElementById("pressureValues");

if (!statusElement || !settingsStatusElement || !pressureSensorsEnabledInput || !historyCanvas || !timeWindowInput || !pauseGraphButton || !zeroCalibrateSensor0Button || !zeroCalibrateSensor1Button || !graphCaptionElement || !valuesElement) {
	throw new Error("Pressure sensors page elements are missing");
}

const historyContext = historyCanvas.getContext("2d");
if (!historyContext) {
	throw new Error("Canvas context is unavailable");
}

const sensorCount = 2;
const defaultMinPressure = -1.0;
const defaultMaxPressure = 1.0;
const storageKeyTimeWindowSec = "pressureSensors.timeWindowSec";
const sensorColors = ["#2f67ff", "#d1495b"];

let socket = null;
let reconnectTimer = null;
let historyDurationSec = 60;
let graphPaused = false;
let graphTimeOffsetSec = 0;
let graphPausedAtRealTimeSec = null;
let pressureSensorsEnabled = true;
const historySamples = [];
const latestPressures = new Array(sensorCount).fill(null);

function parseTimeWindowInput() {
	const parsed = Number(timeWindowInput.value.trim());
	if (!Number.isFinite(parsed) || parsed <= 0) {
		return 60;
	}

	return Math.min(3600, Math.max(1, parsed));
}

function xTickStep(windowSec) {
	if (windowSec <= 20) {
		return 2;
	}
	if (windowSec <= 60) {
		return 10;
	}
	if (windowSec <= 300) {
		return 30;
	}
	return 60;
}

function readStoredTimeWindow() {
	try {
		const raw = localStorage.getItem(storageKeyTimeWindowSec);
		if (raw === null) {
			return 60;
		}

		const parsed = Number(raw);
		if (!Number.isFinite(parsed) || parsed <= 0) {
			return 60;
		}

		return Math.min(3600, Math.max(1, parsed));
	} catch (error) {
		return 60;
	}
}

function storeTimeWindow(windowSec) {
	try {
		localStorage.setItem(storageKeyTimeWindowSec, String(windowSec));
	} catch (error) {
		// Ignore storage errors.
	}
}

function setGraphPaused(paused) {
	if (paused === graphPaused) {
		return;
	}

	const nowSec = Date.now() / 1000;
	if (paused) {
		graphPausedAtRealTimeSec = nowSec;
	} else if (graphPausedAtRealTimeSec !== null) {
		graphTimeOffsetSec += nowSec - graphPausedAtRealTimeSec;
		graphPausedAtRealTimeSec = null;
	}

	graphPaused = paused;
	pauseGraphButton.textContent = graphPaused ? "Resume graph" : "Pause graph";
}

function applyTimeWindowFromInput() {
	historyDurationSec = parseTimeWindowInput();
	timeWindowInput.value = String(historyDurationSec);
	graphCaptionElement.textContent = "Time axis: -" + historyDurationSec + " to 0 s. Pressure axis auto-scales (barG).";
	storeTimeWindow(historyDurationSec);
}

function setStatus(text, isError) {
	statusElement.textContent = text;
	statusElement.classList.toggle("error", Boolean(isError));
}

function setSettingsStatus(text, isError) {
	settingsStatusElement.textContent = text;
	settingsStatusElement.classList.toggle("error", Boolean(isError));
}

function applyPressureSettings(settings) {
	pressureSensorsEnabled = settings && settings.enabled !== false;
	pressureSensorsEnabledInput.checked = pressureSensorsEnabled;
	setCalibrationButtonsDisabled(!pressureSensorsEnabled);
	pressureSensorsEnabledInput.disabled = false;
}

async function loadPressureSettings() {
	setSettingsStatus("Loading pressure settings...", false);
	pressureSensorsEnabledInput.disabled = true;

	try {
		const response = await fetch("/api/pressureSensors/settings", { method: "GET" });
		if (!response.ok) {
			throw new Error("HTTP " + response.status);
		}

		const settings = await response.json();
		applyPressureSettings(settings);
		setSettingsStatus("Pressure settings loaded.", false);
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		setSettingsStatus("Failed to load pressure settings: " + message, true);
	}
}

async function updatePressureEnabled(enabled) {
	setSettingsStatus("Saving pressure settings...", false);
	pressureSensorsEnabledInput.disabled = true;

	try {
		const body = new URLSearchParams();
		body.set("enabled", enabled ? "true" : "false");

		const response = await fetch("/api/pressureSensors/settings", {
			method: "POST",
			headers: {
				"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"
			},
			body: body.toString()
		});

		if (!response.ok) {
			throw new Error("HTTP " + response.status);
		}

		const settings = await response.json();
		applyPressureSettings(settings);
		setSettingsStatus("Pressure settings synchronized.", false);
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		setSettingsStatus("Failed to save pressure settings: " + message, true);
		await loadPressureSettings();
	}
}

function setCalibrationButtonsDisabled(disabled) {
	zeroCalibrateSensor0Button.disabled = disabled;
	zeroCalibrateSensor1Button.disabled = disabled;
}

async function zeroCalibrateSensor(sensorId) {
	if (!pressureSensorsEnabled) {
		setStatus("Pressure sensors are disabled", true);
		return;
	}

	setCalibrationButtonsDisabled(true);
	setStatus("Zero-calibrating sensor " + sensorId + "...", false);

	try {
		const response = await fetch("/api/pressureSensors/zeroCalibrate", {
			method: "POST",
			headers: {
				"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"
			},
			body: new URLSearchParams({ sensorId: String(sensorId) })
		});

		if (!response.ok) {
			throw new Error("Calibration request failed");
		}

		setStatus("Sensor " + sensorId + " zero-calibrated", false);
	} catch (error) {
		setStatus("Failed to zero-calibrate sensor " + sensorId, true);
	} finally {
		setCalibrationButtonsDisabled(false);
	}
}

function resizeHistoryCanvas() {
	const dpr = window.devicePixelRatio || 1;
	const width = Math.max(10, historyCanvas.clientWidth);
	const height = Math.max(10, historyCanvas.clientHeight);
	historyCanvas.width = Math.floor(width * dpr);
	historyCanvas.height = Math.floor(height * dpr);
	historyContext.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function normalizePressure(pressure) {
	const parsed = Number(pressure);
	return Number.isFinite(parsed) ? parsed : null;
}

function pruneHistory(nowSec) {
	const cutoff = nowSec - historyDurationSec;
	while (historySamples.length > 0 && historySamples[0].t < cutoff) {
		historySamples.shift();
	}
}

function yTickStep(range) {
	if (range <= 1) {
		return 0.2;
	}
	if (range <= 2) {
		return 0.5;
	}
	if (range <= 5) {
		return 1;
	}
	if (range <= 10) {
		return 2;
	}
	if (range <= 20) {
		return 5;
	}
	return 10;
}

function formatPressureTick(value, tickStep) {
	if (tickStep < 1) {
		return value.toFixed(1);
	}
	return String(Math.round(value));
}

function computePressureRange() {
	let min = Infinity;
	let max = -Infinity;

	for (let i = 0; i < historySamples.length; i += 1) {
		const sample = historySamples[i];
		for (let sensor = 0; sensor < sensorCount; sensor += 1) {
			const value = sample.v[sensor];
			if (typeof value !== "number") {
				continue;
			}
			if (value < min) {
				min = value;
			}
			if (value > max) {
				max = value;
			}
		}
	}

	if (!Number.isFinite(min) || !Number.isFinite(max)) {
		return { min: defaultMinPressure, max: defaultMaxPressure };
	}

	if (min === max) {
		const padding = Math.max(0.1, Math.abs(min) * 0.05);
		min -= padding;
		max += padding;
	} else {
		const padding = Math.max(0.05, (max - min) * 0.1);
		min -= padding;
		max += padding;
	}

	if (max <= min) {
		max = min + 1;
	}

	return { min, max };
}

function renderPressureValues() {
	valuesElement.innerHTML = "";

	for (let sensor = 0; sensor < sensorCount; sensor += 1) {
		const card = document.createElement("div");
		card.className = "pressure-reading-card";

		const name = document.createElement("span");
		name.className = "pressure-reading-name";
		name.textContent = "Sensor " + sensor;
		name.style.color = sensorColors[sensor];

		const value = document.createElement("span");
		value.className = "pressure-reading-number";
		const pressure = latestPressures[sensor];
		value.textContent = pressure === null ? "--" : pressure.toFixed(3);

		const unit = document.createElement("span");
		unit.className = "pressure-reading-unit";
		unit.textContent = "barG";

		const valueWrap = document.createElement("span");
		valueWrap.appendChild(value);
		valueWrap.appendChild(unit);

		card.appendChild(name);
		card.appendChild(valueWrap);
		valuesElement.appendChild(card);
	}
}

function drawGraph() {
	const nowSec = Date.now() / 1000;
	const pausedElapsedSec = graphPaused && graphPausedAtRealTimeSec !== null ? nowSec - graphPausedAtRealTimeSec : 0;
	const referenceNowSec = nowSec - graphTimeOffsetSec - pausedElapsedSec;

	if (!graphPaused) {
		pruneHistory(referenceNowSec);
	}

	const width = historyCanvas.clientWidth;
	const height = historyCanvas.clientHeight;
	const ctx = historyContext;
	const pressureRange = computePressureRange();
	const yMin = pressureRange.min;
	const yMax = pressureRange.max;
	const yRange = yMax - yMin;

	const padLeft = 46;
	const padRight = 12;
	const padTop = 10;
	const padBottom = 24;
	const graphWidth = width - padLeft - padRight;
	const graphHeight = height - padTop - padBottom;

	ctx.clearRect(0, 0, width, height);
	ctx.fillStyle = "#ffffff";
	ctx.fillRect(0, 0, width, height);

	ctx.strokeStyle = "#d9dfef";
	ctx.lineWidth = 1;
	ctx.beginPath();
	ctx.rect(padLeft, padTop, graphWidth, graphHeight);
	ctx.stroke();

	ctx.font = "11px Arial, sans-serif";
	ctx.fillStyle = "#5a6075";
	ctx.strokeStyle = "#e8ecf6";

	const tickStepSec = xTickStep(historyDurationSec);
	for (let sec = -historyDurationSec; sec <= 0; sec += tickStepSec) {
		const x = padLeft + ((sec + historyDurationSec) / historyDurationSec) * graphWidth;
		ctx.beginPath();
		ctx.moveTo(x, padTop);
		ctx.lineTo(x, padTop + graphHeight);
		ctx.stroke();
		ctx.fillText(String(Math.round(sec)), x - 8, padTop + graphHeight + 16);
	}

	const tickStepPressure = yTickStep(yRange);
	const firstTick = Math.ceil(yMin / tickStepPressure) * tickStepPressure;
	for (let yValue = firstTick; yValue <= yMax; yValue += tickStepPressure) {
		const ratio = (yValue - yMin) / yRange;
		const y = padTop + graphHeight - ratio * graphHeight;
		ctx.beginPath();
		ctx.moveTo(padLeft, y);
		ctx.lineTo(padLeft + graphWidth, y);
		ctx.stroke();
		ctx.fillText(formatPressureTick(yValue, tickStepPressure), 6, y + 4);
	}

	ctx.fillStyle = "#3f4e9e";
	ctx.fillText("s", width - 8, padTop + graphHeight + 16);
	ctx.fillText("barG", 10, padTop - 2);
	graphCaptionElement.textContent = "Time axis: -" + historyDurationSec + " to 0 s. Pressure axis: " + yMin.toFixed(2) + " to " + yMax.toFixed(2) + " barG.";

	for (let sensor = 0; sensor < sensorCount; sensor += 1) {
		let hasPoint = false;
		ctx.strokeStyle = sensorColors[sensor];
		ctx.lineWidth = 2;
		ctx.beginPath();

		for (let i = 0; i < historySamples.length; i += 1) {
			const sample = historySamples[i];
			const value = sample.v[sensor];
			if (typeof value !== "number") {
				continue;
			}

			const ageSec = sample.t - referenceNowSec;
			const x = padLeft + ((ageSec + historyDurationSec) / historyDurationSec) * graphWidth;
			const ratio = (value - yMin) / yRange;
			const y = padTop + graphHeight - ratio * graphHeight;

			if (!hasPoint) {
				ctx.moveTo(x, y);
				hasPoint = true;
			} else {
				ctx.lineTo(x, y);
			}
		}

		if (hasPoint) {
			ctx.stroke();
		}
	}

	requestAnimationFrame(drawGraph);
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

function connectSocket() {
	const wsProtocol = window.location.protocol === "https:" ? "wss" : "ws";
	const wsUrl = wsProtocol + "://" + window.location.host + "/ws/pressureSensors";

	setStatus("Connecting...", false);
	socket = new WebSocket(wsUrl);

	socket.addEventListener("open", function () {
		setStatus("Connected (20 Hz)", false);
	});

	socket.addEventListener("message", function (event) {
		try {
			const payload = JSON.parse(event.data);
			if (typeof payload.enabled === "boolean") {
				pressureSensorsEnabled = payload.enabled;
				pressureSensorsEnabledInput.checked = pressureSensorsEnabled;
				setCalibrationButtonsDisabled(!pressureSensorsEnabled);
			}
			if (!Array.isArray(payload.pressures) || payload.pressures.length !== sensorCount) {
				return;
			}

			const pressures = payload.pressures.map(function (value) {
				return normalizePressure(value);
			});

			for (let i = 0; i < sensorCount; i += 1) {
				latestPressures[i] = pressures[i];
			}

			if (!graphPaused) {
				historySamples.push({ t: Date.now() / 1000 - graphTimeOffsetSec, v: pressures });
			}
			renderPressureValues();
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

window.addEventListener("resize", resizeHistoryCanvas);
timeWindowInput.addEventListener("change", applyTimeWindowFromInput);
timeWindowInput.addEventListener("blur", applyTimeWindowFromInput);
pauseGraphButton.addEventListener("click", function () {
	setGraphPaused(!graphPaused);
});
zeroCalibrateSensor0Button.addEventListener("click", function () {
	zeroCalibrateSensor(0);
});
zeroCalibrateSensor1Button.addEventListener("click", function () {
	zeroCalibrateSensor(1);
});
pressureSensorsEnabledInput.addEventListener("change", function () {
	updatePressureEnabled(pressureSensorsEnabledInput.checked);
});

timeWindowInput.value = String(readStoredTimeWindow());
applyTimeWindowFromInput();
renderPressureValues();
resizeHistoryCanvas();
requestAnimationFrame(drawGraph);
loadPressureSettings();
connectSocket();