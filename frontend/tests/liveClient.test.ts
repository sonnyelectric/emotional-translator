import { describe, expect, it } from 'vitest';
import { LiveClient, wsUrlFromHttpOrigin } from '../src/protocol/liveClient';
import type { InboundEvent } from '../src/protocol/events';
import { validateClientCommand } from '../src/protocol/validate';
import { readJson } from './helpers';

class FakeSocket {
  static last: FakeSocket[] = [];
  readyState = 0;
  binaryType = 'blob';
  bufferedAmount = 0;
  sent: (string | ArrayBuffer)[] = [];
  onopen: (() => void) | null = null;
  onmessage: ((ev: { data: unknown }) => void) | null = null;
  onclose: ((ev: { code: number; reason: string; wasClean: boolean }) => void) | null = null;
  onerror: (() => void) | null = null;
  constructor(readonly url: string) {
    FakeSocket.last.push(this);
  }
  send(d: string | ArrayBuffer) {
    this.sent.push(d);
  }
  close() {
    this.readyState = 3;
  }
  open() {
    this.readyState = 1;
    this.onopen?.();
  }
  recv(obj: unknown) {
    this.onmessage?.({ data: typeof obj === 'string' ? obj : JSON.stringify(obj) });
  }
}

function make() {
  FakeSocket.last = [];
  const events: InboundEvent[] = [];
  const diags: string[] = [];
  let opened = 0;
  const client = new LiveClient(
    'http://127.0.0.1:8102',
    {
      onEvent: (e) => events.push(e),
      onOpen: () => opened++,
      onClose: () => {},
      onDiagnostic: (m) => diags.push(m),
    },
    (url) => new FakeSocket(url) as unknown as WebSocket,
  );
  return { client, events, diags, opened: () => opened };
}

describe('LiveClient', () => {
  it('derives the WS URL from the backend HTTP origin', () => {
    expect(wsUrlFromHttpOrigin('http://127.0.0.1:8000')).toBe('ws://127.0.0.1:8000/ws/v1/session');
  });

  it('sends schema-valid commands and forwards validated events', () => {
    const { client, events, diags } = make();
    client.connect();
    const s = FakeSocket.last[0];
    expect(s.binaryType).toBe('arraybuffer');
    s.open();
    expect(client.send('session.start')).toBe(true);
    expect(validateClientCommand(JSON.parse(s.sent[0] as string))).toBe(true);
    const live = readJson<unknown[]>('server_examples.json');
    s.recv(live[0]);
    s.recv('{"support":NaN}');
    s.recv({ schema_version: '2.0', type: 'session.status' });
    s.recv({ schema_version: '1.0', type: 'future.thing', session_id: 's-live', seq: 9, issued_at_ms: 5, payload: {} });
    expect(events.map((e) => e.type)).toEqual(['session.status', 'future.thing']);
    expect(diags.filter((d) => d.startsWith('invalid'))).toHaveLength(2);
  });

  it('ignores callbacks from a superseded socket generation', () => {
    const { client, events } = make();
    client.connect();
    const old = FakeSocket.last[0];
    old.open();
    client.connect();
    const fresh = FakeSocket.last[1];
    fresh.open();
    old.recv(readJson<unknown[]>('server_examples.json')[0]);
    expect(events).toHaveLength(0);
    fresh.recv(readJson<unknown[]>('server_examples.json')[0]);
    expect(events).toHaveLength(1);
  });

  it('refuses audio when closed or congested and only sends legal frame sizes', () => {
    const { client } = make();
    expect(client.sendAudio(new ArrayBuffer(1280))).toBe('closed');
    client.connect();
    const s = FakeSocket.last[0];
    s.open();
    expect(client.sendAudio(new ArrayBuffer(1280))).toBe('sent');
    client.sendAudio(new ArrayBuffer(100)); // illegal size: not sent
    expect(s.sent.filter((x) => x instanceof ArrayBuffer)).toHaveLength(1);
    s.bufferedAmount = 10 * 1024 * 1024;
    expect(client.sendAudio(new ArrayBuffer(1280))).toBe('congested');
  });

  it('no audio after close', () => {
    const { client } = make();
    client.connect();
    const s = FakeSocket.last[0];
    s.open();
    client.close();
    expect(client.sendAudio(new ArrayBuffer(1280))).toBe('closed');
    expect(s.sent).toHaveLength(0);
  });
});
