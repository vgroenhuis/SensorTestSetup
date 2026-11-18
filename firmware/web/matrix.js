import { connectDevice, controlBar } from "./device.js";

const $ = (id) => document.getElementById(id);

// What the board can read and drive (main/matrix.h); min/max are the defaults for a new route.
const INPUTS = {
	mcp3008: { label: "MCP3008 analog input", channels: 8, chLabel: (c) => "channel " + c + (c === 7 ? " (pot)" : c === 6 ? " (MH sensor)" : ""), unit: "V", min: 0, max: 3.3 },
	mcp_a: { label: "MCP23017 pin (bank A)", channels: 8, chLabel: (c) => "A" + c, unit: "0/1", min: 0, max: 1 },
	mcp_b: { label: "MCP23017 pin (bank B)", channels: 8, chLabel: (c) => "B" + c, unit: "0/1", min: 0, max: 1 },
	pressure: { label: "Pressure sensor", channels: 2, chLabel: (c) => "sensor " + c, unit: "bar", min: 0, max: 1 },
	ultrasonic: { label: "Ultrasonic distance", channels: 1, unit: "mm", min: 50, max: 1000 },
	tof: { label: "ToF distance", channels: 65, chLabel: (c) => (c === 64 ? "nearest zone" : "zone " + c), unit: "mm", min: 50, max: 1000, defaultCh: 64 },
	loadcell: { label: "Load cell", channels: 1, unit: "load cell units", min: 0, max: 100 },
	encoder: { label: "Motor encoder", channels: 1, unit: "counts", min: 0, max: 1000 },
};
const OUTPUTS = {
	servo: { label: "Servo / PWM (PCA9685)", channels: 16, chLabel: (c) => "channel " + c, note: "0..1 moves the servo between the channel's min and max pulse (PWM servo page)." },
	motor: { label: "DC motor speed", channels: 1, note: "0: full reverse, 0.5: stop, 1: full forward. Only while the motor is in speed mode (DC motor page)." },
	mcp_a: { label: "MCP23017 pin (bank A)", channels: 8, chLabel: (c) => "A" + c, digital: true, note: "Only pins set as outputs on the MCP23017 page." },
	mcp_b: { label: "MCP23017 pin (bank B)", channels: 8, chLabel: (c) => "B" + c, digital: true, note: "Only pins set as outputs on the MCP23017 page." },
};
const PRESETS = {
	potServo: { name: "Pot to servo", in: "mcp3008", in_ch: 7, in_min: 0, in_max: 3.3, out: "servo", out_ch: 0 },
	distanceMotor: { name: "Distance to motor", in: "ultrasonic", in_ch: 0, in_min: 100, in_max: 600, out: "motor", out_ch: 0 },
	pressureLed: { name: "Pressure to A0", in: "pressure", in_ch: 0, in_min: 0, in_max: 0.2, out: "mcp_a", out_ch: 0, threshold: 0.5 },
};

let routes = [];
let editingId = null;       // null: the form makes a new route

function setStatus(text, isError) {
	$("matrixStatus").textContent = text;
	$("matrixStatus").classList.toggle("error", Boolean(isError));
}

function fillSelect(select, entries, value) {
	select.innerHTML = "";
	for (const [v, text] of entries) {
		const option = document.createElement("option");
		option.value = String(v);
		option.textContent = text;
		select.appendChild(option);
	}
	if (value !== undefined) select.value = String(value);
}

function channelEntries(def) {
	return Array.from({ length: def.channels }, (_, c) => [c, def.chLabel ? def.chLabel(c) : ""]);
}

function describeIn(r) {
	const def = INPUTS[r.in];
	return def ? def.label + (def.channels > 1 ? " " + def.chLabel(r.in_ch) : "") : r.in;
}

function describeOut(r) {
	const def = OUTPUTS[r.out];
	return def ? def.label + (def.channels > 1 ? " " + def.chLabel(r.out_ch) : "") : r.out;
}

function showInputType(keepRange) {
	const def = INPUTS[$("inputType").value];
	fillSelect($("inputChannel"), channelEntries(def), def.defaultCh || 0);
	$("inputChannel").hidden = def.channels <= 1;
	$("inputUnit").textContent = def.unit;
	if (!keepRange) {
		$("inputMin").value = String(def.min);
		$("inputMax").value = String(def.max);
	}
}

function showOutputType() {
	const def = OUTPUTS[$("outputType").value];
	fillSelect($("outputChannel"), channelEntries(def), 0);
	$("outputChannel").hidden = def.channels <= 1;
	$("thresholdRow").hidden = !def.digital;
	$("outputNote").textContent = def.note;
}

function fillForm(r) {
	$("routeName").value = r.name || "";
	$("inputType").value = r.in;
	showInputType(true);
	$("inputChannel").value = String(r.in_ch);
	$("inputMin").value = String(r.in_min);
	$("inputMax").value = String(r.in_max);
	$("invertInput").checked = Boolean(r.invert);
	$("outputType").value = r.out;
	showOutputType();
	$("outputChannel").value = String(r.out_ch);
	$("threshold").value = String(r.threshold ?? 0.5);
}

