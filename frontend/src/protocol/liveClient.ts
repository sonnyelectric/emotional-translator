// Live WebSocket transport. Text frames are validated (strict parse + schema) and handed to
// the shared reducer by the caller; binary frames out are PCM. Every socket gets a
// generation number so callbacks from superseded sockets are ignored.
import { makeCommand, type ClientCommandType, type InboundEvent } from './events';
import { decodeServerFrame } from './validate';

export interface LiveClientHandlers {
  onEvent(event: InboundEvent): void;
  onOpen(): void;
  onClose(info: { code: number; reason: string; wasClean: boolean }): void;
  onDiagnostic(message: string): void;
}

/** Above this many unsent bytes we stop forwarding audio rather than silently splice it. */
export const MAX_BUFFERED_BYTES = 512 * 1024;

export function wsUrlFromHttpOrigin(origin: string): string {
  const u = new URL(origin);
  u.protocol = u.protocol === 'https:' ? 'wss:' : 'ws:';
  u.pathname = '/ws/v1/session';
  u.search = '';
  u.hash = '';
  return u.toString();
}

const WS_CONNECTING = 0;
const WS_OPEN = 1;

export type SocketFactory = (url: string) => WebSocket;

export class LiveClient {
  private ws: WebSocket | null = null;
  private generation = 0;
  private congested = false;

  constructor(
    private readonly httpOrigin: string,
    private readonly handlers: LiveClientHandlers,
    private readonly makeSocket: SocketFactory = (url) => new WebSocket(url),
  ) {}

  get isOpen(): boolean {
    return this.ws !== null && this.ws.readyState === WS_OPEN;
  }

  get currentGeneration(): number {
    return this.generation;
  }

  /** Open a new transport generation (closes any previous one first). */
  connect(): void {
    this.close(1000, 'superseded');
    const gen = ++this.generation;
    const ws = this.makeSocket(wsUrlFromHttpOrigin(this.httpOrigin));
    ws.binaryType = 'arraybuffer';
    this.ws = ws;
    this.congested = false;
    ws.onopen = () => {
      if (gen !== this.generation) return;
      this.handlers.onOpen();
    };
    ws.onmessage = (ev: MessageEvent) => {
      if (gen !== this.generation) return;
      if (typeof ev.data !== 'string') {
        this.handlers.onDiagnostic('ignored unexpected binary frame from server');
        return;
      }
      const c = decodeServerFrame(ev.data);
      if (c.kind === 'invalid') {
        this.handlers.onDiagnostic(`invalid server event ignored: ${c.reason}`);
        return;
      }
      if (c.kind === 'unknown') this.handlers.onDiagnostic(`unknown v1 event type ignored: ${c.event.type}`);
      this.handlers.onEvent(c.event);
    };
    ws.onclose = (ev: CloseEvent) => {
      if (gen !== this.generation) return;
      this.ws = null;
      this.handlers.onClose({ code: ev.code, reason: ev.reason, wasClean: ev.wasClean });
    };
    ws.onerror = () => {
      if (gen !== this.generation) return;
      this.handlers.onDiagnostic('websocket error');
    };
  }

  send(type: ClientCommandType): boolean {
    if (!this.isOpen) return false;
    this.ws!.send(JSON.stringify(makeCommand(type)));
    return true;
  }

  /**
   * Send one PCM frame. Returns false (and drops nothing silently) when the socket is not
   * open or is congested; the caller must then pause/stop with a warning.
   */
  sendAudio(frame: ArrayBuffer): 'sent' | 'closed' | 'congested' {
    if (!this.isOpen) return 'closed';
    if (this.congested || this.ws!.bufferedAmount > MAX_BUFFERED_BYTES) {
      this.congested = true;
      return 'congested';
    }
    if (frame.byteLength < 640 || frame.byteLength > 3200 || frame.byteLength % 2 !== 0) {
      this.handlers.onDiagnostic(`refused to send invalid PCM frame of ${frame.byteLength} bytes`);
      return 'sent';
    }
    this.ws!.send(frame);
    return 'sent';
  }

  /** Close the current generation; its later callbacks are ignored. */
  close(code = 1000, reason = 'client closed'): void {
    const ws = this.ws;
    this.ws = null;
    this.generation++;
    if (ws && (ws.readyState === WS_OPEN || ws.readyState === WS_CONNECTING)) {
      try {
        ws.close(code, reason);
      } catch {
        /* ignore */
      }
    }
  }
}
