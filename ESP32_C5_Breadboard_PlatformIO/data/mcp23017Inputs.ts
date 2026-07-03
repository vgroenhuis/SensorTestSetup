// @ts-nocheck
const statusElement = document.getElementById("mcp23017WsStatus");
const historyCanvas = document.getElementById("mcp23017HistoryCanvas");
const timeWindowInput = document.getElementById("mcp23017TimeWindowSec");
const pauseGraphButton = document.getElementById("pauseGraphButton");
const graphCaptionElement = document.getElementById("mcp23017GraphCaption");
const bankAHexElement = document.getElementById("bankAHexValue");
const bankABinaryElement = document.getElementById("bankABinaryValue");
const bankABitRowsElement = document.getElementById("bankABitRows");
const bankBHexElement = document.getElementById("bankBHexValue");
const bankBBinaryElement = document.getElementById("bankBBinaryValue");
const bankBBitRowsElement = document.getElementById("bankBBitRows");
const bankAConfigBody = document.getElementById("bankAConfigBody");
const bankBConfigBody = document.getElementById("bankBConfigBody");
const applySettingsButton = document.getElementById("applySettingsButton");
const autoApplyCheckbox = document.getElementById("autoApplyCheckbox");
const settingsStatusElement = document.getElementById("settingsStatus");