function startEdit(r) {
	editingId = r ? r.id : null;
	$("formTitle").textContent = r ? "Edit route" : "New route";
	$("saveButton").textContent = r ? "Save route" : "Add route";
	$("cancelButton").hidden = !r;
	if (r) {
		fillForm(r);
		$("editCard").scrollIntoView({ behavior: "smooth" });
	}
}

function formRoute() {
	const r = {
		name: $("routeName").value.trim(),
		in: $("inputType").value,
		in_ch: Number($("inputChannel").value) || 0,
		in_min: Number($("inputMin").value),
		in_max: Number($("inputMax").value),
		invert: $("invertInput").checked,
		out: $("outputType").value,
		out_ch: Number($("outputChannel").value) || 0,
		threshold: Number($("threshold").value),
		enabled: true,
	};
	if (editingId !== null) {
		r.id = editingId;
		const old = routes.find((x) => x.id === editingId);
		if (old) r.enabled = old.enabled;
	}
	return r;
}

function nowText(r) {
	const unit = INPUTS[r.in] ? INPUTS[r.in].unit : "";
	return r.ok ? `${Number(r.raw.toFixed(3))} ${unit} → ${r.value.toFixed(2)}` : "no input";
}

let shownConfig = "";

// The table is built again only when the routes change (else a click could land on a row being replaced); the
// live column is updated in place.
function renderRoutes() {
	const body = $("routeTable");
	const config = JSON.stringify(routes.map(({ ok, raw, value, ...rest }) => rest));
	if (config === shownConfig) {
		routes.forEach((r, i) => { if (body.rows[i]) body.rows[i].cells[3].textContent = nowText(r); });
		return;
	}
	shownConfig = config;
	body.innerHTML = "";
	$("emptyState").hidden = routes.length > 0;
	for (const r of routes) {
		const tr = document.createElement("tr");
		tr.innerHTML = `<td></td><td>${describeIn(r)}${r.invert ? " (inverted)" : ""}</td><td>${describeOut(r)}</td>` +
			`<td>${nowText(r)}</td><td><input type="checkbox"${r.enabled ? " checked" : ""}></td>` +
			`<td><button class="btn btn-small" type="button">Edit</button> <button class="btn btn-small btn-danger" type="button">Delete</button></td>`;
		tr.firstChild.textContent = r.name || "(route " + r.id + ")";
		const [enabledBox] = tr.querySelectorAll("input");
		const [editButton, deleteButton] = tr.querySelectorAll("button");
		enabledBox.addEventListener("change", () => dev.send({ matrix: { set: { ...r, enabled: enabledBox.checked } } }));
		editButton.addEventListener("click", () => startEdit(r));
		deleteButton.addEventListener("click", () => {
			if (confirm(`Delete route "${r.name || r.id}"?`)) dev.send({ matrix: { delete: r.id } });
		});
		body.appendChild(tr);
	}
}

const dev = connectDevice(["matrix"], (msg) => {
	if (msg.t === "matrix") {
		routes = msg.routes;
		renderRoutes();
		setStatus(`${routes.length} route${routes.length === 1 ? "" : "s"} (live values 4 times a second)`, false);
	} else if (msg.cmd === "matrix") {
		setStatus(msg.ok ? "Saved on the board." : "Not saved: check the values (range min and max must differ), or all 12 routes are in use.", !msg.ok);
		if (msg.ok) startEdit(null);
	}
}, setStatus);

// While watching, the table's switches and buttons do nothing (the board would refuse).
controlBar($("control"), dev, (mine) => {
	$("editCard").classList.toggle("locked", !mine);
	$("routeTable").classList.toggle("needs-control", true);
	$("routeTable").classList.toggle("locked", !mine);
});

fillSelect($("inputType"), Object.entries(INPUTS).map(([k, d]) => [k, d.label]));
fillSelect($("outputType"), Object.entries(OUTPUTS).map(([k, d]) => [k, d.label]));
showInputType(false);
showOutputType();
$("inputType").addEventListener("change", () => showInputType(false));
$("outputType").addEventListener("change", showOutputType);
$("saveButton").addEventListener("click", () => {
	const r = formRoute();
	if (!Number.isFinite(r.in_min) || !Number.isFinite(r.in_max) || r.in_min === r.in_max) {
		setStatus("The input range needs two different numbers.", true);
		return;
	}
	dev.send({ matrix: { set: r } });
});
$("cancelButton").addEventListener("click", () => startEdit(null));
$("clearAllButton").addEventListener("click", () => {
	if (confirm("Delete all routes?")) dev.send({ matrix: { clear: 1 } });
});
for (const button of document.querySelectorAll("[data-preset]")) {
	button.addEventListener("click", () => fillForm({ threshold: 0.5, invert: false, ...PRESETS[button.dataset.preset] }));
}
