import { useEffect, useMemo, useRef, useState } from "react";
import { DungeonGrid } from "./DungeonGrid";
import { fetchRunRaw } from "./liveApi";
import { parseRunJsonl } from "./parseRun";
import { playToolSound, unlockAudio } from "./sounds";
import type { ReplayFrame } from "./types";

const SOUND_STORAGE_KEY = "dungeonAgents-viz-sound";

function readSoundPreference(): boolean {
  try {
    return localStorage.getItem(SOUND_STORAGE_KEY) !== "0";
  } catch {
    return true;
  }
}

const SPEED_OPTIONS = [150, 300, 600, 1000];
const LIVE_POLL_MS = 350;
const STABLE_POLLS_FOR_IDLE = 12;

function readLiveParams(): { runId: string | null; live: boolean } {
  const p = new URLSearchParams(window.location.search);
  const run = p.get("run");
  const live = p.get("live") === "1";
  return { runId: run && run.length > 0 ? run : null, live };
}

function disconnectLiveFromUrl(): void {
  window.history.replaceState({}, "", window.location.pathname);
}

export default function App(): JSX.Element {
  const [liveParams, setLiveParams] = useState(readLiveParams);
  const { runId, live: liveFromUrl } = liveParams;
  const liveActive = Boolean(liveFromUrl && runId);

  const [frames, setFrames] = useState<ReplayFrame[]>([]);
  const [frameIndex, setFrameIndex] = useState(0);
  const [isPlaying, setIsPlaying] = useState(false);
  const [speedMs, setSpeedMs] = useState(300);
  const [status, setStatus] = useState("Pick a run .jsonl file, load the demo, or open a live run URL from the CLI.");
  const [followLive, setFollowLive] = useState(true);
  const [soundOn, setSoundOn] = useState(readSoundPreference);

  const followLiveRef = useRef(followLive);
  const prevSoundKeyRef = useRef<string | null>(null);
  const frameCountRef = useRef(0);
  const stableCountRef = useRef(0);
  const lastTextRef = useRef("");

  useEffect(() => {
    followLiveRef.current = followLive;
  }, [followLive]);

  useEffect(() => {
    frameCountRef.current = frames.length;
  }, [frames.length]);

  const frame = frames[frameIndex];
  const dataRunId = frames[0]?.worldState.run_id ?? "";

  useEffect(() => {
    try {
      localStorage.setItem(SOUND_STORAGE_KEY, soundOn ? "1" : "0");
    } catch {
      /* ignore */
    }
  }, [soundOn]);

  useEffect(() => {
    prevSoundKeyRef.current = null;
  }, [dataRunId]);

  useEffect(() => {
    if (frames.length === 0 || !frame) {
      return;
    }
    const k = `${frameIndex}|${frame.turn}|${frame.agentId}|${frame.toolName}`;
    const prev = prevSoundKeyRef.current;
    if (prev === k) {
      return;
    }
    prevSoundKeyRef.current = k;
    if (prev === null || !soundOn) {
      return;
    }
    playToolSound(frame.toolName);
  }, [frame, frameIndex, frames.length, soundOn, dataRunId]);

  useEffect(() => {
    if (!isPlaying || frames.length === 0) {
      return;
    }

    const timer = window.setInterval(() => {
      setFrameIndex((current) => {
        if (current >= frames.length - 1) {
          window.clearInterval(timer);
          setIsPlaying(false);
          return current;
        }
        return current + 1;
      });
    }, speedMs);

    return () => window.clearInterval(timer);
  }, [isPlaying, speedMs, frames.length]);

  const progressText = useMemo(() => {
    if (!frame) return "No frame loaded";
    return `Frame ${frameIndex + 1}/${frames.length} · Turn ${frame.turn} · ${frame.agentId} · ${frame.toolName}`;
  }, [frame, frameIndex, frames.length]);

  function disconnectLive(): void {
    disconnectLiveFromUrl();
    setLiveParams({ runId: null, live: false });
  }

  useEffect(() => {
    if (!liveActive || !runId) {
      return;
    }

    let cancelled = false;
    stableCountRef.current = 0;
    lastTextRef.current = "";

    const tick = async (): Promise<void> => {
      try {
        const data = await fetchRunRaw(runId);
        if (cancelled) return;

        if (!data.exists) {
          setStatus("Live: waiting for log file (simulation is starting)…");
          return;
        }

        if (data.text === lastTextRef.current) {
          stableCountRef.current += 1;
          if (
            stableCountRef.current >= STABLE_POLLS_FOR_IDLE &&
            frameCountRef.current > 0
          ) {
            setStatus(
              `Live: ${frameCountRef.current} outcome frames — log unchanged (simulation likely finished). You can scrub history or load another run.`,
            );
          }
          return;
        }

        stableCountRef.current = 0;
        lastTextRef.current = data.text;
        const { frames: next, ignoredLines } = parseRunJsonl(data.text);
        setFrames(next);
        const ig = ignoredLines > 0 ? ` (${ignoredLines} bad lines skipped)` : "";
        setStatus(`Live: ${next.length} outcome frames (streaming)${ig}`);

        if (followLiveRef.current && next.length > 0) {
          setFrameIndex(next.length - 1);
        }
      } catch (e) {
        if (!cancelled) {
          setStatus(
            `Live poll failed: ${e instanceof Error ? e.message : String(e)}. Start the visualizer with npm run dev, run the simulation with --live-viz, and keep the default API port 8765 (or set VITE_LIVE_API_BASE_URL).`,
          );
        }
      }
    };

    void tick();
    const id = window.setInterval(() => void tick(), LIVE_POLL_MS);
    return () => {
      cancelled = true;
      window.clearInterval(id);
    };
  }, [liveActive, runId]);

  async function handleFileChange(file: File | null): Promise<void> {
    if (!file) return;

    disconnectLive();
    setFollowLive(false);

    const raw = await file.text();
    const { frames: parsedFrames, ignoredLines } = parseRunJsonl(raw);
    if (parsedFrames.length === 0) {
      setFrames([]);
      setFrameIndex(0);
      setIsPlaying(false);
      setStatus("No outcome frames were found in that file.");
      return;
    }

    setFrames(parsedFrames);
    setFrameIndex(0);
    setIsPlaying(false);

    const ignoredMessage =
      ignoredLines > 0 ? ` Ignored ${ignoredLines} malformed line(s).` : "";
    setStatus(`Loaded ${parsedFrames.length} outcome frames from file.${ignoredMessage}`);
  }

  async function handleLoadDemo(): Promise<void> {
    disconnectLive();
    setFollowLive(false);

    const url = `${import.meta.env.BASE_URL}sample_visualizer_demo.jsonl`;
    let raw: string;
    try {
      const res = await fetch(url);
      if (!res.ok) {
        setStatus(`Demo fetch failed (${res.status}).`);
        return;
      }
      raw = await res.text();
    } catch {
      setStatus("Demo fetch failed (network).");
      return;
    }

    const { frames: parsedFrames, ignoredLines } = parseRunJsonl(raw);
    if (parsedFrames.length === 0) {
      setFrames([]);
      setFrameIndex(0);
      setStatus("Demo file had no outcome frames.");
      return;
    }

    setFrames(parsedFrames);
    setFrameIndex(0);
    setIsPlaying(false);
    const ig = ignoredLines > 0 ? ` Ignored ${ignoredLines} bad line(s).` : "";
    setStatus(`Loaded bundled demo (${parsedFrames.length} frames).${ig}`);
  }

  function step(delta: number): void {
    setFrameIndex((current) => {
      if (frames.length === 0) return current;
      return Math.max(0, Math.min(current + delta, frames.length - 1));
    });
  }

  function withAudio(fn: () => void): void {
    void unlockAudio();
    fn();
  }

  return (
    <main className="app-shell">
      <header className="top-bar">
        <div>
          <h1>Dungeon Replay Mini-Window</h1>
          <p className="subtitle">{status}</p>
          {liveActive && (
            <p className="live-banner">
              <strong>Live run</strong> · Run ID <code>{runId}</code> · polling{" "}
              <code>/api/runs/…/raw</code>
            </p>
          )}
        </div>
        <div className="header-actions">
          <button
            type="button"
            className="secondary-btn"
            onClick={() => {
              void unlockAudio();
              void handleLoadDemo();
            }}
          >
            Load bundled demo
          </button>
          <label className="file-input-label">
            <span>Load .jsonl run</span>
            <input
              type="file"
              accept=".jsonl,application/json,text/plain"
              onChange={(event) => {
                void unlockAudio();
                void handleFileChange(event.target.files?.[0] ?? null);
              }}
            />
          </label>
          {liveActive && (
            <button type="button" className="secondary-btn" onClick={disconnectLive}>
              Exit live mode
            </button>
          )}
        </div>
      </header>

      {liveActive && (
        <section className="live-controls">
          <label className="follow-checkbox">
            <input
              type="checkbox"
              checked={followLive}
              onChange={(e) => {
                void unlockAudio();
                setFollowLive(e.target.checked);
              }}
            />
            Follow latest frame (uncheck to scrub while the run is in progress)
          </label>
        </section>
      )}

      <section className="controls-panel">
        <div className="transport">
          <button
            type="button"
            onClick={() => withAudio(() => step(-1))}
            disabled={frameIndex <= 0}
          >
            Prev
          </button>
          <button
            type="button"
            onClick={() => withAudio(() => setIsPlaying((current) => !current))}
            disabled={frames.length === 0}
          >
            {isPlaying ? "Pause" : "Play"}
          </button>
          <button
            type="button"
            onClick={() => withAudio(() => step(1))}
            disabled={frames.length === 0 || frameIndex >= frames.length - 1}
          >
            Next
          </button>
        </div>

        <label className="sound-toggle">
          <input
            type="checkbox"
            checked={soundOn}
            onChange={(e) => {
              void unlockAudio();
              setSoundOn(e.target.checked);
            }}
          />
          Sound effects
        </label>

        <label className="speed-control">
          Speed
          <select
            value={speedMs}
            onChange={(event) => setSpeedMs(Number(event.target.value))}
            disabled={frames.length === 0}
          >
            {SPEED_OPTIONS.map((speed) => (
              <option key={speed} value={speed}>
                {speed} ms
              </option>
            ))}
          </select>
        </label>

        <input
          type="range"
          min={0}
          max={Math.max(frames.length - 1, 0)}
          value={frameIndex}
          disabled={frames.length === 0}
          onPointerDown={() => void unlockAudio()}
          onChange={(event) => setFrameIndex(Number(event.target.value))}
        />
        <p className="progress-text">{progressText}</p>
      </section>

      {frame && (
        <>
          <DungeonGrid frame={frame} />
          <section className="meta-panel">
            <p>
              <strong>Run:</strong> {frame.worldState.run_id}
            </p>
            <p>
              <strong>Door unlocked:</strong>{" "}
              {frame.worldState.door_unlocked ? "yes" : "no"}
            </p>
            <p>
              <strong>Key held by:</strong> {frame.worldState.key_held_by ?? "nobody"}
            </p>
            <p>
              <strong>Outcome:</strong> {frame.resultDescription}
            </p>
          </section>
        </>
      )}
    </main>
  );
}
