import { connectDevice, controlBar } from "./device.js";

const $ = (id) => document.getElementById(id);
const modeInputs = document.querySelectorAll('input[name="motorMode"]');
const slider = $("speedSlider");
const MODE_NAMES = { api: "speed", direct: "direct GPIO", pot: "following the potentiometer" };

let state = null;
let dragging = false;       // (don't move the slider under the user's finger)
let lastSent = 0;
let pending = null;

function setStatus(id, text, isError) {
	$(id).textContent = text;
	$(id).classList.toggle("error", Boolean(isError));
}

function showMode(mode) {
	$("apiPanel").classList.toggle("hidden", mode !== "api");
	$("directPanel").classList.toggle("hidden", mode !== "direct");
	$("potPanel").classList.toggle("hidden", mode !== "pot");
	for (const input of modeInputs) input.checked = input.value === mode;
}

function show(s) {
	state = s;
	const pct = Math.round(s.speed * 100);
	$("speedValue").textContent = (pct > 0 ? "+" : "") + pct;
	const turning = pct === 0 ? "stopped" : (pct > 0 ? "forward" : "reverse") + " (" + (pct > 0 === (s.forward === "ccw") ? "CCW" : "CW") + ")";
	setStatus("motorSummary", `Mode: ${MODE_NAMES[s.mode]}. Motor ${turning}.`, false);
	showMode(s.mode);
	$("directIn1").checked = s.in1;
	$("directIn2").checked = s.in2;
	$("forwardSense").value = s.forward;
	$("potVoltage").textContent = s.pot_ok ? s.pot.toFixed(2) : "-- (MCP3008 not found)";
	if (!dragging && s.mode === "api") {
		slider.value = String(pct);
		$("speedLive").textContent = pct + " %";
	}
}

const dev = connectDevice(["motor"], (msg) => {
	if (msg.t === "motor") show(msg);
	else if (msg.cmd === "motor") setStatus("commandStatus", msg.ok ? "" : "Failed.", !msg.ok);
}, (text, isError) => setStatus("motorSummary", text, isError));

controlBar($("control"), dev, (mine) => $("motorCard").classList.toggle("locked", !mine));

for (const input of modeInputs) {
	input.addEventListener("change", () => { if (input.checked) dev.send({ motor: { mode: input.value } }); });
}

// The slider sends while it moves, at most 20 times a second (the last position always goes out).
function sendSpeed() {
	clearTimeout(pending);
	const send = () => { lastSent = Date.now(); dev.send({ motor: { speed: Number(slider.value) / 100 } }); };
	if (Date.now() - lastSent >= 50) send();
	else pending = setTimeout(send, 50);
}
slider.addEventListener("input", () => { dragging = true; $("speedLive").textContent = slider.value + " %"; sendSpeed(); });
slider.addEventListener("change", () => { dragging = false; sendSpeed(); });
slider.addEventListener("pointerup", () => { dragging = false; });
$("stopButton").addEventListener("click", () => {
	slider.value = "0";
	$("speedLive").textContent = "0 %";
	clearTimeout(pending);
	dev.send({ motor: { speed: 0 } });
});

const sendDirect = () => dev.send({ motor: { in1: $("directIn1").checked, in2: $("directIn2").checked } });
$("directIn1").addEventListener("change", sendDirect);
$("directIn2").addEventListener("change", sendDirect);
$("forwardSense").addEventListener("change", () => dev.send({ motor: { forward: $("forwardSense").value } }));
