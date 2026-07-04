// @ts-nocheck
import * as THREE from "https://esm.sh/three@0.166.1";
import { OrbitControls } from "https://esm.sh/three@0.166.1/examples/jsm/controls/OrbitControls.js";

const statusElement = document.getElementById("tof3dStatus");
const canvasWrap = document.getElementById("tof3dCanvasWrap");
const canvas = document.getElementById("tof3dCanvas");
const hideInvalidDistanceInput = document.getElementById("tof3dHideInvalidDistance") || document.getElementById("tofHideInvalidDistance");
const useOrthographicInput = document.getElementById("tof3dUseOrthographic");
const viewEnabledHeader = document.getElementById("tof3dViewHeader");
const sectionBody = document.getElementById("tof3dSectionBody");

if (!statusElement || !canvasWrap || !canvas || !hideInvalidDistanceInput || !useOrthographicInput || !viewEnabledHeader || !sectionBody) {
	throw new Error("ToF 3D page elements are missing");
}

const fovDeg = 60;
const defaultGridSide = 4;
const minDistanceMeters = 0.03;
const maxDistanceMeters = 3.5;
const fovGuideDistanceMeters = 0.2;
const storageKeyHideInvalidDistance = "tofSensor.hideInvalidDistance";
const storageKeyUseOrthographic = "tofSensor3d.useOrthographic";
const storageKeyViewEnabled = "tofSensor.view3dEnabled";

// World frame used for ToF visualization:
// X = right, Y = back, Z = up.
// Three.js frame is converted with: (x, y, z)_world -> (x, z, -y)_three.
function worldToThree(x, y, z) {
	return new THREE.Vector3(x, z, -y);
}

function worldDirToThree(x, y, z) {
	return new THREE.Vector3(x, z, -y).normalize();
}

let viewEnabled = true;

const scene = new THREE.Scene();
scene.background = new THREE.Color(0xf7f8fc);

const renderer = new THREE.WebGLRenderer({ canvas, antialias: false });
renderer.setPixelRatio(window.devicePixelRatio || 1);
renderer.shadowMap.enabled = false;

const perspectiveCamera = new THREE.PerspectiveCamera(48, 1, 0.01, 30);
perspectiveCamera.position.set(1.1, 1.2, 1.1);

const orthographicCamera = new THREE.OrthographicCamera(-1, 1, 1, -1, 0.01, 30);
orthographicCamera.position.copy(perspectiveCamera.position);

let activeCamera = perspectiveCamera;
let controls = null;

function createControls(camera, target) {
	const nextControls = new OrbitControls(camera, renderer.domElement);
	nextControls.enableDamping = true;
	nextControls.target.copy(target);
	nextControls.minDistance = 0.25;
	nextControls.maxDistance = 8;
	nextControls.update();
	return nextControls;
}

controls = createControls(activeCamera, new THREE.Vector3(0, 0.45, 0));

const ambientLight = new THREE.AmbientLight(0xffffff, 0.7);
scene.add(ambientLight);

const keyLight = new THREE.DirectionalLight(0xffffff, 0.9);
keyLight.position.set(2.5, 4.5, 2.5);
keyLight.castShadow = false;
scene.add(keyLight);

// 100 mm grid: 0.1 m spacing in scene units.
const floorGridSizeMeters = 4;
const floorGridSpacingMeters = 0.1;
const floorGrid = new THREE.GridHelper(
	floorGridSizeMeters,
	Math.round(floorGridSizeMeters / floorGridSpacingMeters),
	0xcbd5e1,
	0xcbd5e1
);
floorGrid.position.y = 0.001;
scene.add(floorGrid);

const sensorBody = new THREE.Mesh(
	new THREE.BoxGeometry(0.08, 0.03, 0.08),
	new THREE.MeshStandardMaterial({ color: 0x374151, roughness: 0.5, metalness: 0.2 })
);
sensorBody.position.set(0, 0.015, 0);
sensorBody.castShadow = false;
sensorBody.receiveShadow = false;
scene.add(sensorBody);

const sensorTop = new THREE.Mesh(
	new THREE.CylinderGeometry(0.012, 0.012, 0.01, 20),
	new THREE.MeshStandardMaterial({ color: 0x0ea5e9, roughness: 0.35, metalness: 0.15 })
);
sensorTop.position.set(0, 0.035, 0);
sensorTop.castShadow = false;
scene.add(sensorTop);

const axisLength = 0.28;
const axisHeadLength = 0.04;
const axisHeadWidth = 0.022;
const axisOrigin = worldToThree(0, 0, 0.002);
scene.add(new THREE.ArrowHelper(worldDirToThree(1, 0, 0), axisOrigin, axisLength, 0xff0000, axisHeadLength, axisHeadWidth));
scene.add(new THREE.ArrowHelper(worldDirToThree(0, 1, 0), axisOrigin, axisLength, 0x22c55e, axisHeadLength, axisHeadWidth));
scene.add(new THREE.ArrowHelper(worldDirToThree(0, 0, 1), axisOrigin, axisLength, 0x2563eb, axisHeadLength, axisHeadWidth));

