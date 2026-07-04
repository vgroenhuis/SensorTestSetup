// @ts-nocheck
const channelInput = document.getElementById("servoChannel");
const servoMicrosecondsPanel = document.getElementById("servoMicrosecondsPanel");
const pulseInput = document.getElementById("servoPulseUs");
const setButton = document.getElementById("setServoButton");
const setAsMinButton = document.getElementById("setAsMinButton");
const setAsMaxButton = document.getElementById("setAsMaxButton");
const rawPwmPanel = document.getElementById("rawPwmPanel");
const rawPwmSlider = document.getElementById("rawPwmSlider");
const rawPwmValueDisplay = document.getElementById("rawPwmValueDisplay");
const applyRawPwmButton = document.getElementById("applyRawPwmButton");
const autoUpdateCheckbox = document.getElementById("autoUpdateCheckbox");
const frequencyInput = document.getElementById("pwmFrequency");
const setFrequencyButton = document.getElementById("setPwmFrequencyButton");
const configMode = document.getElementById("configMode");
const configMinPulse = document.getElementById("configMinPulse");
const configMaxPulse = document.getElementById("configMaxPulse");
const saveChannelConfigButton = document.getElementById("saveChannelConfigButton");
const autoSaveCheckbox = document.getElementById("autoSaveCheckbox");
const servoCalibrationPanel = document.getElementById("servoCalibrationPanel");
const statusElement = document.getElementById("servoStatus");

if (!channelInput || !servoMicrosecondsPanel || !pulseInput || !setButton || !setAsMinButton || !setAsMaxButton || !rawPwmPanel || !rawPwmSlider || !rawPwmValueDisplay || !applyRawPwmButton || !autoUpdateCheckbox || !frequencyInput || !setFrequencyButton || !configMode || !configMinPulse || !configMaxPulse || !saveChannelConfigButton || !autoSaveCheckbox || !servoCalibrationPanel || !statusElement) {
	throw new Error("PWM servo page elements are missing");
}

let channelConfigs = [];

function setStatus(text, isError) {
	statusElement.textContent = text;
	statusElement.classList.toggle("error", Boolean(isError));
}

function parsePulseUs() {
	const parsed = Number(pulseInput.value.trim());
	if (!Number.isFinite(parsed)) {
		return null;
	}

	const rounded = Math.round(parsed);
	if (rounded < 100 || rounded > 5000) {
		return null;
	}

	return rounded;
}

function parseChannel() {
	const parsed = Number(channelInput.value);
	if (!Number.isFinite(parsed)) {
		return null;
	}

	const rounded = Math.round(parsed);
	if (rounded < 0 || rounded > 15) {
		return null;
	}

	return rounded;
}

function parseFrequency() {
	const parsed = Number(frequencyInput.value.trim());
	if (!Number.isFinite(parsed)) {
		return null;
	}

	if (parsed < 24 || parsed > 1000) {
		return null;
	}

	return parsed;
}

async function setServo() {
	const channel = parseChannel();
	const pulseUs = parsePulseUs();
	if (channel === null || pulseUs === null) {
		setStatus("Invalid input: channel 0-15, pulse 100-5000 us", true);
		return;
	}

	pulseInput.value = String(pulseUs);
	setStatus("Setting servo...", false);
	setButton.disabled = true;

	try {
		const body = new URLSearchParams();
		body.set("channel", String(channel));
		body.set("microseconds", String(pulseUs));

		const response = await fetch("/api/pwmServo", {
			method: "POST",
			headers: {
				"Content-Type": "application/x-www-form-urlencoded"
			},
			body: body.toString()
		});

		if (!response.ok) {
			throw new Error("HTTP " + response.status);
		}

		setStatus("Servo set: channel " + channel + ", " + pulseUs + " us", false);
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		setStatus("Failed to set servo: " + message, true);
	} finally {
		setButton.disabled = false;
	}
}

