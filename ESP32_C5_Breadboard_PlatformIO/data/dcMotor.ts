// @ts-nocheck
const motorStatus = document.getElementById("motorStatus");
const modeInputs = document.querySelectorAll('input[name="motorMode"]');
const directPanel = document.getElementById("directPanel");
const forwardSensePanel = document.getElementById("forwardSensePanel");
const normalizedPanel = document.getElementById("normalizedPanel");
const potPanel = document.getElementById("potPanel");
const directIn1 = document.getElementById("directIn1");
const directIn2 = document.getElementById("directIn2");
const forwardSense = document.getElementById("forwardSense");
const potDirectionInfo = document.getElementById("potDirectionInfo");
const normalizedSlider = document.getElementById("normalizedSlider");
const normalizedLive = document.getElementById("normalizedLive");
const normalizedApplyBtn = document.getElementById("normalizedApplyBtn");
const pwmSpeedSlider = document.getElementById("pwmSpeedSlider");
const pwmSpeedLive = document.getElementById("pwmSpeedLive");
const pwmSpeedApplyBtn = document.getElementById("pwmSpeedApplyBtn");
const motorDirectionFwdBtn = document.getElementById("motorDirectionFwdBtn");
const motorDirectionRevBtn = document.getElementById("motorDirectionRevBtn");

if (!motorStatus || !directPanel || !forwardSensePanel || !potPanel || !directIn1 || !directIn2 || !forwardSense || !potDirectionInfo || !normalizedPanel || !normalizedSlider || !normalizedLive || !normalizedApplyBtn || !pwmSpeedSlider || !pwmSpeedLive || !pwmSpeedApplyBtn || !motorDirectionFwdBtn || !motorDirectionRevBtn) {
	throw new Error("DC motor page elements are missing");
}



function setStatus(text, isError) {
	motorStatus.textContent = text;
	motorStatus.classList.toggle("error", Boolean(isError));
}

function showMode(mode) {
	directPanel.classList.toggle("hidden", mode !== "direct");
	forwardSensePanel.classList.toggle("hidden", mode !== "potentiometer" && mode !== "motor_api");
	normalizedPanel.classList.toggle("hidden", mode !== "motor_api");
	potPanel.classList.toggle("hidden", mode !== "potentiometer");
	for (const modeInput of modeInputs) {
		modeInput.checked = modeInput.value === mode;
	}
}

function clampDuty(value) {
	const parsed = Number(value);
	if (!Number.isFinite(parsed)) {
		return 0;
	}
	return Math.max(0, Math.min(255, Math.round(parsed)));
}



function updatePotDirectionInfo() {
	const sense = forwardSense.value === "cw" ? "cw" : "ccw";
	const forwardLabel = sense.toUpperCase();
	const reverseLabel = sense === "cw" ? "CCW" : "CW";
	potDirectionInfo.innerHTML =
		"A4 = 1.65V: motor stop.<br>" +
		"A4 = 0V: full speed reverse (" + reverseLabel + ").<br>" +
		"A4 = 3.3V: full speed forward (" + forwardLabel + ").";
}

function applyState(state) {
	showMode(state.mode);
	directIn1.checked = Boolean(state.directIn1);
	directIn2.checked = Boolean(state.directIn2);
	forwardSense.value = state.forwardSense === "cw" ? "cw" : "ccw";
	updatePotDirectionInfo();
}

async function postMotor(params) {
	setStatus("Applying...", false);
	const body = new URLSearchParams();
	for (const key of Object.keys(params)) {
		body.set(key, String(params[key]));
	}

	const response = await fetch("/api/motor", {
		method: "POST",
		headers: { "Content-Type": "application/x-www-form-urlencoded" },
		body: body.toString()
	});

	if (!response.ok) {
		throw new Error("HTTP " + response.status);
	}

	const state = await response.json();
	applyState(state);
	setStatus("Motor state updated.", false);
}

async function loadMotorState() {
	setStatus("Loading motor state...", false);
	try {
		const response = await fetch("/api/motor", { method: "GET" });
		if (!response.ok) {
			throw new Error("HTTP " + response.status);
		}
		const state = await response.json();
		applyState(state);
		setStatus("Motor state loaded.", false);
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		setStatus("Failed to load motor state: " + message, true);
	}
}

async function postMotorSafe(params, errorPrefix) {
	try {
		await postMotor(params);
	} catch (error) {
		const message = error instanceof Error ? error.message : String(error);
		setStatus(errorPrefix + ": " + message, true);
		await loadMotorState();
	}
}