if (!statusElement || !historyCanvas || !timeWindowInput || !pauseGraphButton || !graphCaptionElement ||
    !bankAHexElement || !bankABinaryElement || !bankABitRowsElement ||
    !bankBHexElement || !bankBBinaryElement || !bankBBitRowsElement ||
    !bankAConfigBody || !bankBConfigBody || !applySettingsButton || !autoApplyCheckbox || !settingsStatusElement) {
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
let latestBankA = 0;
let latestBankB = 0;

let currentSettings = {
	modeA: 0x00,
	pullupA: 0x00,
	modeB: 0xff,
	pullupB: 0xff,
	outputA: 0x03,
	outputB: 0x00
};

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
	graphCaptionElement.textContent = "Time axis: -" + historyDurationSec + " to 0 s. Eight lanes (B7..B0), each LOW/HIGH.";
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

function renderBankBitRows(container, value, modeRegister, prefix) {
	container.innerHTML = "";
	for (let bit = 0; bit < channelCount; bit += 1) {
		const row = document.createElement("div");
		row.className = "digital-bit-row";

		const name = document.createElement("span");
		name.className = "digital-bit-name";
		const isInput = ((modeRegister >> bit) & 1) === 1;
		name.textContent = prefix + bit + (isInput ? " (IN)" : " (OUT)");
		name.style.color = channelColors[bit];

		const state = document.createElement("span");
		state.className = "digital-bit-state";
		const isHigh = ((value >> bit) & 1) === 1;
		state.textContent = isHigh ? "HIGH" : "LOW";
		state.classList.toggle("high", isHigh);
		state.classList.toggle("low", !isHigh);

		row.appendChild(name);
		row.appendChild(state);
		container.appendChild(row);
	}
}

function renderBitRows() {
	bankAHexElement.textContent = "0x" + latestBankA.toString(16).toUpperCase().padStart(2, "0");
	bankABinaryElement.textContent = toBinary8(latestBankA);
	bankBHexElement.textContent = "0x" + latestBankB.toString(16).toUpperCase().padStart(2, "0");
	bankBBinaryElement.textContent = toBinary8(latestBankB);
	renderBankBitRows(bankABitRowsElement, latestBankA, currentSettings.modeA, "A");
	renderBankBitRows(bankBBitRowsElement, latestBankB, currentSettings.modeB, "B");
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
		ctx.fillText("B" + bit, 18, top + laneHeight * 0.62);
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
			if (typeof payload.bankA !== "number" || typeof payload.bankB !== "number") {
				return;
			}

			latestBankA = payload.bankA & 0xff;
			latestBankB = payload.bankB & 0xff;
			renderBitRows();
			if (!graphPaused) {
				historySamples.push({ t: Date.now() / 1000 - graphTimeOffsetSec, v: latestBankB });
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

// --- Settings ---

function onConfigTableChange() {
	if (autoApplyCheckbox.checked) {
		applySettings();
	}
}

function buildConfigTable(tbody, modeReg, pullupReg, outputReg, prefix, reverse) {
	tbody.innerHTML = "";
	const bits = reverse ? [7, 6, 5, 4, 3, 2, 1, 0] : [0, 1, 2, 3, 4, 5, 6, 7];
	for (let i = 0; i < bits.length; i += 1) {
		const bit = bits[i];
		const tr = document.createElement("tr");

		const tdPin = document.createElement("td");
		tdPin.textContent = prefix + bit;
		tdPin.style.color = channelColors[bit];
		tdPin.style.fontWeight = "700";

		const isInput = ((modeReg >> bit) & 1) === 1;
		const hasPullup = ((pullupReg >> bit) & 1) === 1;
		const outputHigh = ((outputReg >> bit) & 1) === 1;

		const tdDir = document.createElement("td");
		const dirSelect = document.createElement("select");
		dirSelect.className = "pin-dir-select";
		dirSelect.dataset.bit = String(bit);
		const optIn = document.createElement("option");
		optIn.value = "1";
		optIn.textContent = "Input";
		const optOut = document.createElement("option");
		optOut.value = "0";
		optOut.textContent = "Output";
		dirSelect.appendChild(optIn);
		dirSelect.appendChild(optOut);
		dirSelect.value = isInput ? "1" : "0";
		dirSelect.addEventListener("change", onConfigTableChange);
		tdDir.appendChild(dirSelect);

		const tdPullup = document.createElement("td");
		const pullupChk = document.createElement("input");
		pullupChk.type = "checkbox";
		pullupChk.className = "pin-pullup-chk";
		pullupChk.dataset.bit = String(bit);
		pullupChk.checked = hasPullup;
		pullupChk.addEventListener("change", onConfigTableChange);
		tdPullup.appendChild(pullupChk);

		const tdOutput = document.createElement("td");
		const outputChk = document.createElement("input");
		outputChk.type = "checkbox";
		outputChk.className = "pin-output-chk";
		outputChk.dataset.bit = String(bit);
		outputChk.checked = outputHigh;
		outputChk.addEventListener("change", onConfigTableChange);
		tdOutput.appendChild(outputChk);

		tr.appendChild(tdPin);
		tr.appendChild(tdDir);
		tr.appendChild(tdPullup);
		tr.appendChild(tdOutput);
		tbody.appendChild(tr);
	}
}

function collectByte(tbody, className) {
	let result = 0;
	const elements = tbody.querySelectorAll("." + className);
	elements.forEach(function (el) {
		const bit = parseInt(el.dataset.bit, 10);
		const value = el.type === "checkbox" ? (el.checked ? 1 : 0) : parseInt(el.value, 10);
		if (value === 1) {
			result |= (1 << bit);
		}
	});
	return result;
}

function applySettingsToUI(settings) {
	currentSettings = settings;
	buildConfigTable(bankAConfigBody, settings.modeA, settings.pullupA, settings.outputA, "A", true);
	buildConfigTable(bankBConfigBody, settings.modeB, settings.pullupB, settings.outputB, "B", false);
	renderBitRows();
}

async function loadSettings() {
	setSettingsStatus("Loading settings...", false);
	try {
		const response = await fetch("/api/mcp23017/settings", { method: "GET" });
		if (!response.ok) {
			throw new Error("HTTP " + response.status);
		}
		const settings = await response.json();
		applySettingsToUI(settings);
		setSettingsStatus("Settings loaded.", false);
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		setSettingsStatus("Failed to load settings: " + message, true);
	}
}

async function applySettings() {
	applySettingsButton.disabled = true;
	setSettingsStatus("Saving...", false);
	try {
		const modeA = collectByte(bankAConfigBody, "pin-dir-select");
		const pullupA = collectByte(bankAConfigBody, "pin-pullup-chk");
		const outputA = collectByte(bankAConfigBody, "pin-output-chk");
		const modeB = collectByte(bankBConfigBody, "pin-dir-select");
		const pullupB = collectByte(bankBConfigBody, "pin-pullup-chk");
		const outputB = collectByte(bankBConfigBody, "pin-output-chk");

		const body = new URLSearchParams();
		body.set("modeA", String(modeA));
		body.set("pullupA", String(pullupA));
		body.set("modeB", String(modeB));
		body.set("pullupB", String(pullupB));
		body.set("outputA", String(outputA));
		body.set("outputB", String(outputB));

		const response = await fetch("/api/mcp23017/settings", {
			method: "POST",
			headers: { "Content-Type": "application/x-www-form-urlencoded" },
			body: body.toString()
		});

		if (!response.ok) {
			throw new Error("HTTP " + response.status);
		}
		const settings = await response.json();
		applySettingsToUI(settings);
		setSettingsStatus("Settings applied.", false);
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		setSettingsStatus("Failed to apply settings: " + message, true);
	} finally {
		applySettingsButton.disabled = false;
	}
}

window.addEventListener("resize", resizeHistoryCanvas);
timeWindowInput.addEventListener("change", applyTimeWindowFromInput);
timeWindowInput.addEventListener("blur", applyTimeWindowFromInput);
pauseGraphButton.addEventListener("click", function () {
	setGraphPaused(!graphPaused);
});
applySettingsButton.addEventListener("click", applySettings);
autoApplyCheckbox.addEventListener("change", function () {
	if (autoApplyCheckbox.checked) {
		applySettings();
	}
});

timeWindowInput.value = String(readStoredTimeWindow());
applyTimeWindowFromInput();
renderBitRows();
resizeHistoryCanvas();
requestAnimationFrame(drawGraph);
loadSettings();
connectSocket();
