import logger from "../../lib/logger";

export function classifyCameraError(err) {
  const msg = String(err?.message || err || "");
  const name = String(err?.name || "");
  if (typeof window !== "undefined" && window.isSecureContext === false) {
    return {
      code: "insecure",
      message: "Camera access requires HTTPS or localhost. Use photo upload or a USB scanner.",
    };
  }
  if (name === "NotAllowedError" || name === "PermissionDeniedError" || /permission|denied|allowed/i.test(msg)) {
    return {
      code: "permission_denied",
      message: "Camera permission is off. Enable camera for this site in the browser settings, then tap Retry. USB or photo QR still works.",
    };
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError" || /not found|no camera/i.test(msg)) {
    return {
      code: "not_found",
      message: "No camera found on this device. Use photo upload or USB scanner instead.",
    };
  }
  if (name === "NotReadableError" || name === "TrackStartError" || /in use|busy|started/i.test(msg)) {
    return {
      code: "busy",
      message: "Camera is currently busy or in use by another app. Close other apps and retry.",
    };
  }
  return { code: "unknown", message: "Unable to start camera. Use photo upload or USB scanner instead." };
}

export function cameraErrorMessage(err) {
  return classifyCameraError(err).message;
}

export async function listVideoInputs() {
  if (!navigator.mediaDevices?.enumerateDevices) return [];
  const devices = await navigator.mediaDevices.enumerateDevices();
  return devices.filter((d) => d.kind === "videoinput");
}

const FOCUS = { focusMode: { ideal: "continuous" } };
const FULL_HD = { width: { ideal: 1920 }, height: { ideal: 1080 } };
const HD = { width: { ideal: 1280 }, height: { ideal: 720 } };

export function buildCameraConstraintAttempts(deviceId) {
  const attempts = [];
  if (deviceId) {
    const device = { deviceId: { exact: deviceId } };
    attempts.push({ video: { ...device, ...FULL_HD, ...FOCUS } });
    attempts.push({ video: { ...device, ...HD } });
  }
  const rear = { facingMode: { ideal: "environment" } };
  attempts.push({ video: { ...rear, ...FULL_HD, ...FOCUS } });
  attempts.push({ video: { ...rear, ...HD } });
  attempts.push({ video: { facingMode: "environment" } });
  attempts.push({ video: { facingMode: "user" } });
  attempts.push({ video: true });
  return attempts;
}

export async function acquireCameraStream(deviceId) {
  const attempts = buildCameraConstraintAttempts(deviceId);
  let stream = null;
  let lastErr = null;
  for (const constraints of attempts) {
    try {
      stream = await navigator.mediaDevices.getUserMedia({ audio: false, ...constraints });
      break;
    } catch (e) {
      lastErr = e;
      if (classifyCameraError(e).code === "permission_denied") break;
    }
  }
  if (!stream) {
    throw lastErr || new Error("Unable to start camera");
  }
  return stream;
}

export async function attachStreamToVideo(video, stream) {
  if (!video) throw new Error("Unable to start camera");
  video.srcObject = stream;
  try {
    await video.play();
  } catch (e) {
    logger.warn("Error playing camera:", e);
  }
  if (!video.videoWidth) {
    await new Promise((resolve) => {
      let timer = null;
      const done = () => {
        clearTimeout(timer);
        video.removeEventListener("loadedmetadata", done);
        resolve();
      };
      video.addEventListener("loadedmetadata", done);
      timer = setTimeout(done, 800);
    });
  }
}

export function checkTorchCapability(stream) {
  const track = stream?.getVideoTracks?.()[0];
  if (!track) return false;
  try {
    const caps = track.getCapabilities?.() || {};
    return Boolean(caps.torch);
  } catch (e) {
    logger.warn("Failed to check track capabilities for torch:", e);
    return false;
  }
}

export async function applyTorch(stream, nextTorch) {
  const track = stream?.getVideoTracks?.()[0];
  if (!track) return;
  try {
    await track.applyConstraints({ advanced: [{ torch: nextTorch }] });
  } catch (e) {
    logger.warn("Failed to toggle torch constraints:", e);
  }
}

function capabilities(stream) {
  const track = stream?.getVideoTracks?.()[0];
  try {
    return { track, caps: track?.getCapabilities?.() || {} };
  } catch {
    return { track, caps: {} };
  }
}

export function zoomRange(stream) {
  const { caps } = capabilities(stream);
  const zoom = caps.zoom;
  if (!zoom || !(zoom.max > zoom.min)) return null;
  const step = zoom.step > 0 ? zoom.step : 0.1;
  const snap = (value) => Math.min(zoom.max, Math.max(zoom.min, Math.round(value / step) * step));
  return { min: zoom.min, max: zoom.max, near: snap(zoom.min * 2), snap };
}

export async function applyZoom(stream, value) {
  const { track } = capabilities(stream);
  if (!track) return false;
  try {
    await track.applyConstraints({ advanced: [{ zoom: value }] });
    return true;
  } catch (e) {
    logger.warn("Failed to apply zoom:", e);
    return false;
  }
}

export async function focusAt(stream, x, y) {
  const { track, caps } = capabilities(stream);
  const modes = caps.focusMode || [];
  if (!track || !modes.length) return;
  const mode = modes.includes("single-shot") ? "single-shot" : modes.includes("continuous") ? "continuous" : null;
  if (!mode) return;
  try {
    await track.applyConstraints({ advanced: [{ focusMode: mode, pointsOfInterest: [{ x, y }] }] });
    if (mode === "single-shot" && modes.includes("continuous")) {
      setTimeout(() => {
        track.applyConstraints({ advanced: [{ focusMode: "continuous" }] }).catch(() => {});
      }, 1500);
    }
  } catch (e) {
    logger.warn("Failed to focus:", e);
  }
}
