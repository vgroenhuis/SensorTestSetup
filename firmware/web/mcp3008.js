const statusElement = document.getElementById("mcpWsStatus");
const historyCanvas = document.getElementById("mcpHistoryCanvas");
const timeWindowInput = document.getElementById("mcpTimeWindowSec");
const pauseGraphButton = document.getElementById("pauseGraphButton");
const graphCaptionElement = document.getElementById("mcpGraphCaption");
const selectorElement = document.getElementById("channelSelector");
const valuesElement = document.getElementById("channelValues");

if (!statusElement || !historyCanvas || !timeWindowInput || !pauseGraphButton || !graphCaptionElement || !selectorElement || !valuesElement) {
	throw new Error("MCP3008 page elements are missing");
}

const historyContext = historyCanvas.getContext("2d");
if (!historyContext) {
	throw new Error("Canvas context is unavailable");
}

const channelCount = 8;
const minVoltage = 0.0;
const maxVoltage = 3.3;
const storageKeyTimeWindowSec = "mcp3008.timeWindowSec";
const storageKeyVisibleChannels = "mcp3008.visibleChannels";
const channelColors = ["#2f67ff", "#d1495b", "#2a9d8f", "#f4a261", "#7b61ff", "#0096c7", "#6a994e", "#bc6c25"];

let socket = null;
let reconnectTimer = null;
let historyDurationSec = 60;
let graphPaused = false;
let graphTimeOffsetSec = 0;
let graphPausedAtRealTimeSec = null;
const historySamples = [];
const latestVoltages = new Array(channelCount).fill(null);
const visibleChannels = new Array(channelCount).fill(true);

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
		// Ignore storage failures.
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

function readStoredVisibleChannels() {
	try {
		const raw = localStorage.getItem(storageKeyVisibleChannels);
		if (!raw) {
			return;
		}

		const parsed = JSON.parse(raw);
		if (!Array.isArray(parsed) || parsed.length !== channelCount) {
			return;
		}

		for (let i = 0; i < channelCount; i += 1) {
			visibleChannels[i] = Boolean(parsed[i]);
		}

		if (!visibleChannels.some(Boolean)) {
			visibleChannels[0] = true;
		}
	} catch (error) {
		// Ignore storage failures.
	}
}

function storeVisibleChannels() {
	try {
		localStorage.setItem(storageKeyVisibleChannels, JSON.stringify(visibleChannels));
	} catch (error) {
		// Ignore storage failures.
	}
}

function applyTimeWindowFromInput() {
	historyDurationSec = parseTimeWindowInput();
	timeWindowInput.value = String(historyDurationSec);
	graphCaptionElement.textContent = "Time axis: -" + historyDurationSec + " to 0 s. Voltage axis: 0 to 3.3 V.";
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

function clampVoltage(voltage) {
	if (voltage < minVoltage) {
		return minVoltage;
	}
	if (voltage > maxVoltage) {
		return maxVoltage;
	}
	return voltage;
}

function pruneHistory(nowSec) {
	const cutoff = nowSec - historyDurationSec;
	while (historySamples.length > 0 && historySamples[0].t < cutoff) {
		historySamples.shift();
	}
}

function renderChannelSelector() {
	selectorElement.innerHTML = "";

	for (let channel = 0; channel < channelCount; channel += 1) {
		const label = document.createElement("label");
		label.className = "channel-chip";

		const checkbox = document.createElement("input");
		checkbox.type = "checkbox";
		checkbox.checked = visibleChannels[channel];
		checkbox.addEventListener("change", function () {
			if (!checkbox.checked && visibleChannels.filter(Boolean).length === 1) {
				checkbox.checked = true;
				return;
			}

			visibleChannels[channel] = checkbox.checked;
			storeVisibleChannels();
			renderChannelValues();
		});

		const swatch = document.createElement("span");
		swatch.className = "channel-swatch";
		swatch.style.backgroundColor = channelColors[channel];

		const text = document.createElement("span");
		text.textContent = "CH" + channel;

		label.appendChild(checkbox);
		label.appendChild(swatch);
		label.appendChild(text);
		selectorElement.appendChild(label);
	}
}

function renderChannelValues() {
	valuesElement.innerHTML = "";

	for (let channel = 0; channel < channelCount; channel += 1) {
		if (!visibleChannels[channel]) {
			continue;
		}

		const row = document.createElement("div");
		row.className = "channel-value-row";

		const left = document.createElement("span");
		left.className = "channel-value-name";
		left.textContent = "CH" + channel;
		left.style.color = channelColors[channel];

		const right = document.createElement("span");
		right.className = "channel-value-number";
		const value = latestVoltages[channel];
		right.textContent = value === null ? "--" : value.toFixed(3) + " V";

		row.appendChild(left);
		row.appendChild(right);
		valuesElement.appendChild(row);
	}
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

	const yTicks = [0.0, 1.1, 2.2, 3.3];
	for (const yValue of yTicks) {
		const ratio = (yValue - minVoltage) / (maxVoltage - minVoltage);
		const y = padTop + graphHeight - ratio * graphHeight;
		ctx.beginPath();
		ctx.moveTo(padLeft, y);
		ctx.lineTo(padLeft + graphWidth, y);
		ctx.stroke();
		ctx.fillText(yValue.toFixed(1), 6, y + 4);
	}

	ctx.fillStyle = "#3f4e9e";
	ctx.fillText("s", width - 8, padTop + graphHeight + 16);
	ctx.fillText("V", 24, padTop - 2);

	for (let channel = 0; channel < channelCount; channel += 1) {
		if (!visibleChannels[channel]) {
			continue;
		}

		let hasPoint = false;
		ctx.strokeStyle = channelColors[channel];
		ctx.lineWidth = 2;
		ctx.beginPath();

		for (let i = 0; i < historySamples.length; i += 1) {
			const sample = historySamples[i];
			const value = sample.v[channel];
			if (typeof value !== "number") {
				continue;
			}

			const ageSec = sample.t - virtualNowSec;
			const x = padLeft + ((ageSec + historyDurationSec) / historyDurationSec) * graphWidth;
			const ratio = (value - minVoltage) / (maxVoltage - minVoltage);
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
	// Relative: works on the board itself and through the CloSer server's proxy.
	const wsUrl = new URL("ws", window.location.href).href.replace(/^http/, "ws");

	setStatus("Connecting...", false);
	socket = new WebSocket(wsUrl);

	socket.addEventListener("open", function () {
		socket.send(JSON.stringify({ sub: ["mcp3008"] }));
		setStatus("Connected (20 Hz)", false);
	});

	socket.addEventListener("message", function (event) {
		try {
			const payload = JSON.parse(event.data);
			if (payload.ok === false) {
				setStatus("MCP3008 not found", true);
				return;
			}
			setStatus("Connected (20 Hz)", false);
			if (!Array.isArray(payload.channels) || payload.channels.length !== channelCount) {
				return;
			}

			const voltages = payload.channels.map(function (value) {
				return clampVoltage(Number(value));
			});

			for (let i = 0; i < channelCount; i += 1) {
				latestVoltages[i] = voltages[i];
			}

			if (!graphPaused) {
				historySamples.push({ t: Date.now() / 1000 - graphTimeOffsetSec, v: voltages });
			}
			renderChannelValues();
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

readStoredVisibleChannels();
renderChannelSelector();
renderChannelValues();
timeWindowInput.value = String(readStoredTimeWindow());
applyTimeWindowFromInput();
resizeHistoryCanvas();
requestAnimationFrame(drawGraph);
connectSocket();
