import { connectDevice, controlBar } from "./device.js";

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
const historyContext = historyCanvas.getContext("2d");

const storageKeyTimeWindowSec = "mcp23017inputs.timeWindowSec";
const channelCount = 8;
const channelColors = ["#1f1f1f", "#8b4513", "#d62828", "#f77f00", "#f2c94c", "#2f9e44", "#1d4ed8", "#6a1b9a"];
const historySamples = [];
let historyDurationSec = 60;
let graphPaused = false;
let graphTimeOffsetSec = 0;
let graphPausedAtRealTimeSec = null;
let latestBankA = 0;
let latestBankB = 0;
let currentSettings = null;     // as the device has them (from the live messages)
let edited = false;             // the table has changes not applied yet: don't overwrite them

function parseTimeWindowInput() {
	const parsed = Number(timeWindowInput.value.trim());
	if (!Number.isFinite(parsed) || parsed <= 0) return 60;
	return Math.min(3600, Math.max(1, parsed));
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
	graphCaptionElement.textContent = "Time axis: -" + historyDurationSec + " to 0 s. Eight lanes (B7..B0), each LOW/HIGH.";
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

function toBinary8(value) {
	return value.toString(2).padStart(8, "0");
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
	const settings = currentSettings || { modeA: 0xff, modeB: 0xff };
	renderBankBitRows(bankABitRowsElement, latestBankA, settings.modeA, "A");
	renderBankBitRows(bankBBitRowsElement, latestBankB, settings.modeB, "B");
}

function xTickStep(windowSec) {
	if (windowSec <= 20) return 2;
	if (windowSec <= 60) return 10;
	if (windowSec <= 300) return 30;
	return 60;
}

function drawGraph() {
	const nowSec = Date.now() / 1000;
	const pausedElapsedSec = graphPaused && graphPausedAtRealTimeSec !== null ? nowSec - graphPausedAtRealTimeSec : 0;
	const virtualNowSec = nowSec - graphTimeOffsetSec - pausedElapsedSec;
	if (!graphPaused) pruneHistory(virtualNowSec);

	const width = historyCanvas.clientWidth;
	const height = historyCanvas.clientHeight;
	const ctx = historyContext;
	const padLeft = 54, padRight = 12, padTop = 10, padBottom = 24;
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
		ctx.fillStyle = "#5a6075";
		ctx.fillText("B" + lane, 18, top + laneHeight * 0.62);
	}
	ctx.fillStyle = "#3f4e9e";
	ctx.fillText("s", width - 8, padTop + graphHeight + 16);

	for (let bit = 0; bit < channelCount; bit += 1) {
		const top = padTop + bit * laneHeight;
		const yLow = top + laneHeight * 0.78;
		const yHigh = top + laneHeight * 0.22;
		ctx.strokeStyle = channelColors[bit];
		ctx.lineWidth = 2;
		ctx.beginPath();
		let previousY = null;
		for (const sample of historySamples) {
			const y = ((sample.v >> bit) & 1) === 1 ? yHigh : yLow;
			const x = padLeft + ((sample.t - virtualNowSec + historyDurationSec) / historyDurationSec) * graphWidth;
			if (previousY === null) ctx.moveTo(x, y);
			else {
				if (previousY !== y) ctx.lineTo(x, previousY);
				ctx.lineTo(x, y);
			}
			previousY = y;
		}
		ctx.stroke();
	}
	requestAnimationFrame(drawGraph);
}

// --- Settings ---

function onConfigTableChange() {
	edited = true;
	if (autoApplyCheckbox.checked) applySettings();
	else setStatus(settingsStatusElement, "Changed: press Apply Settings.", false);
}

