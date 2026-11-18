// Shared by the pages: the one WebSocket to the device (/ws, relative, so it also works through the lab demos
// site's proxy), and the control bar for pages that change something.
//
//   const dev = connectDevice(["pressure"], (msg) => ..., (text, isError) => ...);
//   dev.send({ pressure_zero: 0 });
//   controlBar(document.getElementById("control"), dev);
//
// Watching is open to everyone; changing something needs control: one person at a time, with the code the OLED
// shows (closer_access on the device).

export function connectDevice(topics, onMessage, onConnection) {
	const handlers = [];
	let socket = null;
	const dev = {
		send(obj) {
			if (socket && socket.readyState === WebSocket.OPEN) socket.send(JSON.stringify(obj));
			else if (onConnection) onConnection("Not connected", true);
		},
		listen(fn) { handlers.push(fn); },
	};
	function open() {
		socket = new WebSocket(new URL("ws", window.location.href).href.replace(/^http/, "ws"));
		socket.addEventListener("open", () => {
			socket.send(JSON.stringify({ sub: ["status", ...topics] }));
			for (const fn of handlers) fn({ t: "open" });
			if (onConnection) onConnection("Connected", false);
		});
		socket.addEventListener("message", (event) => {
			let msg;
			try { msg = JSON.parse(event.data); } catch (e) { return; }
			for (const fn of handlers) if (fn(msg)) return;
			onMessage(msg);
		});
		socket.addEventListener("close", () => {
			if (onConnection) onConnection("Disconnected, retrying...", true);
			setTimeout(open, 1000);
		});
	}
	open();
	return dev;
}

const ANSWER = {
	shown: "Type the code the OLED shows.",
	wrong: "Wrong code: try again.",
	expired: "That code is no longer valid: ask again.",
	released: "You released control.",
	busy: "Someone else has control.",
	denied: "Not allowed.",
};

function getToken() { try { return sessionStorage.getItem("sensortestAccess") || ""; } catch (e) { return ""; } }
function setToken(t) {
	try { if (t) sessionStorage.setItem("sensortestAccess", t); else sessionStorage.removeItem("sensortestAccess"); } catch (e) {}
}

// The bar that asks for control. onChange(mine) is told whether this page may change things now.
export function controlBar(container, dev, onChange) {
	container.innerHTML = `
		<div class="control-row">
			<b class="control-state">Watching</b>
			<button class="btn control-ask" type="button">Ask for control</button>
			<input class="form-input control-code" inputmode="numeric" autocomplete="one-time-code" maxlength="8" placeholder="code" hidden>
			<button class="btn control-send" type="button" hidden>OK</button>
			<button class="btn control-release" type="button" hidden>Release</button>
		</div>
		<div class="status control-msg"></div>`;
	const $ = (c) => container.querySelector(c);
	let access = "none", codeSeconds = 0, asked = false, note = "", had = false;

	function show() {
		const mine = access === "you";
		if (had && !mine) { note = access === "other" ? "Someone else took control." : "Control ended (released, or 10 minutes unused)."; setToken(""); }
		had = mine;
		if (!codeSeconds) asked = false;
		$(".control-state").textContent = mine ? "You have control" : access === "other" ? "Someone else has control" : "Watching";
		$(".control-ask").hidden = mine;
		$(".control-ask").textContent = codeSeconds ? "New code" : "Ask for control";
		$(".control-code").hidden = $(".control-send").hidden = mine || !(codeSeconds || asked);
		$(".control-release").hidden = !mine;
		$(".control-msg").textContent = note || (mine
			? "You can change things. Control ends when you release it, close the page, or after 10 minutes unused."
			: codeSeconds ? `A code is on the OLED for ${codeSeconds} s more.`
			: "Everyone can watch; one person at a time can change things. Ask for control and type the code the OLED shows.");
		container.classList.toggle("mine", mine);
		if (onChange) onChange(mine);
	}

	dev.listen((msg) => {
		if (msg.t === "open") {
			const token = getToken();
			if (token) dev.send({ access: "token", token });
			return false;
		}
		if (msg.t === "status") {
			if (msg.access !== access || msg.code !== codeSeconds) { access = msg.access; codeSeconds = msg.code; show(); }
			return false;           // (the page may want the status too)
		}
		if (msg.access) {
			if (msg.access === "granted") { setToken(msg.token); note = ""; $(".control-code").value = ""; access = "you"; }
			else if (msg.access === "wait") note = `Wait ${msg.for} s before trying again.`;
			else { note = ANSWER[msg.access] || ""; if (msg.access === "expired" || msg.access === "released") setToken(""); }
			if (msg.access === "shown") { asked = true; setTimeout(() => $(".control-code").focus(), 0); }
			show();
			return true;
		}
		if (msg.need) { note = "You don't have control (any more): ask for it again."; access = access === "you" ? "none" : access; show(); return true; }
		return false;
	});

	$(".control-ask").addEventListener("click", () => { note = ""; dev.send({ access: "request" }); });
	const sendCode = () => {
		const code = $(".control-code").value.replace(/\D/g, "");
		if (code.length >= 2) dev.send({ access: "code", code });
	};
	$(".control-send").addEventListener("click", sendCode);
	$(".control-code").addEventListener("keydown", (e) => { if (e.key === "Enter") sendCode(); });
	$(".control-release").addEventListener("click", () => dev.send({ access: "release" }));
	show();
}
