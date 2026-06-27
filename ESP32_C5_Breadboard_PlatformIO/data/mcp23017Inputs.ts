// @ts-nocheck
const statusElement = document.getElementById("mcp23017WsStatus");
const historyCanvas = document.getElementById("mcp23017HistoryCanvas");
const timeWindowInput = document.getElementById("mcp23017TimeWindowSec");
const pauseGraphButton = document.getElementById("pauseGraphButton");
const graphCaptionElement = document.getElementById("mcp23017GraphCaption");
const hexValueElement = document.getElementById("mcp23017HexValue");
const binaryValueElement = document.getElementById("mcp23017BinaryValue");
const bitRowsElement = document.getElementById("mcp23017BitRows");

if (!statusElement || !historyCanvas || !timeWindowInput || !pauseGraphButton || !graphCaptionElement || !hexValueElement || !binaryValueElement || !bitRowsElement) {
	throw new Error("MCP23017 page elements are missing");
}

const historyContext = historyCanvas.getContext("2d");
if (!historyContext) {
	throw new Error("Canvas context is unavailable");
}

const storageKeyTimeWindowSec = "mcp23017inputs.timeWindowSec";
const channelCount = 8;
const channelColors = ["#1f1f1f", "#8b4513", "#d62828", "#f77f00", "#f2c94c", "#2f9e44", "#1d4ed8", "#6a1b9a"];
const historySamples = [];
let historyDurationSec = 60;
let graphPaused = false;
let graphTimeOffsetSec = 0;
let graphPausedAtRealTimeSec = null;
let socket = null;
let reconnectTimer = null;
let latestValue = 0;

function parseTimeWindowInput() {
	const parsed = Number(timeWindowInput.value.trim());
	if (!Number.isFinite(parsed) || parsed <= 0) {
		return 60;
	}
	return Math.min(3600, Math.max(1, parsed));
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
	graphCaptionElement.textContent = "Time axis: -" + historyDurationSec + " to 0 s. Eight lanes (IN7..IN0), each LOW/HIGH.";
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

function toBinary8(value) {
	let binary = value.toString(2);
	while (binary.length < 8) {
		binary = "0" + binary;
	}
	return binary;
}

function renderBitRows() {
	bitRowsElement.innerHTML = "";
	for (let bit = 0; bit < channelCount; bit += 1) {
		const row = document.createElement("div");
		row.className = "digital-bit-row";

		const name = document.createElement("span");
		name.className = "digital-bit-name";
		name.textContent = "IN" + bit;
		name.style.color = channelColors[bit];

		const state = document.createElement("span");
		state.className = "digital-bit-state";
		const isHigh = ((latestValue >> bit) & 1) === 1;
		state.textContent = isHigh ? "HIGH" : "LOW";
		state.classList.toggle("high", isHigh);
		state.classList.toggle("low", !isHigh);

		row.appendChild(name);
		row.appendChild(state);
		bitRowsElement.appendChild(row);
	}
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

	const padLeft = 54;
	const padRight = 12;
	const padTop = 10;
	const padBottom = 24;
	const graphWidth = width - padLeft - padRight;
	const graphHeight = height - padTop - padBottom;
	const laneHeight = graphHeight / channelCount;

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

	for (let lane = 0; lane < channelCount; lane += 1) {
		const top = padTop + lane * laneHeight;
		ctx.strokeStyle = "#eef1f9";
		ctx.beginPath();
		ctx.moveTo(padLeft, top);
		ctx.lineTo(padLeft + graphWidth, top);
		ctx.stroke();

		const bit = lane;
		ctx.fillStyle = "#5a6075";
		ctx.fillText("IN" + bit, 18, top + laneHeight * 0.62);
	}

	ctx.fillStyle = "#3f4e9e";
	ctx.fillText("s", width - 8, padTop + graphHeight + 16);

	for (let bit = 0; bit < channelCount; bit += 1) {
		const lane = bit;
		const top = padTop + lane * laneHeight;
		const yLow = top + laneHeight * 0.78;
		const yHigh = top + laneHeight * 0.22;

		ctx.strokeStyle = channelColors[bit];
		ctx.lineWidth = 2;
		ctx.beginPath();

		let hasPoint = false;
		let previousY = null;
		for (let i = 0; i < historySamples.length; i += 1) {
			const sample = historySamples[i];
			const state = ((sample.v >> bit) & 1) === 1;
			const y = state ? yHigh : yLow;
			const ageSec = sample.t - virtualNowSec;
			const x = padLeft + ((ageSec + historyDurationSec) / historyDurationSec) * graphWidth;

			if (!hasPoint) {
				ctx.moveTo(x, y);
				hasPoint = true;
			} else {
				if (previousY !== y) {
					ctx.lineTo(x, previousY);
				}
				ctx.lineTo(x, y);
			}
			previousY = y;
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
	const wsUrl = wsProtocol + "://" + window.location.host + "/ws/mcp23017inputs";

	setStatus("Connecting...", false);
	socket = new WebSocket(wsUrl);

	socket.addEventListener("open", function () {
		setStatus("Connected (20 Hz)", false);
	});

	socket.addEventListener("message", function (event) {
		try {
			const payload = JSON.parse(event.data);
			if (typeof payload.bankValue !== "number") {
				return;
			}

			latestValue = payload.bankValue & 0xff;
			hexValueElement.textContent = "0x" + latestValue.toString(16).toUpperCase().padStart(2, "0");
			binaryValueElement.textContent = toBinary8(latestValue);
			renderBitRows();
			if (!graphPaused) {
				historySamples.push({ t: Date.now() / 1000 - graphTimeOffsetSec, v: latestValue });
			}
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

timeWindowInput.value = String(readStoredTimeWindow());
applyTimeWindowFromInput();
renderBitRows();
resizeHistoryCanvas();
requestAnimationFrame(drawGraph);
connectSocket();
