// @ts-nocheck
/** @type {HTMLInputElement | null} */
const serialOutputCheckbox = document.getElementById("serialOutputEnabled");
/** @type {HTMLInputElement | null} */
const potentiometerCheckbox = document.getElementById("includePotentiometerValue");
/** @type {HTMLDivElement | null} */
const statusElement = document.getElementById("status");

if (!serialOutputCheckbox || !potentiometerCheckbox || !statusElement) {
	throw new Error("Serial settings page elements are missing");
}

function setStatus(text, isError) {
	statusElement.textContent = text;
	statusElement.classList.toggle("error", Boolean(isError));
}

function applySettings(settings) {
	serialOutputCheckbox.checked = Boolean(settings.serialOutputEnabled);
	potentiometerCheckbox.checked = Boolean(settings.includePotentiometerValue);
}

async function loadSettings() {
	setStatus("Loading settings...", false);
	try {
		const response = await fetch("/api/serialSettings", { method: "GET" });
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
		body.set(name, value ? "true" : "false");

		const response = await fetch("/api/serialSettings", {
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

serialOutputCheckbox.addEventListener("change", function () {
	updateSetting("serialOutputEnabled", serialOutputCheckbox.checked);
});

potentiometerCheckbox.addEventListener("change", function () {
	updateSetting("includePotentiometerValue", potentiometerCheckbox.checked);
});

loadSettings();
