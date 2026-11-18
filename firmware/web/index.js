const statusElement = document.getElementById("status");
const partsElement = document.getElementById("parts");

const PART_NAMES = {
	mcp3008: "MCP3008", mcp23017: "MCP23017", pca9685: "PCA9685", tca9548: "TCA9548",
	pressure0: "pressure sensor 0", pressure1: "pressure sensor 1", hx711: "HX711 load cell",
	ultrasonic: "ultrasonic sensor (no echo)",
	vl53l7cx: "VL53L7CX ToF sensor",
};

function show(s) {
	const uptimeMin = Math.floor(s.uptime_s / 60);
	statusElement.textContent =
		`${s.host} · firmware ${s.fw} · up ${uptimeMin} min · ${s.ssid} ${s.rssi} dBm · ` +
		`${(s.heap / 1024).toFixed(0)} kB free · ${s.clients} viewer${s.clients === 1 ? "" : "s"}`;
	const missing = Object.keys(PART_NAMES).filter((key) => s.parts[key] === false);
	partsElement.textContent = missing.length ? "Not answering: " + missing.map((key) => PART_NAMES[key]).join(", ")
		: "All parts answer.";
	partsElement.classList.toggle("error", missing.length > 0);
}

function connect() {
	const socket = new WebSocket(new URL("ws", window.location.href).href.replace(/^http/, "ws"));
	socket.addEventListener("open", () => socket.send(JSON.stringify({ sub: ["status"] })));
	socket.addEventListener("message", (event) => {
		const payload = JSON.parse(event.data);
		if (payload.t === "status") show(payload);
	});
	socket.addEventListener("close", () => {
		statusElement.textContent = "Disconnected, retrying...";
		statusElement.classList.add("error");
		setTimeout(connect, 1000);
	});
}

connect();
