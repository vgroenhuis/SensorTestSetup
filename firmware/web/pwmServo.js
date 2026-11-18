import { connectDevice, controlBar } from "./device.js";

const $ = (id) => document.getElementById(id);
const channelInput = $("servoChannel");
const pulseInput = $("servoPulseUs");
const slider = $("valueSlider");
const configMode = $("configMode");
const configMinPulse = $("configMinPulse");
const configMaxPulse = $("configMaxPulse");
const frequencyInput = $("pwmFrequency");
const autoUpdateCheckbox = $("autoUpdateCheckbox");

let channels = [];          // as the device has them (live)
let channel = 0;
let shownConfigFor = -1;    // the config fields show this channel's config (rebuilt when the channel changes)
let frequencyShown = false;
let lastAuto = 0;

function setStatus(id, text, isError) {
	$(id).textContent = text;
	$(id).classList.toggle("error", Boolean(isError));
}

function outputText(c) {
	if (c.duty < 0) return "off";
	if (c.us >= 0) return c.us + " µs";
	return (c.duty * 100).toFixed(1) + " %";
}

function renderTable() {
	const body = $("channelTable");
	body.innerHTML = "";
	channels.forEach((c, i) => {
		const tr = document.createElement("tr");
		tr.classList.toggle("selected", i === channel);
		const range = c.mode === "servo" ? `${c.min}–${c.max} µs` : "0–100 %";
		tr.innerHTML = `<td>${i}</td><td>${c.mode === "servo" ? "Servo" : "Raw PWM"}</td><td>${range}</td><td>${outputText(c)}</td>`;
		tr.addEventListener("click", () => selectChannel(i));
		body.appendChild(tr);
	});
}

function showChannelConfig() {
	const c = channels[channel];
	if (!c) return;
	$("channelTitle").textContent = String(channel);
	if (shownConfigFor !== channel) {
		shownConfigFor = channel;
		configMode.value = c.mode;
		configMinPulse.value = String(c.min);
		configMaxPulse.value = String(c.max);
		if (c.duty >= 0) {
			slider.value = c.mode === "servo" && c.us >= 0 ? String(Math.min(1, Math.max(0, (c.us - c.min) / (c.max - c.min)))) : String(c.duty);
			if (c.us >= 0) pulseInput.value = String(c.us);
		}
	}
	const servo = c.mode === "servo";
	$("servoMicrosecondsPanel").classList.toggle("hidden", !servo);
	$("servoCalibrationPanel").classList.toggle("hidden", configMode.value !== "servo");
	$("sliderLabel").textContent = servo ? "Position" : "Duty cycle";
	updateSliderLabel();
}

function updateSliderLabel() {
	const c = channels[channel];
	const v = Number(slider.value);
	if (c && c.mode === "servo") {
		const us = Math.round(c.min + v * (c.max - c.min));
		$("valueDisplay").textContent = `${v.toFixed(2)} (${us} µs)`;
	} else {
		$("valueDisplay").textContent = (v * 100).toFixed(0) + " %";
	}
}

function selectChannel(i) {
	if (!(i >= 0 && i <= 15)) return;
	channel = i;
	channelInput.value = String(i);
	shownConfigFor = -1;
	showChannelConfig();
	renderTable();
}

function sendValue() {
	dev.send({ pwm: { ch: channel, value: Number(slider.value) } });
}

function parseNumber(input, min, max) {
	const v = Number(input.value.trim());
	return Number.isFinite(v) && v >= min && v <= max ? v : null;
}

