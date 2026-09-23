let audio = null;

export function primeFeedback() {
  try {
    const Context = window.AudioContext || window.webkitAudioContext;
    if (!Context) return;
    audio = audio || new Context();
    if (audio.state === "suspended") audio.resume().catch(() => {});
  } catch {
    audio = null;
  }
}

export function signalSuccess() {
  if (typeof navigator.vibrate === "function") navigator.vibrate(80);
  if (!audio) return;
  try {
    const tone = audio.createOscillator();
    const gain = audio.createGain();
    tone.frequency.value = 1320;
    gain.gain.value = 0.1;
    tone.connect(gain).connect(audio.destination);
    tone.start();
    tone.stop(audio.currentTime + 0.12);
  } catch {
    audio = null;
  }
}
