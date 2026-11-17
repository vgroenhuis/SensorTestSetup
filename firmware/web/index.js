const statusElement = document.getElementById("status");

function show(s) {
	const uptimeMin = Math.floor(s.uptime_s / 60);
	statusElement.textContent =
		`${s.host} · firmware ${s.fw} · up ${uptimeMin} min · ${s.ssid} ${s.rssi} dBm · ` +
		`${(s.heap / 1024).toFixed(0)} kB free · sensors ${s.sample_hz.toFixed(0)} Hz · ` +
		`MCP3008 ${s.mcp3008 ? "ok" : "not found"}`;
	statusElement.classList.toggle("error", !s.mcp3008);
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
