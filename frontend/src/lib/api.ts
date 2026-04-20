import type { BootstrapPayload, LeaderboardRow } from "./types";

async function get<T>(path: string): Promise<T> {
  const r = await fetch(path, { cache: "no-store" });
  if (!r.ok) throw new Error(`${path}: ${r.status}`);
  return r.json() as Promise<T>;
}

export const api = {
  health: () => get<{ ok: boolean; mode: string; bot_live: boolean }>("/api/health"),
  bootstrap: (instanceId?: number) =>
    get<BootstrapPayload>(
      instanceId != null ? `/api/bootstrap?instance_id=${instanceId}` : "/api/bootstrap",
    ),
  instances: () => get<LeaderboardRow[]>("/api/instances"),
  instanceDetail: (id: number) => get<BootstrapPayload>(`/api/instance/${id}`),
};
