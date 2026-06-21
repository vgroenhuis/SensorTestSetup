// @ts-nocheck
const interruptCountElement = document.getElementById("interruptCount");
const encoderCountElement = document.getElementById("encoderCount");
const encoderDoubleStepCountElement = document.getElementById("encoderDoubleStepCount");
const encABitElement = document.getElementById("encABit");
const encBBitElement = document.getElementById("encBBit");
const historyCanvas = document.getElementById("historyCanvas");
const timeWindowInput = document.getElementById("timeWindowSec");
const graphCaptionElement = document.getElementById("graphCaption");
const statusElement = document.getElementById("encoderStatus");

if (!interruptCountElement ||
	!encoderCountElement ||
	!encoderDoubleStepCountElement ||
	!encABitElement ||
	!encBBitElement ||
	!historyCanvas ||
	!timeWindowInput ||
	!graphCaptionElement ||
	!statusElement) {
	throw new Error("Rotary encoder page elements are missing");
}

const historyContext = historyCanvas.getContext("2d");
if (!historyContext) {
	throw new Error("Canvas context is unavailable");
}

let socket = null;
let reconnectTimer = null;
let historyDurationSec = 60;
const storageKeyTimeWindowSec = "rotaryEncoder.timeWindowSec";
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

function applyTimeWindowFromInput() {
	historyDurationSec = parseTimeWindowInput();
	timeWindowInput.value = String(historyDurationSec);
	graphCaptionElement.textContent = "Time axis: -" + historyDurationSec + " to 0 s. Position axis auto-scales.";
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
	if (range <= 8) {
		return 1;
	}
	if (range <= 20) {
		return 2;
	}
	if (range <= 50) {
		return 5;
	}
	if (range <= 100) {
		return 10;
	}
	return Math.max(20, Math.ceil(range / 8 / 10) * 10);
	}

function computeYRange() {
	if (historySamples.length === 0) {
		return { min: -1, max: 1 };
	}

	let min = historySamples[0].p;
	let max = historySamples[0].p;
	for (const sample of historySamples) {
		if (sample.p < min) {
			min = sample.p;
		}
		if (sample.p > max) {
			max = sample.p;
		}
	}

	if (min === max) {
		min -= 1;
		max += 1;
	} else {
		const padding = Math.max(1, Math.ceil((max - min) * 0.1));
		min -= padding;
		max += padding;
	}

	return { min, max };
}

function drawGraph() {
	const nowSec = Date.now() / 1000;
	pruneHistory(nowSec);

	const width = historyCanvas.clientWidth;
	const height = historyCanvas.clientHeight;
	const ctx = historyContext;
	const yRange = computeYRange();
	const totalRange = yRange.max - yRange.min;

	const padLeft = 52;
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

	const tickStepPos = yTickStep(totalRange);
	const firstTick = Math.ceil(yRange.min / tickStepPos) * tickStepPos;
	for (let position = firstTick; position <= yRange.max; position += tickStepPos) {
		const ratio = (position - yRange.min) / totalRange;
		const y = padTop + graphHeight - ratio * graphHeight;
		ctx.beginPath();
		ctx.moveTo(padLeft, y);
		ctx.lineTo(padLeft + graphWidth, y);
		ctx.stroke();
		ctx.fillText(String(position), 6, y + 4);
	}

	ctx.fillStyle = "#3f4e9e";
	ctx.fillText("s", width - 8, padTop + graphHeight + 16);
	ctx.fillText("pos", 18, padTop - 2);

	if (historySamples.length >= 2) {
		ctx.strokeStyle = "#2f67ff";
		ctx.lineWidth = 2;
		ctx.beginPath();

		for (let i = 0; i < historySamples.length; i += 1) {
			const sample = historySamples[i];
			const ageSec = sample.t - nowSec;
			const x = padLeft + ((ageSec + historyDurationSec) / historyDurationSec) * graphWidth;
			const ratio = (sample.p - yRange.min) / totalRange;
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
	const wsUrl = wsProtocol + "://" + window.location.host + "/ws/rotaryEncoder";

	setStatus("Connecting...", false);
	socket = new WebSocket(wsUrl);

	socket.addEventListener("open", function () {
		setStatus("Connected (20 Hz)", false);
	});

	socket.addEventListener("message", function (event) {
		try {
			const payload = JSON.parse(event.data);
			if (
				typeof payload.interruptCount !== "number" ||
				typeof payload.encoderCount !== "number" ||
				typeof payload.encoderDoubleStepCount !== "number" ||
				typeof payload.encABBits !== "number"
			) {
				throw new Error("Invalid payload");
			}

			const aBit = String(payload.encABBits & 0x01);
			const bBit = String((payload.encABBits >> 1) & 0x01);
			interruptCountElement.textContent = String(payload.interruptCount);
			encoderCountElement.textContent = String(payload.encoderCount);
			encoderDoubleStepCountElement.textContent = String(payload.encoderDoubleStepCount);
			encABitElement.textContent = aBit;
			encBBitElement.textContent = bBit;
			historySamples.push({ t: Date.now() / 1000, p: payload.encoderCount });
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
timeWindowInput.value = String(readStoredTimeWindow());
applyTimeWindowFromInput();
resizeHistoryCanvas();
requestAnimationFrame(drawGraph);
connectSocket();
