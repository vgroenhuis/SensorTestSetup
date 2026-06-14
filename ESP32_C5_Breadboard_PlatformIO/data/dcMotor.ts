// @ts-nocheck
const motorStatus = document.getElementById("motorStatus");
const modeInputs = document.querySelectorAll('input[name="motorMode"]');
const directPanel = document.getElementById("directPanel");
const forwardSensePanel = document.getElementById("forwardSensePanel");
const pwmPanel = document.getElementById("pwmPanel");
const potPanel = document.getElementById("potPanel");
const directIn1 = document.getElementById("directIn1");
const directIn2 = document.getElementById("directIn2");
const pwmDuty = document.getElementById("pwmDuty");
const pwmDutySlider = document.getElementById("pwmDutySlider");
const pwmDutyLive = document.getElementById("pwmDutyLive");
const pwmDirection = document.getElementById("pwmDirection");
const forwardSense = document.getElementById("forwardSense");
const potDirectionInfo = document.getElementById("potDirectionInfo");

if (!motorStatus || !directPanel || !forwardSensePanel || !pwmPanel || !potPanel || !directIn1 || !directIn2 || !pwmDuty || !pwmDutySlider || !pwmDutyLive || !pwmDirection || !forwardSense || !potDirectionInfo) {
	throw new Error("DC motor page elements are missing");
}

let pwmUpdateTimer = null;
let lastPwmPostMs = 0;
const pwmPostIntervalMs = 120;

function setStatus(text, isError) {
	motorStatus.textContent = text;
	motorStatus.classList.toggle("error", Boolean(isError));
}

function showMode(mode) {
	directPanel.classList.toggle("hidden", mode !== "direct");
	forwardSensePanel.classList.toggle("hidden", mode !== "pwm" && mode !== "potentiometer");
	pwmPanel.classList.toggle("hidden", mode !== "pwm");
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

function syncDutyInputs(value) {
	const duty = clampDuty(value);
	pwmDuty.value = String(duty);
	pwmDutySlider.value = String(duty);
	pwmDutyLive.textContent = String(duty);
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
	syncDutyInputs(state.pwmDuty);
	pwmDirection.value = state.direction === "reverse" ? "reverse" : "forward";
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

function postPwmNow() {
	lastPwmPostMs = Date.now();
	postMotorSafe(
		{
			mode: "pwm",
			pwmDuty: String(clampDuty(pwmDuty.value)),
			direction: pwmDirection.value,
			forwardSense: forwardSense.value
		},
		"Failed to apply PWM mode"
	);
}

function schedulePwmUpdate() {
	const now = Date.now();
	const elapsed = now - lastPwmPostMs;

	if (elapsed >= pwmPostIntervalMs) {
		if (pwmUpdateTimer !== null) {
			clearTimeout(pwmUpdateTimer);
			pwmUpdateTimer = null;
		}
		postPwmNow();
		return;
	}

	const waitMs = pwmPostIntervalMs - elapsed;
	if (pwmUpdateTimer === null) {
		pwmUpdateTimer = setTimeout(function () {
			pwmUpdateTimer = null;
			postPwmNow();
		}, waitMs);
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

pwmDutySlider.addEventListener("input", function () {
	syncDutyInputs(pwmDutySlider.value);
	schedulePwmUpdate();
});

pwmDuty.addEventListener("change", function () {
	syncDutyInputs(pwmDuty.value);
	schedulePwmUpdate();
});

pwmDuty.addEventListener("input", function () {
	syncDutyInputs(pwmDuty.value);
	schedulePwmUpdate();
});

pwmDirection.addEventListener("change", function () {
	schedulePwmUpdate();
});

forwardSense.addEventListener("change", function () {
	updatePotDirectionInfo();
	postMotorSafe({ forwardSense: forwardSense.value }, "Failed to update forward sense");
});

loadMotorState();