for (const modeInput of modeInputs) {
	modeInput.addEventListener("change", async function () {
		if (!modeInput.checked) {
			return;
		}

		await postMotorSafe({ mode: modeInput.value }, "Failed to update mode");
	});
}

directIn1.addEventListener("change", function () {
	postMotorSafe(
		{
			mode: "direct",
			directIn1: directIn1.checked ? "true" : "false",
			directIn2: directIn2.checked ? "true" : "false"
		},
		"Failed to apply direct outputs"
	);
});

directIn2.addEventListener("change", function () {
	postMotorSafe(
		{
			mode: "direct",
			directIn1: directIn1.checked ? "true" : "false",
			directIn2: directIn2.checked ? "true" : "false"
		},
		"Failed to apply direct outputs"
	);
});

forwardSense.addEventListener("change", function () {
	updatePotDirectionInfo();
	postMotorSafe({ forwardSense: forwardSense.value }, "Failed to update forward sense");
});

// Normalized mode controls
normalizedSlider.addEventListener("input", function () {
	const value = Number(normalizedSlider.value) / 100.0;
	normalizedLive.textContent = value.toFixed(2);
});

normalizedApplyBtn.addEventListener("click", function () {
	const normalized = Number(normalizedSlider.value) / 100.0;
	setStatus("Applying normalized input...", false);
	const body = new URLSearchParams();
	body.set("mode", "motor_api");
	body.set("normalized", String(normalized));
	
	fetch("/api/motor", {
		method: "POST",
		headers: { "Content-Type": "application/x-www-form-urlencoded" },
		body: body.toString()
	}).then(response => {
		if (!response.ok) {
			throw new Error("HTTP " + response.status);
		}
		return response.json();
	}).then(state => {
		applyState(state);
		setStatus("Normalized input applied. Motor responding...", false);
	}).catch(error => {
		const message = error instanceof Error ? error.message : String(error);
		setStatus("Failed to apply normalized input: " + message, true);
		loadMotorState();
	});
});

// PWM speed controls
pwmSpeedSlider.addEventListener("input", function () {
	const value = Number(pwmSpeedSlider.value) / 100.0;
	pwmSpeedLive.textContent = value.toFixed(2);
});

pwmSpeedApplyBtn.addEventListener("click", function () {
	const normalized = Number(pwmSpeedSlider.value) / 100.0;
	setStatus("Applying PWM speed...", false);
	const body = new URLSearchParams();
	body.set("mode", "motor_api");
	body.set("pwmNormalized", String(normalized));
	
	fetch("/api/motor", {
		method: "POST",
		headers: { "Content-Type": "application/x-www-form-urlencoded" },
		body: body.toString()
	}).then(response => {
		if (!response.ok) {
			throw new Error("HTTP " + response.status);
		}
		return response.json();
	}).then(state => {
		applyState(state);
		setStatus("PWM speed applied. Motor responding...", false);
	}).catch(error => {
		const message = error instanceof Error ? error.message : String(error);
		setStatus("Failed to apply PWM speed: " + message, true);
		loadMotorState();
	});
});

motorDirectionFwdBtn.addEventListener("click", function () {
	setStatus("Setting direction to forward...", false);
	const body = new URLSearchParams();
	body.set("mode", "motor_api");
	body.set("direction_boolean", "true");
	
	fetch("/api/motor", {
		method: "POST",
		headers: { "Content-Type": "application/x-www-form-urlencoded" },
		body: body.toString()
	}).then(response => {
		if (!response.ok) {
			throw new Error("HTTP " + response.status);
		}
		return response.json();
	}).then(state => {
		applyState(state);
		setStatus("Direction set to forward.", false);
	}).catch(error => {
		const message = error instanceof Error ? error.message : String(error);
		setStatus("Failed to set direction: " + message, true);
		loadMotorState();
	});
});

motorDirectionRevBtn.addEventListener("click", function () {
	setStatus("Setting direction to reverse...", false);
	const body = new URLSearchParams();
	body.set("mode", "motor_api");
	body.set("direction_boolean", "false");
	
	fetch("/api/motor", {
		method: "POST",
		headers: { "Content-Type": "application/x-www-form-urlencoded" },
		body: body.toString()
	}).then(response => {
		if (!response.ok) {
			throw new Error("HTTP " + response.status);
		}
		return response.json();
	}).then(state => {
		applyState(state);
		setStatus("Direction set to reverse.", false);
	}).catch(error => {
		const message = error instanceof Error ? error.message : String(error);
		setStatus("Failed to set direction: " + message, true);
		loadMotorState();
	});
});

loadMotorState();