const fovHalfRad = THREE.MathUtils.degToRad(fovDeg / 2);
const fovGuideHalfExtent = Math.tan(fovHalfRad) * fovGuideDistanceMeters;
const fovGuideCornersWorld = [
	[-fovGuideHalfExtent, -fovGuideHalfExtent, fovGuideDistanceMeters],
	[ fovGuideHalfExtent, -fovGuideHalfExtent, fovGuideDistanceMeters],
	[ fovGuideHalfExtent,  fovGuideHalfExtent, fovGuideDistanceMeters],
	[-fovGuideHalfExtent,  fovGuideHalfExtent, fovGuideDistanceMeters]
];
const fovGuideVertices = [];
const fovOrigin = worldToThree(0, 0, 0);
for (let i = 0; i < fovGuideCornersWorld.length; i += 1) {
	const corner = fovGuideCornersWorld[i];
	const cornerThree = worldToThree(corner[0], corner[1], corner[2]);
	fovGuideVertices.push(fovOrigin.x, fovOrigin.y, fovOrigin.z);
	fovGuideVertices.push(cornerThree.x, cornerThree.y, cornerThree.z);
}
const fovGuideGeometry = new THREE.BufferGeometry();
fovGuideGeometry.setAttribute("position", new THREE.Float32BufferAttribute(fovGuideVertices, 3));
const fovGuideMaterial = new THREE.LineBasicMaterial({ color: 0x64748b, transparent: true, opacity: 0.9 });
const fovGuideLines = new THREE.LineSegments(fovGuideGeometry, fovGuideMaterial);
scene.add(fovGuideLines);

const fovGroup = new THREE.Group();
scene.add(fovGroup);

const zoneMeshByIndex = new Map();

function shouldHideInvalidDistance() {
	return Boolean(hideInvalidDistanceInput.checked);
}

function readStoredHideInvalidDistance() {
	try {
		return localStorage.getItem(storageKeyHideInvalidDistance) === "true";
	} catch (error) {
		return false;
	}
}

function storeHideInvalidDistance(hideInvalidDistance) {
	try {
		localStorage.setItem(storageKeyHideInvalidDistance, hideInvalidDistance ? "true" : "false");
	} catch (error) {
		// Ignore storage failures.
	}
}

function zoneIsValid(zone) {
	return Boolean(zone && zone.targetCount > 0 && zone.valid);
}

function applyHideInvalidDistanceSetting() {
	storeHideInvalidDistance(shouldHideInvalidDistance());
}

function setStatus(text, isError) {
	statusElement.textContent = text;
	statusElement.classList.toggle("error", Boolean(isError));
}

function readStoredViewEnabled() {
	try {
		const stored = localStorage.getItem(storageKeyViewEnabled);
		if (stored === null) {
			return true;
		}
		return stored === "true";
	} catch (error) {
		return true;
	}
}

function storeViewEnabled(enabled) {
	try {
		localStorage.setItem(storageKeyViewEnabled, enabled ? "true" : "false");
	} catch (error) {
		// Ignore storage failures.
	}
}

function setViewEnabled(enabled) {
	viewEnabled = Boolean(enabled);
	viewEnabledHeader.setAttribute("aria-expanded", viewEnabled ? "true" : "false");
	sectionBody.classList.toggle("tof-section-collapsed", !viewEnabled);
	if (!viewEnabled) {
		clearZones();
	}
	setStatus(viewEnabled ? "Connected (shared stream)" : "Connected (3D view disabled)", false);
	storeViewEnabled(viewEnabled);
}

function resizeRenderer() {
	const width = Math.max(10, canvasWrap.clientWidth);
	const height = Math.max(10, canvasWrap.clientHeight);
	renderer.setSize(width, height, false);

	const aspect = width / height;
	perspectiveCamera.aspect = aspect;
	perspectiveCamera.updateProjectionMatrix();

	const orthoHalfHeight = 1.0;
	orthographicCamera.top = orthoHalfHeight;
	orthographicCamera.bottom = -orthoHalfHeight;
	orthographicCamera.left = -orthoHalfHeight * aspect;
	orthographicCamera.right = orthoHalfHeight * aspect;
	orthographicCamera.updateProjectionMatrix();
}

function readStoredUseOrthographic() {
	try {
		return localStorage.getItem(storageKeyUseOrthographic) === "true";
	} catch (error) {
		return false;
	}
}

function storeUseOrthographic(useOrthographic) {
	try {
		localStorage.setItem(storageKeyUseOrthographic, useOrthographic ? "true" : "false");
	} catch (error) {
		// Ignore storage failures.
	}
}

