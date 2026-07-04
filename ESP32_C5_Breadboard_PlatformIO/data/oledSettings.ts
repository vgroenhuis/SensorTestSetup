// @ts-nocheck
/** @type {HTMLInputElement | null} */
const oledCheckbox = document.getElementById("oledEnabled");
/** @type {HTMLDivElement | null} */
const statusElement = document.getElementById("status");

if (!oledCheckbox || !statusElement) {
	throw new Error("OLED settings page elements are missing");
}

function setStatus(text, isError) {
	statusElement.textContent = text;
	statusElement.classList.toggle("error", Boolean(isError));
}

function applySettings(settings) {
	oledCheckbox.checked = Boolean(settings.enabled);
}

async function loadSettings() {
	setStatus("Loading settings...", false);
	try {
		const response = await fetch("/api/oledSettings", { method: "GET" });
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

async function updateSetting(value) {
	setStatus("Saving...", false);
	try {
		const body = new URLSearchParams();
		body.set("enabled", value ? "true" : "false");

		const response = await fetch("/api/oledSettings", {
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

oledCheckbox.addEventListener("change", function () {
	updateSetting(oledCheckbox.checked);
});

loadSettings();
