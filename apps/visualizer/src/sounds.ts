/** Lightweight Web Audio cues for dungeon replay (no external assets). */

let ctx: AudioContext | null = null;
let lastPlayTime = 0;
const MIN_INTERVAL_MS = 85;

function getCtx(): AudioContext | null {
  if (typeof window === "undefined") return null;
  if (!ctx) {
    const Ctx =
      window.AudioContext ??
      (window as unknown as { webkitAudioContext?: typeof AudioContext }).webkitAudioContext;
    if (!Ctx) return null;
    ctx = new Ctx();
  }
  return ctx;
}

/** Call from a user gesture so the browser allows playback. */
export async function unlockAudio(): Promise<void> {
  const c = getCtx();
  if (c?.state === "suspended") {
    await c.resume();
  }
}

function now(): number {
  const c = getCtx();
  return c?.currentTime ?? 0;
}

function beep(
  freq: number,
  duration: number,
  type: OscillatorType = "sine",
  gain = 0.12,
  freqEnd?: number,
): void {
  const c = getCtx();
  if (!c || c.state !== "running") return;

  const t = now();
  const osc = c.createOscillator();
  const g = c.createGain();
  osc.type = type;
  osc.frequency.setValueAtTime(freq, t);
  if (freqEnd !== undefined) {
    osc.frequency.exponentialRampToValueAtTime(Math.max(40, freqEnd), t + duration);
  }
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(gain, t + 0.012);
  g.gain.exponentialRampToValueAtTime(0.0001, t + duration);
  osc.connect(g);
  g.connect(c.destination);
  osc.start(t);
  osc.stop(t + duration + 0.02);
}

function noiseBurst(duration: number, gain = 0.06): void {
  const c = getCtx();
  if (!c || c.state !== "running") return;

  const t = now();
  const bufferSize = Math.max(1, Math.floor(c.sampleRate * duration));
  const buffer = c.createBuffer(1, bufferSize, c.sampleRate);
  const data = buffer.getChannelData(0);
  for (let i = 0; i < bufferSize; i++) {
    data[i] = (Math.random() * 2 - 1) * (1 - i / bufferSize);
  }
  const src = c.createBufferSource();
  src.buffer = buffer;
  const g = c.createGain();
  g.gain.setValueAtTime(0.0001, t);
  g.gain.exponentialRampToValueAtTime(gain, t + 0.005);
  g.gain.exponentialRampToValueAtTime(0.0001, t + duration);
  src.connect(g);
  g.connect(c.destination);
  src.start(t);
}

function throttle(): boolean {
  if (typeof performance === "undefined") return false;
  const wall = performance.now();
  if (wall - lastPlayTime < MIN_INTERVAL_MS) return true;
  lastPlayTime = wall;
  return false;
}

export function playToolSound(toolName: string): void {
  if (throttle()) return;

  switch (toolName) {
    case "move":
      noiseBurst(0.038, 0.05);
      beep(165, 0.07, "triangle", 0.07, 95);
      break;
    case "observe":
      beep(900, 0.065, "sine", 0.085, 720);
      break;
    case "interact":
      beep(240, 0.035, "square", 0.055);
      window.setTimeout(() => {
        beep(360, 0.045, "square", 0.045);
      }, 55);
      break;
    case "communicate":
      beep(523, 0.075, "sine", 0.095);
      window.setTimeout(() => {
        beep(659, 0.09, "sine", 0.08);
      }, 75);
      break;
    default:
      beep(440, 0.055, "sine", 0.065);
  }
}