function setProjectionMode(useOrthographic) {
	const currentTarget = controls ? controls.target.clone() : new THREE.Vector3(0, 0.45, 0);
	const currentPosition = activeCamera.position.clone();

	activeCamera = useOrthographic ? orthographicCamera : perspectiveCamera;
	activeCamera.position.copy(currentPosition);

	if (controls) {
		controls.dispose();
	}
	controls = createControls(activeCamera, currentTarget);

	useOrthographicInput.checked = useOrthographic;
	storeUseOrthographic(useOrthographic);
}

function clearZones() {
	for (const mesh of zoneMeshByIndex.values()) {
		fovGroup.remove(mesh);
		mesh.geometry.dispose();
		mesh.material.dispose();
	}
	zoneMeshByIndex.clear();
}

function normalizedCellBounds(row, col, gridSide) {
	const left = col / gridSide;
	const right = (col + 1) / gridSide;
	const back = 1 - row / gridSide;
	const front = 1 - (row + 1) / gridSide;

	return {
		xMin: left * 2 - 1,
		xMax: right * 2 - 1,
		yMin: front * 2 - 1,
		yMax: back * 2 - 1
	};
}

function zoneColor(valid) {
	if (valid) {
		return 0x2a9d8f;
	}
	return 0xd1495b;
}

function createZoneMesh(zone, gridSide) {
	const distanceMm = Number(zone.distanceMm);
	if (!Number.isFinite(distanceMm) || distanceMm <= 0) {
		return null;
	}

	const distanceMeters = Math.min(maxDistanceMeters, Math.max(minDistanceMeters, distanceMm / 1000));
	const angleScale = Math.tan(fovHalfRad);
	const bounds = normalizedCellBounds(zone.row, zone.col, gridSide);

	const x0 = bounds.xMin * angleScale * distanceMeters;
	const x1 = bounds.xMax * angleScale * distanceMeters;
	const y0 = bounds.yMin * angleScale * distanceMeters;
	const y1 = bounds.yMax * angleScale * distanceMeters;
	const z = distanceMeters;

	const p00 = worldToThree(x0, y0, z);
	const p10 = worldToThree(x1, y0, z);
	const p11 = worldToThree(x1, y1, z);
	const p01 = worldToThree(x0, y1, z);

	const geometry = new THREE.BufferGeometry();
	const vertices = new Float32Array([
		p00.x, p00.y, p00.z,
		p10.x, p10.y, p10.z,
		p11.x, p11.y, p11.z,
		p01.x, p01.y, p01.z
	]);
	const indices = [0, 1, 2, 0, 2, 3];

	geometry.setAttribute("position", new THREE.BufferAttribute(vertices, 3));
	geometry.setIndex(indices);
	geometry.computeVertexNormals();

	const material = new THREE.MeshBasicMaterial({
		color: zoneColor(zoneIsValid(zone)),
		side: THREE.FrontSide
	});

	const mesh = new THREE.Mesh(geometry, material);
	mesh.castShadow = false;
	mesh.receiveShadow = false;
	return mesh;
}

function updateZones(payload) {
	clearZones();

	const zones = Array.isArray(payload.zones) ? payload.zones : [];
	const gridSide = Number(payload.gridSide) > 0 ? Number(payload.gridSide) : defaultGridSide;

	for (let i = 0; i < zones.length; i += 1) {
		const zone = zones[i];
		if (!zone || zone.targetCount <= 0) {
			continue;
		}

		if (shouldHideInvalidDistance() && !zoneIsValid(zone)) {
			continue;
		}

		const mesh = createZoneMesh(zone, gridSide);
		if (!mesh) {
			continue;
		}

		fovGroup.add(mesh);
		zoneMeshByIndex.set(zone.index, mesh);
	}
}

hideInvalidDistanceInput.checked = readStoredHideInvalidDistance();
hideInvalidDistanceInput.addEventListener("change", function () {
	applyHideInvalidDistanceSetting();
});
applyHideInvalidDistanceSetting();

window.addEventListener("tofSensorData", function (event) {
	try {
		if (!viewEnabled || !event || !event.detail) {
			return;
		}

		// Check if map is paused (respect pause button from 2D view)
		if (window.tofMapPaused && window.tofMapPaused()) {
			return;
		}

		updateZones(event.detail);
	} catch (error) {
		setStatus("Invalid data received", true);
	}
});

function animate() {
	const nowMs = performance.now();
	if (!animate.lastFrameMs) {
		animate.lastFrameMs = nowMs;
	}

	if (viewEnabled && nowMs - animate.lastFrameMs >= 33) {
		animate.lastFrameMs = nowMs;
		controls.update();
		renderer.render(scene, activeCamera);
	}
	requestAnimationFrame(animate);
}

animate.lastFrameMs = 0;

window.addEventListener("resize", resizeRenderer);
useOrthographicInput.addEventListener("change", function () {
	setProjectionMode(Boolean(useOrthographicInput.checked));
});
viewEnabledHeader.addEventListener("click", function () {
	setViewEnabled(!viewEnabled);
});
resizeRenderer();
setProjectionMode(readStoredUseOrthographic());
setViewEnabled(readStoredViewEnabled());
animate();