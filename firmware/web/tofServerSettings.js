// The sensor's settings (resolution, distance filter), kept on the device. Changing them needs control; the live
// values come with every "tof" message, so every viewer sees the same.
import { controlBar } from "./device.js";

const outlierThresholdMmInput = document.getElementById("outlierThresholdMm");
const outlierEnabledInput = document.getElementById("outlierEnabled");
const tofResolutionModeInput = document.getElementById("tofResolutionMode");
const statusElement = document.getElementById("status");
const settingsElement = document.getElementById("tofSettings");

let editing = false;        // (don't overwrite a field while it has focus)

function setStatus(text, isError) {
	statusElement.textContent = text;
	statusElement.classList.toggle("error", Boolean(isError));
}

function parseOutlierInput() {
	const parsed = Number(outlierThresholdMmInput.value.trim());
	if (!Number.isFinite(parsed) || parsed <= 0) {
		return 350;
	}
	return Math.min(4000, Math.max(20, Math.round(parsed)));
}

function send(settings) {
	if (!window.tofDevice) return;
	setStatus("Saving...", false);
	window.tofDevice.send({ tof: settings });
}

window.addEventListener("tofSettingsData", (event) => {
	const t = event.detail;
	if (editing) return;
	tofResolutionModeInput.value = t.side === 8 ? "8x8" : "4x4";
	outlierEnabledInput.checked = t.filter;
	outlierThresholdMmInput.value = String(t.max_mm);
});

window.addEventListener("tofDeviceMessage", (event) => {
	const msg = event.detail;
	if (msg.cmd === "tof") setStatus(msg.ok ? "Saved on the device." : "Not saved: a value out of range.", !msg.ok);
});

function start(dev) {
	controlBar(document.getElementById("control"), dev, (mine) => settingsElement.classList.toggle("locked", !mine));
}
if (window.tofDevice) start(window.tofDevice);
else window.addEventListener("tofDeviceReady", (event) => start(event.detail), { once: true });

outlierThresholdMmInput.addEventListener("focus", () => { editing = true; });
outlierThresholdMmInput.addEventListener("blur", () => { editing = false; });
outlierThresholdMmInput.addEventListener("change", () => {
	const value = parseOutlierInput();
	outlierThresholdMmInput.value = String(value);
	send({ max_mm: value });
});
outlierEnabledInput.addEventListener("change", () => send({ filter: outlierEnabledInput.checked }));
tofResolutionModeInput.addEventListener("change", () => send({ side: tofResolutionModeInput.value === "8x8" ? 8 : 4 }));
