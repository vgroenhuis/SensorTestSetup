// @ts-nocheck
/** @type {HTMLInputElement | null} */
const tofEnabledInput = document.getElementById("tofEnabled");
/** @type {HTMLInputElement | null} */
const outlierThresholdMmInput = document.getElementById("outlierThresholdMm");
/** @type {HTMLInputElement | null} */
const outlierEnabledInput = document.getElementById("outlierEnabled");
/** @type {HTMLSelectElement | null} */
const tofResolutionModeInput = document.getElementById("tofResolutionMode");
/** @type {HTMLDivElement | null} */
const statusElement = document.getElementById("status");

if (!tofEnabledInput || !outlierThresholdMmInput || !outlierEnabledInput || !tofResolutionModeInput || !statusElement) {
	throw new Error("ToF server settings page elements are missing");
}

function setStatus(text, isError) {
	statusElement.textContent = text;
	statusElement.classList.toggle("error", Boolean(isError));
}

function parseOutlierInput() {
	const parsed = Number(outlierThresholdMmInput.value.trim());
	if (!Number.isFinite(parsed) || parsed <= 0) {
		return 350;
	}
	return Math.min(2000, Math.max(20, Math.round(parsed)));
}

function parseModeInput() {
	return tofResolutionModeInput.value === "8x8" ? "8x8" : "4x4";
}

function applySettings(settings) {
	const enabled = settings.enabled !== false;
	tofEnabledInput.checked = enabled;
	outlierEnabledInput.checked = settings.outlierEnabled !== false;
	const outlierThreshold = Number(settings.outlierThresholdMm);
	const mode = settings && settings.mode === "8x8" ? "8x8" : "4x4";
	outlierThresholdMmInput.value = Number.isFinite(outlierThreshold) ? String(Math.round(outlierThreshold)) : "350";
	tofResolutionModeInput.value = mode;
	outlierEnabledInput.disabled = !enabled;
	outlierThresholdMmInput.disabled = !enabled;
	tofResolutionModeInput.disabled = !enabled;
}

async function loadSettings() {
	setStatus("Loading settings...", false);
	try {
		const response = await fetch("/api/tofServerSettings", { method: "GET" });
		if (!response.ok) {
			throw new Error("HTTP " + response.status);
		}

		const settings = await response.json();
		applySettings(settings);
		setStatus("Settings loaded.", false);
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		setStatus("Failed to load settings: " + message, true);
	}
}

async function updateSetting(name, value) {
	setStatus("Saving...", false);
	try {
		const body = new URLSearchParams();
		body.set(name, String(value));

		const response = await fetch("/api/tofServerSettings", {
			method: "POST",
			headers: {
				"Content-Type": "application/x-www-form-urlencoded"
			},
			body: body.toString()
		});

		if (!response.ok) {
			throw new Error("HTTP " + response.status);
		}

		const settings = await response.json();
		applySettings(settings);
		setStatus("Settings synchronized.", false);
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		setStatus("Failed to save setting: " + message, true);
		await loadSettings();
	}
}

tofEnabledInput.addEventListener("change", function () {
	updateSetting("enabled", tofEnabledInput.checked ? "true" : "false");
});

outlierThresholdMmInput.addEventListener("change", function () {
	const value = parseOutlierInput();
	outlierThresholdMmInput.value = String(value);
	updateSetting("outlierThresholdMm", value);
});

outlierThresholdMmInput.addEventListener("blur", function () {
	const value = parseOutlierInput();
	outlierThresholdMmInput.value = String(value);
	updateSetting("outlierThresholdMm", value);
});

outlierEnabledInput.addEventListener("change", function () {
	updateSetting("outlierEnabled", outlierEnabledInput.checked ? "true" : "false");
});

tofResolutionModeInput.addEventListener("change", function () {
	const value = parseModeInput();
	tofResolutionModeInput.value = value;
	updateSetting("mode", value);
});

loadSettings();
