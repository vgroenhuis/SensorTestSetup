import { connectDevice } from "./device.js";

const distanceValueElement = document.getElementById("ultrasonicDistanceValue");
const statusElement = document.getElementById("wsStatus");
const historyCanvas = document.getElementById("historyCanvas");
const timeWindowInput = document.getElementById("ultrasonicTimeWindowSec");
const pauseGraphButton = document.getElementById("pauseGraphButton");
const graphCaptionElement = document.getElementById("graphCaption");

if (!distanceValueElement || !statusElement || !historyCanvas || !timeWindowInput || !pauseGraphButton || !graphCaptionElement) {
	throw new Error("Ultrasonic sensor page elements are missing");
}

const historyContext = historyCanvas.getContext("2d");
if (!historyContext) {
	throw new Error("Canvas context is unavailable");
}

const storageKeyTimeWindowSec = "ultrasonicSensor.timeWindowSec";
let historyDurationSec = 60;
let graphPaused = false;
let graphTimeOffsetSec = 0;
let graphPausedAtRealTimeSec = null;
const historySamples = [];

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
	graphCaptionElement.textContent = "Time axis: -" + historyDurationSec + " to 0 s. Distance axis auto-scales (mm).";
	storeTimeWindow(historyDurationSec);
}

function setStatus(text, isError) {
	statusElement.textContent = text;
	statusElement.classList.toggle("error", Boolean(isError));
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
	while (historySamples.length > 0 && historySamples[0].t < cutoff) {
		historySamples.shift();
	}
}

function yTickStep(range) {
	if (range <= 200) {
		return 20;
	}
	if (range <= 500) {
		return 50;
	}
	if (range <= 1000) {
		return 100;
	}
	if (range <= 2000) {
		return 200;
	}
	return 500;
}

function computeRange() {
	let min = Infinity;
	let max = -Infinity;

	for (let i = 0; i < historySamples.length; i += 1) {
		const value = historySamples[i].distanceMm;
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

	if (!Number.isFinite(min) || !Number.isFinite(max)) {
		return { min: 0, max: 1000 };
	}

	if (min === max) {
		const padding = Math.max(20, Math.abs(min) * 0.1);
		min -= padding;
		max += padding;
	} else {
		const padding = Math.max(10, (max - min) * 0.1);
		min -= padding;
		max += padding;
	}

	if (min < 0) {
		min = 0;
	}
	if (max <= min) {
		max = min + 1;
	}

	return { min, max };
}

function drawGraph() {
	const nowSec = Date.now() / 1000;
	const pausedElapsedSec = graphPaused && graphPausedAtRealTimeSec !== null ? nowSec - graphPausedAtRealTimeSec : 0;
	const virtualNowSec = nowSec - graphTimeOffsetSec - pausedElapsedSec;

	if (!graphPaused) {
		pruneHistory(virtualNowSec);
	}

	const width = historyCanvas.clientWidth;
	const height = historyCanvas.clientHeight;
	const ctx = historyContext;
	const range = computeRange();
	const yMin = range.min;
	const yMax = range.max;
	const yRange = yMax - yMin;

	const padLeft = 50;
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

	const yStep = yTickStep(yRange);
	const start = Math.ceil(yMin / yStep) * yStep;
	for (let yValue = start; yValue <= yMax + yStep * 0.5; yValue += yStep) {
		const ratio = (yValue - yMin) / yRange;
		const y = padTop + graphHeight - ratio * graphHeight;
		ctx.beginPath();
		ctx.moveTo(padLeft, y);
		ctx.lineTo(padLeft + graphWidth, y);
		ctx.stroke();
		ctx.fillText(String(Math.round(yValue)), 4, y + 4);
	}

	ctx.fillStyle = "#3f4e9e";
	ctx.fillText("s", width - 8, padTop + graphHeight + 16);
	ctx.fillText("mm", 10, padTop - 2);
	graphCaptionElement.textContent = "Time axis: -" + historyDurationSec + " to 0 s. Distance axis: " + Math.round(yMin) + " to " + Math.round(yMax) + " mm.";

	if (historySamples.length >= 2) {
		ctx.strokeStyle = "#2f67ff";
		ctx.lineWidth = 2;
		ctx.beginPath();

		for (let i = 0; i < historySamples.length; i += 1) {
			const sample = historySamples[i];
			const ageSec = sample.t - virtualNowSec;
			const x = padLeft + ((ageSec + historyDurationSec) / historyDurationSec) * graphWidth;
			const ratio = (sample.distanceMm - yMin) / yRange;
			const y = padTop + graphHeight - ratio * graphHeight;

			if (i === 0) {
				ctx.moveTo(x, y);
			} else {
				ctx.lineTo(x, y);
			}
		}

		ctx.stroke();
	}

	requestAnimationFrame(drawGraph);
}

function applyPayload(payload) {
	if (payload.t !== "ultrasonic") return;
	if (!payload.ok) {
		distanceValueElement.textContent = "--";
		setStatus("No echo: nothing within ~4 m, or the sensor isn't connected", true);
		return;
	}
	setStatus(`Connected (${payload.hz.toFixed(0)} measurements/s)`, false);
	distanceValueElement.textContent = payload.distanceMm.toFixed(1);
	if (!graphPaused) {
		historySamples.push({ t: Date.now() / 1000 - graphTimeOffsetSec, distanceMm: payload.distanceMm });
	}
}

function connectSocket() {
	connectDevice(["ultrasonic"], applyPayload, (text, isError) => setStatus(text, isError));
}

pauseGraphButton.addEventListener("click", function () {
	setGraphPaused(!graphPaused);
});

timeWindowInput.addEventListener("change", applyTimeWindowFromInput);
timeWindowInput.addEventListener("blur", applyTimeWindowFromInput);

window.addEventListener("resize", resizeHistoryCanvas);

historyDurationSec = readStoredTimeWindow();
timeWindowInput.value = String(historyDurationSec);
applyTimeWindowFromInput();
resizeHistoryCanvas();
connectSocket();
requestAnimationFrame(drawGraph);
