import type { WsEnvelope } from "./types";

type Listener = (env: WsEnvelope) => void;

export class WsManager {
  private url: string;
  private ws: WebSocket | null = null;
  private listeners = new Set<Listener>();
  private statusListeners = new Set<(s: "connecting" | "open" | "closed") => void>();
  private retryMs = 500;
  private stopped = false;
  private queue: string[] = [];

  constructor(url: string) {
    this.url = url;
  }

  connect() {
    this.stopped = false;
    this.open();
  }

  private open() {
    this.emitStatus("connecting");
    try {
      this.ws = new WebSocket(this.url);
    } catch (e) {
      this.scheduleReconnect();
      return;
    }
    this.ws.onopen = () => {
      this.retryMs = 500;
      this.emitStatus("open");
      for (const m of this.queue.splice(0)) this.ws?.send(m);
    };
    this.ws.onmessage = (ev) => {
      try {
        const env = JSON.parse(ev.data as string) as WsEnvelope;
        this.listeners.forEach((l) => l(env));
      } catch {
        /* ignore */
      }
    };
    this.ws.onclose = () => {
      this.emitStatus("closed");
      if (!this.stopped) this.scheduleReconnect();
    };
    this.ws.onerror = () => this.ws?.close();
  }

  private scheduleReconnect() {
    const delay = Math.min(this.retryMs, 10_000);
    this.retryMs = Math.min(this.retryMs * 2, 10_000);
    setTimeout(() => {
      if (!this.stopped) this.open();
    }, delay);
  }

  send(obj: object) {
    const m = JSON.stringify(obj);
    if (this.ws && this.ws.readyState === WebSocket.OPEN) this.ws.send(m);
    else this.queue.push(m);
  }

  selectInstance(instanceId: number) {
    this.send({ action: "select_instance", instance_id: instanceId });
  }

  subscribe(l: Listener) {
    this.listeners.add(l);
    return () => this.listeners.delete(l);
  }

  subscribeStatus(l: (s: "connecting" | "open" | "closed") => void) {
    this.statusListeners.add(l);
    return () => this.statusListeners.delete(l);
  }

  private emitStatus(s: "connecting" | "open" | "closed") {
    this.statusListeners.forEach((l) => l(s));
  }

  close() {
    this.stopped = true;
    this.ws?.close();
  }
}

export function createWs(): WsManager {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${window.location.host}/ws`;
  return new WsManager(url);
}
