// @ts-nocheck
const channelInput = document.getElementById("servoChannel");
const pulseInput = document.getElementById("servoPulseUs");
const setButton = document.getElementById("setServoButton");
const statusElement = document.getElementById("servoStatus");

if (!channelInput || !pulseInput || !setButton || !statusElement) {
	throw new Error("PWM servo page elements are missing");
}

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

for (let channel = 0; channel <= 15; channel += 1) {
	const option = document.createElement("option");
	option.value = String(channel);
	option.textContent = "Channel " + channel;
	channelInput.appendChild(option);
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