async function setPwmFrequency() {
	const frequency = parseFrequency();
	if (frequency === null) {
		setStatus("Invalid frequency: must be 24-1000 Hz", true);
		return;
	}

	setStatus("Setting PWM frequency...", false);
	setFrequencyButton.disabled = true;

	try {
		const body = new URLSearchParams();
		body.set("frequency", String(frequency));

		const response = await fetch("/api/pwmServo", {
			method: "POST",
			headers: {
				"Content-Type": "application/x-www-form-urlencoded"
			},
			body: body.toString()
		});

		if (!response.ok) {
			throw new Error("HTTP " + response.status);
		}

		setStatus("PWM frequency set to " + frequency.toFixed(2) + " Hz", false);
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		setStatus("Failed to set frequency: " + message, true);
	} finally {
		setFrequencyButton.disabled = false;
	}
}

function updateControlPanel() {
	const channel = Number(channelInput.value);
	const config = channelConfigs[channel];
	const isRawPwm = config && config.mode === "raw_pwm";
	servoMicrosecondsPanel.classList.toggle("hidden", isRawPwm);
	rawPwmPanel.classList.remove("hidden");
}

async function loadChannelConfigs() {
	try {
		const response = await fetch("/api/pwmServo/config", { method: "GET" });
		if (!response.ok) {
			throw new Error("HTTP " + response.status);
		}
		const configs = await response.json();
		channelConfigs = configs;
		
		const channel = Number(channelInput.value);

		// Update control panel visibility
		updateControlPanel();

		// Update the config panel fields
		if (configs[channel]) {
			const config = configs[channel];
			configMode.value = config.mode;
			configMinPulse.value = String(config.minPulseUs);
			configMaxPulse.value = String(config.maxPulseUs);
			updateServoCalibrationVisibility();
		}
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		setStatus("Failed to load channel configs: " + message, true);
	}
}

function updateServoCalibrationVisibility() {
	servoCalibrationPanel.classList.toggle("hidden", configMode.value !== "servo");
}

async function saveChannelConfig() {
	const channel = Number(channelInput.value);
	const mode = configMode.value;
	
	if (mode !== "servo" && mode !== "raw_pwm") {
		setStatus("Invalid mode: " + mode, true);
		console.error("Invalid mode:", mode);
		return;
	}

	setStatus("Saving channel config...", false);
	saveChannelConfigButton.disabled = true;

	try {
		const body = new URLSearchParams();
		body.set("channel", String(channel));
		body.set("mode", mode);
		
		console.log("Saving channel " + channel + " with mode " + mode);
		
		if (mode === "servo") {
			const minPulseStr = configMinPulse.value.trim();
			const maxPulseStr = configMaxPulse.value.trim();
			const minPulse = Number(minPulseStr);
			const maxPulse = Number(maxPulseStr);
			
			console.log("Min pulse: " + minPulseStr + " -> " + minPulse);
			console.log("Max pulse: " + maxPulseStr + " -> " + maxPulse);
			
			if (!Number.isFinite(minPulse) || !Number.isFinite(maxPulse)) {
				setStatus("Invalid pulse values (not numbers)", true);
				console.error("Non-numeric pulse values");
				return;
			}
			
			if (minPulse >= maxPulse) {
				setStatus("Invalid range: min must be less than max", true);
				console.error("Min >= max");
				return;
			}
			
			if (minPulse < 100 || maxPulse > 5000) {
				setStatus("Invalid pulse range: 100-5000 us", true);
				console.error("Pulse outside valid range");
				return;
			}
			
			body.set("minPulseUs", String(minPulse));
			body.set("maxPulseUs", String(maxPulse));
		}

		console.log("Request body:", body.toString());

		const response = await fetch("/api/pwmServo/config", {
			method: "POST",
			headers: { "Content-Type": "application/x-www-form-urlencoded" },
			body: body.toString()
		});

		console.log("Response status:", response.status);
		
		if (!response.ok) {
			const text = await response.text();
			console.error("Error response:", text);
			throw new Error("HTTP " + response.status + ": " + text);
		}

		const result = await response.json();
		console.log("Success response:", result);
		setStatus("Channel " + channel + " config saved", false);
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		console.error("Save error:", message);
		setStatus("Failed: " + message, true);
	} finally {
		saveChannelConfigButton.disabled = false;
	}
}


