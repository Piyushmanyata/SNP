import logger from "../../lib/logger";

export function cameraErrorMessage(err) {
  const msg = String(err?.message || err || "");
  const name = String(err?.name || "");
  if (typeof window !== "undefined" && window.isSecureContext === false) {
    return "Camera access requires HTTPS or localhost. Please use a secure connection, photo upload, or USB scanner.";
  }
  if (name === "NotAllowedError" || name === "PermissionDeniedError" || /permission|denied|allowed/i.test(msg)) {
    return "Camera permission denied. Please allow camera access in your browser or use photo upload / USB scanner.";
  }
  if (name === "NotFoundError" || name === "DevicesNotFoundError" || /not found|no camera/i.test(msg)) {
    return "No camera found on this device. Use photo upload or USB scanner instead.";
  }
  if (name === "NotReadableError" || name === "TrackStartError" || /in use|busy|started/i.test(msg)) {
    return "Camera is currently busy or in use by another app. Close other apps and retry.";
  }
  return "Unable to start camera. Use photo upload or USB scanner instead.";
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

export function createStillCapture(stream) {
  const track = stream?.getVideoTracks?.()[0];
  if (!track || typeof window === "undefined" || !window.ImageCapture) return null;
  try {
    const capture = new window.ImageCapture(track);
    if (typeof capture.takePhoto !== "function") return null;
    return capture;
  } catch (e) {
    logger.warn("Still capture unavailable on this track:", e);
    return null;
  }
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
