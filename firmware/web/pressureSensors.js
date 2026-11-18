import { connectDevice, controlBar } from "./device.js";

const statusElement = document.getElementById("pressureWsStatus");
const calibrationStatusElement = document.getElementById("calibrationStatus");
const historyCanvas = document.getElementById("pressureHistoryCanvas");
const timeWindowInput = document.getElementById("pressureTimeWindowSec");
const pauseGraphButton = document.getElementById("pauseGraphButton");
const zeroButtons = [document.getElementById("zeroCalibrateSensor0Button"), document.getElementById("zeroCalibrateSensor1Button")];
const graphCaptionElement = document.getElementById("pressureGraphCaption");
const valuesElement = document.getElementById("pressureValues");
const historyContext = historyCanvas.getContext("2d");

const sensorCount = 2;
const defaultMinPressure = -1.0;
const defaultMaxPressure = 1.0;
const storageKeyTimeWindowSec = "pressureSensors.timeWindowSec";
const sensorColors = ["#2f67ff", "#d1495b"];

let historyDurationSec = 60;
let graphPaused = false;
let graphTimeOffsetSec = 0;
let graphPausedAtRealTimeSec = null;
const historySamples = [];
const latestPressures = new Array(sensorCount).fill(null);
const sensorPresent = new Array(sensorCount).fill(true);

function parseTimeWindowInput() {
	const parsed = Number(timeWindowInput.value.trim());
	if (!Number.isFinite(parsed) || parsed <= 0) return 60;
	return Math.min(3600, Math.max(1, parsed));
}

function xTickStep(windowSec) {
	if (windowSec <= 20) return 2;
	if (windowSec <= 60) return 10;
	if (windowSec <= 300) return 30;
	return 60;
}

function readStoredTimeWindow() {
	try {
		const parsed = Number(localStorage.getItem(storageKeyTimeWindowSec));
		if (!Number.isFinite(parsed) || parsed <= 0) return 60;
		return Math.min(3600, Math.max(1, parsed));
	} catch (error) {
		return 60;
	}
}

function storeTimeWindow(windowSec) {
	try { localStorage.setItem(storageKeyTimeWindowSec, String(windowSec)); } catch (error) {}
}

function setGraphPaused(paused) {
	if (paused === graphPaused) return;
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
	storeTimeWindow(historyDurationSec);
}

function setStatus(element, text, isError) {
	element.textContent = text;
	element.classList.toggle("error", Boolean(isError));
}

function resizeHistoryCanvas() {
	const dpr = window.devicePixelRatio || 1;
	const width = Math.max(10, historyCanvas.clientWidth);
	const height = Math.max(10, historyCanvas.clientHeight);
	historyCanvas.width = Math.floor(width * dpr);
	historyCanvas.height = Math.floor(height * dpr);
	historyContext.setTransform(dpr, 0, 0, dpr, 0, 0);
}

function pruneHistory(nowSec) {
	const cutoff = nowSec - historyDurationSec;
	while (historySamples.length > 0 && historySamples[0].t < cutoff) historySamples.shift();
}

function yTickStep(range) {
	if (range <= 1) return 0.2;
	if (range <= 2) return 0.5;
	if (range <= 5) return 1;
	if (range <= 10) return 2;
	if (range <= 20) return 5;
	return 10;
}

function formatPressureTick(value, tickStep) {
	return tickStep < 1 ? value.toFixed(1) : String(Math.round(value));
}

function computePressureRange() {
	let min = Infinity;
	let max = -Infinity;
	for (const sample of historySamples) {
		for (const value of sample.v) {
			if (typeof value !== "number") continue;
			if (value < min) min = value;
			if (value > max) max = value;
		}
	}
	if (!Number.isFinite(min) || !Number.isFinite(max)) return { min: defaultMinPressure, max: defaultMaxPressure };
	if (min === max) {
		const padding = Math.max(0.1, Math.abs(min) * 0.05);
		min -= padding;
		max += padding;
	} else {
		const padding = Math.max(0.05, (max - min) * 0.1);
		min -= padding;
		max += padding;
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
		const unit = document.createElement("span");
		unit.className = "pressure-reading-unit";
		const pressure = latestPressures[sensor];
		if (!sensorPresent[sensor]) {
			value.textContent = "not found";
		} else {
			value.textContent = pressure === null ? "--" : pressure.toFixed(3);
			unit.textContent = "barG";
		}
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
	if (!graphPaused) pruneHistory(referenceNowSec);

	const width = historyCanvas.clientWidth;
	const height = historyCanvas.clientHeight;
	const ctx = historyContext;
	const { min: yMin, max: yMax } = computePressureRange();
	const yRange = yMax - yMin;
	const padLeft = 46, padRight = 12, padTop = 10, padBottom = 24;
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
	for (let yValue = Math.ceil(yMin / tickStepPressure) * tickStepPressure; yValue <= yMax; yValue += tickStepPressure) {
		const y = padTop + graphHeight - ((yValue - yMin) / yRange) * graphHeight;
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
		for (const sample of historySamples) {
			const value = sample.v[sensor];
			if (typeof value !== "number") { hasPoint = false; continue; }
			const x = padLeft + ((sample.t - referenceNowSec + historyDurationSec) / historyDurationSec) * graphWidth;
			const y = padTop + graphHeight - ((value - yMin) / yRange) * graphHeight;
			if (!hasPoint) { ctx.moveTo(x, y); hasPoint = true; } else ctx.lineTo(x, y);
		}
		ctx.stroke();
	}
	requestAnimationFrame(drawGraph);
}

const dev = connectDevice(["pressure"], (msg) => {
	if (msg.t === "pressure") {
		const pressures = msg.bar.map((value, i) => (msg.ok[i] ? value : null));
		for (let i = 0; i < sensorCount; i += 1) {
			latestPressures[i] = pressures[i];
			sensorPresent[i] = msg.ok[i];
		}
		if (!graphPaused) historySamples.push({ t: Date.now() / 1000 - graphTimeOffsetSec, v: pressures });
		renderPressureValues();
		const absent = msg.ok.every((ok) => !ok);
		setStatus(statusElement, absent ? "No pressure sensor answers (TCA9548 or sensors not connected)" : `Connected (${msg.hz.toFixed(0)} readings/s per sensor)`, absent);
	} else if (msg.cmd === "pressure_zero") {
		setStatus(calibrationStatusElement, msg.ok ? "Zero-calibrated." : "Calibration failed: sensor not answering.", !msg.ok);
	}
}, (text, isError) => setStatus(statusElement, text, isError));

controlBar(document.getElementById("control"), dev, (mine) => {
	document.querySelector(".calibration-actions").classList.toggle("locked", !mine);
});

zeroButtons.forEach((button, sensor) => button.addEventListener("click", () => {
	setStatus(calibrationStatusElement, "Zero-calibrating sensor " + sensor + "...", false);
	dev.send({ pressure_zero: sensor });
}));

window.addEventListener("resize", resizeHistoryCanvas);
timeWindowInput.addEventListener("change", applyTimeWindowFromInput);
timeWindowInput.addEventListener("blur", applyTimeWindowFromInput);
pauseGraphButton.addEventListener("click", () => setGraphPaused(!graphPaused));

timeWindowInput.value = String(readStoredTimeWindow());
applyTimeWindowFromInput();
renderPressureValues();
resizeHistoryCanvas();
requestAnimationFrame(drawGraph);