function buildConfigTable(tbody, modeReg, pullupReg, outputReg, prefix, reverse) {
	tbody.innerHTML = "";
	const bits = reverse ? [7, 6, 5, 4, 3, 2, 1, 0] : [0, 1, 2, 3, 4, 5, 6, 7];
	for (const bit of bits) {
		const tr = document.createElement("tr");
		const tdPin = document.createElement("td");
		tdPin.textContent = prefix + bit;
		tdPin.style.color = channelColors[bit];
		tdPin.style.fontWeight = "700";

		const tdDir = document.createElement("td");
		const dirSelect = document.createElement("select");
		dirSelect.className = "pin-dir-select";
		dirSelect.dataset.bit = String(bit);
		dirSelect.innerHTML = '<option value="1">Input</option><option value="0">Output</option>';
		dirSelect.value = ((modeReg >> bit) & 1) === 1 ? "1" : "0";
		dirSelect.addEventListener("change", onConfigTableChange);
		tdDir.appendChild(dirSelect);

		const tdPullup = document.createElement("td");
		const pullupChk = document.createElement("input");
		pullupChk.type = "checkbox";
		pullupChk.className = "pin-pullup-chk";
		pullupChk.dataset.bit = String(bit);
		pullupChk.checked = ((pullupReg >> bit) & 1) === 1;
		pullupChk.addEventListener("change", onConfigTableChange);
		tdPullup.appendChild(pullupChk);

		const tdOutput = document.createElement("td");
		const outputChk = document.createElement("input");
		outputChk.type = "checkbox";
		outputChk.className = "pin-output-chk";
		outputChk.dataset.bit = String(bit);
		outputChk.checked = ((outputReg >> bit) & 1) === 1;
		outputChk.addEventListener("change", onConfigTableChange);
		tdOutput.appendChild(outputChk);

		tr.append(tdPin, tdDir, tdPullup, tdOutput);
		tbody.appendChild(tr);
	}
}

function collectByte(tbody, className) {
	let result = 0;
	tbody.querySelectorAll("." + className).forEach((el) => {
		const value = el.type === "checkbox" ? (el.checked ? 1 : 0) : parseInt(el.value, 10);
		if (value === 1) result |= 1 << parseInt(el.dataset.bit, 10);
	});
	return result;
}

function sameSettings(a, b) {
	return a && b && Object.keys(a).every((key) => a[key] === b[key]);
}

function showSettings(settings) {
	if (sameSettings(settings, currentSettings)) return;
	currentSettings = settings;
	if (edited) return;
	buildConfigTable(bankAConfigBody, settings.modeA, settings.pullupA, settings.outputA, "A", true);
	buildConfigTable(bankBConfigBody, settings.modeB, settings.pullupB, settings.outputB, "B", false);
}

function applySettings() {
	setStatus(settingsStatusElement, "Applying...", false);
	dev.send({
		mcp23017: {
			modeA: collectByte(bankAConfigBody, "pin-dir-select"),
			pullupA: collectByte(bankAConfigBody, "pin-pullup-chk"),
			outputA: collectByte(bankAConfigBody, "pin-output-chk"),
			modeB: collectByte(bankBConfigBody, "pin-dir-select"),
			pullupB: collectByte(bankBConfigBody, "pin-pullup-chk"),
			outputB: collectByte(bankBConfigBody, "pin-output-chk"),
		},
	});
}

const dev = connectDevice(["mcp23017"], (msg) => {
	if (msg.t === "mcp23017") {
		if (!msg.ok) {
			setStatus(statusElement, "MCP23017 not found", true);
			return;
		}
		setStatus(statusElement, "Connected (20 Hz)", false);
		latestBankA = msg.a;
		latestBankB = msg.b;
		showSettings(msg.cfg);
		renderBitRows();
		if (!graphPaused) historySamples.push({ t: Date.now() / 1000 - graphTimeOffsetSec, v: latestBankB });
	} else if (msg.cmd === "mcp23017") {
		edited = false;
		currentSettings = null;         // (the next live message rebuilds the table from what the device has)
		setStatus(settingsStatusElement, msg.ok ? "Settings applied." : "Failed: MCP23017 not answering.", !msg.ok);
	}
}, (text, isError) => setStatus(statusElement, text, isError));

controlBar(document.getElementById("control"), dev, (mine) => {
	document.getElementById("pinConfig").classList.toggle("locked", !mine);
	if (!mine && edited) { edited = false; currentSettings = null; }      // (back to what the device has)
});

window.addEventListener("resize", resizeHistoryCanvas);
timeWindowInput.addEventListener("change", applyTimeWindowFromInput);
timeWindowInput.addEventListener("blur", applyTimeWindowFromInput);
pauseGraphButton.addEventListener("click", () => setGraphPaused(!graphPaused));
applySettingsButton.addEventListener("click", applySettings);
autoApplyCheckbox.addEventListener("change", () => { if (autoApplyCheckbox.checked && edited) applySettings(); });

timeWindowInput.value = String(readStoredTimeWindow());
applyTimeWindowFromInput();
renderBitRows();
resizeHistoryCanvas();
requestAnimationFrame(drawGraph);