channelInput.value = "0";

setButton.addEventListener("click", function () {
	setServo();
});

pulseInput.addEventListener("keydown", function (event) {
	if (event.key === "Enter") {
		setServo();
	}
});

setFrequencyButton.addEventListener("click", function () {
	setPwmFrequency();
});

frequencyInput.addEventListener("keydown", function (event) {
	if (event.key === "Enter") {
		setPwmFrequency();
	}
});

channelInput.addEventListener("change", function () {
	loadChannelConfigs();
});

configMode.addEventListener("change", function () {
	updateServoCalibrationVisibility();
	if (autoSaveCheckbox.checked) {
		saveChannelConfig();
	}
});

function onCalibrationInput() {
	if (autoSaveCheckbox.checked) {
		saveChannelConfig();
	}
}

configMinPulse.addEventListener("change", onCalibrationInput);
configMaxPulse.addEventListener("change", onCalibrationInput);

saveChannelConfigButton.addEventListener("click", function () {
	saveChannelConfig();
});

setAsMinButton.addEventListener("click", function () {
	configMinPulse.value = pulseInput.value;
	if (autoSaveCheckbox.checked) {
		saveChannelConfig();
	}
});

setAsMaxButton.addEventListener("click", function () {
	configMaxPulse.value = pulseInput.value;
	if (autoSaveCheckbox.checked) {
		saveChannelConfig();
	}
});

rawPwmSlider.addEventListener("input", function () {
	const normalized = Number(rawPwmSlider.value);
	rawPwmValueDisplay.textContent = normalized.toFixed(2);

	// For servo mode, also sync the microseconds input
	const channel = Number(channelInput.value);
	const config = channelConfigs[channel];
	if (config && config.mode === "servo") {
		const us = Math.round(config.minPulseUs + normalized * (config.maxPulseUs - config.minPulseUs));
		pulseInput.value = String(us);
	}

	if (autoUpdateCheckbox.checked) {
		applyRawPwm();
	}
});

async function applyRawPwm() {
	const channel = parseChannel();
	if (channel === null) {
		setStatus("Invalid channel", true);
		return;
	}
	const normalized = Number(rawPwmSlider.value);
	setStatus("Applying duty cycle...", false);
	applyRawPwmButton.disabled = true;
	try {
		const body = new URLSearchParams();
		body.set("channel", String(channel));
		body.set("normalized", String(normalized));
		const response = await fetch("/api/pwmServo", {
			method: "POST",
			headers: { "Content-Type": "application/x-www-form-urlencoded" },
			body: body.toString()
		});
		if (!response.ok) {
			throw new Error("HTTP " + response.status);
		}
		setStatus("Channel " + channel + " duty cycle: " + normalized.toFixed(2), false);
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		setStatus("Failed: " + message, true);
	} finally {
		applyRawPwmButton.disabled = false;
	}
}

applyRawPwmButton.addEventListener("click", async function () {
	applyRawPwm();
});

// Persist checkboxes in localStorage
const AUTO_UPDATE_KEY = "pwmServo.autoUpdate";
const AUTO_SAVE_KEY = "pwmServo.autoSave";

autoUpdateCheckbox.checked = localStorage.getItem(AUTO_UPDATE_KEY) === "true";
autoSaveCheckbox.checked = localStorage.getItem(AUTO_SAVE_KEY) === "true";

autoUpdateCheckbox.addEventListener("change", function () {
	localStorage.setItem(AUTO_UPDATE_KEY, String(autoUpdateCheckbox.checked));
});

autoSaveCheckbox.addEventListener("change", function () {
	localStorage.setItem(AUTO_SAVE_KEY, String(autoSaveCheckbox.checked));
});

// Load initial configs
loadChannelConfigs();
