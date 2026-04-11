/** Base URL for the live-viz Python server. Empty = same origin (Vite proxies /api). */
export function getLiveApiBase(): string {
  const fromEnv = import.meta.env.VITE_LIVE_API_BASE_URL as string | undefined;
  return (fromEnv ?? "").replace(/\/$/, "");
}

export async function fetchRunRaw(runId: string): Promise<{
  exists: boolean;
  text: string;
}> {
  const base = getLiveApiBase();
  const url = `${base}/api/runs/${encodeURIComponent(runId)}/raw`;
  const res = await fetch(url);
  if (!res.ok) {
    throw new Error(`Live API ${res.status}: ${await res.text()}`);
  }
  return res.json() as Promise<{ exists: boolean; text: string }>;
}