const dev = connectDevice(["pwm"], (msg) => {
	if (msg.t === "pwm") {
		if (!msg.ok) setStatus("pwmStatus", "PCA9685 not found", true);
		else setStatus("pwmStatus", "Connected", false);
		channels = msg.ch;
		$("frequencyCaption").textContent = `PWM frequency ${msg.hz.toFixed(1)} Hz (period ${(1000 / msg.hz).toFixed(2)} ms).`;
		if (!frequencyShown) { frequencyInput.value = msg.hz.toFixed(1); frequencyShown = true; }
		renderTable();
		showChannelConfig();
	} else if (msg.cmd) {
		const names = { pwm: "Output", pwm_cfg: "Channel config", pwm_hz: "Frequency" };
		if (msg.cmd in names) setStatus("commandStatus", msg.ok ? names[msg.cmd] + " set." : names[msg.cmd] + ": failed (PCA9685 not answering, or a value out of range).", !msg.ok);
		if (msg.cmd === "pwm_cfg") shownConfigFor = -1;
		if (msg.cmd === "pwm_hz") frequencyShown = false;
	}
}, (text, isError) => setStatus("pwmStatus", text, isError));

controlBar($("control"), dev, (mine) => {
	$("channelCard").classList.toggle("locked", !mine);
	$("frequencyCard").classList.toggle("locked", !mine);
});

channelInput.addEventListener("change", () => selectChannel(Math.round(Number(channelInput.value))));

slider.addEventListener("input", () => {
	updateSliderLabel();
	const c = channels[channel];
	if (c && c.mode === "servo") pulseInput.value = String(Math.round(c.min + Number(slider.value) * (c.max - c.min)));
	// Auto update: at most 20 changes a second (the last one always goes out).
	if (!autoUpdateCheckbox.checked) return;
	const now = Date.now();
	clearTimeout(sendValue.timer);
	if (now - lastAuto >= 50) { lastAuto = now; sendValue(); }
	else sendValue.timer = setTimeout(() => { lastAuto = Date.now(); sendValue(); }, 50);
});
$("applyValueButton").addEventListener("click", sendValue);
$("offButton").addEventListener("click", () => dev.send({ pwm: { ch: channel, off: 1 } }));

function setPulse() {
	const us = parseNumber(pulseInput, 100, 5000);
	if (us === null) { setStatus("commandStatus", "Pulse width: 100–5000 µs", true); return; }
	dev.send({ pwm: { ch: channel, us: Math.round(us) } });
}
$("setServoButton").addEventListener("click", setPulse);
pulseInput.addEventListener("keydown", (e) => { if (e.key === "Enter") setPulse(); });
$("setAsMinButton").addEventListener("click", () => { configMinPulse.value = pulseInput.value; });
$("setAsMaxButton").addEventListener("click", () => { configMaxPulse.value = pulseInput.value; });

configMode.addEventListener("change", () => $("servoCalibrationPanel").classList.toggle("hidden", configMode.value !== "servo"));
$("saveChannelConfigButton").addEventListener("click", () => {
	const cfg = { ch: channel, mode: configMode.value };
	if (cfg.mode === "servo") {
		const min = parseNumber(configMinPulse, 100, 5000), max = parseNumber(configMaxPulse, 100, 5000);
		if (min === null || max === null || min >= max) { setStatus("commandStatus", "Pulse range: 100–5000 µs, min below max", true); return; }
		cfg.min = Math.round(min);
		cfg.max = Math.round(max);
	}
	dev.send({ pwm_cfg: cfg });
});

function setFrequency() {
	const hz = parseNumber(frequencyInput, 24, 1500);
	if (hz === null) { setStatus("commandStatus", "Frequency: 24–1500 Hz", true); return; }
	dev.send({ pwm_hz: hz });
}
$("setPwmFrequencyButton").addEventListener("click", setFrequency);
frequencyInput.addEventListener("keydown", (e) => { if (e.key === "Enter") setFrequency(); });

try {
	autoUpdateCheckbox.checked = localStorage.getItem("pwmServo.autoUpdate") === "true";
	autoUpdateCheckbox.addEventListener("change", () => localStorage.setItem("pwmServo.autoUpdate", String(autoUpdateCheckbox.checked)));
} catch (e) {}
