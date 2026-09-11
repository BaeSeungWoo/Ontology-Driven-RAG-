import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { VoiceSession, type VoiceState } from "@/services/voiceInput";
vi.mock("@/services/api", () => ({ API_BASE_URL: "" }));

class Socket {
  static OPEN = 1;
  static instances: Socket[] = [];
  readyState = 1; bufferedAmount = 0;
  onmessage: ((event: { data: string }) => void) | null = null;
  onerror: (() => void) | null = null;
  onclose: (() => void) | null = null;
  send = vi.fn(); close = vi.fn();
  constructor(public url: URL, public protocols: string[]) { Socket.instances.push(this); }
  message(data: object) { this.onmessage?.({ data: JSON.stringify(data) }); }
}
class AudioNode {
  static instances: AudioNode[] = [];
  connect = vi.fn(); disconnect = vi.fn();
  port = {
    onmessage: null as ((event: { data: object }) => void) | null,
    postMessage: vi.fn((value: string) => {
      if (value === "flush") {
        this.port.onmessage?.({ data: { type: "pcm", buffer: new ArrayBuffer(2), rms: 0 } });
        this.port.onmessage?.({ data: { type: "flushed" } });
      }
    }),
  };
  constructor() { AudioNode.instances.push(this); }
}
class Context {
  static instances: Context[] = [];
  sampleRate = 16000; state = "running";
  destination = {}; onstatechange: (() => void) | null = null;
  audioWorklet = { addModule: vi.fn().mockResolvedValue(undefined) };
  resume = vi.fn().mockResolvedValue(undefined);
  close = vi.fn(async () => { this.state = "closed"; });
  createMediaStreamSource = () => ({ connect: vi.fn(), disconnect: vi.fn() });
  createGain = () => ({ gain: { value: 1 }, connect: vi.fn(), disconnect: vi.fn() });
  constructor() { Context.instances.push(this); }
}
let track: { stop: ReturnType<typeof vi.fn>; onended: (() => void) | null };
let getUserMedia: ReturnType<typeof vi.fn>;
let sessions: VoiceSession[];
const tick = async () => { for (let i = 0; i < 15; i++) await Promise.resolve(); };
function create() {
  const states: VoiceState[] = [];
  const onComplete = vi.fn(), onError = vi.fn();
  const session = new VoiceSession({ onState: state => states.push(state), onComplete, onError });
  sessions.push(session);
  return { session, states, onComplete, onError };
}
async function record() {
  const current = create(); const starting = current.session.start(); await tick();
  const socket = Socket.instances[0];
  socket.message({ type: "config", sampleRate: 16000, useAudioWorklet: true });
  await starting;
  return { ...current, socket, node: AudioNode.instances[0] };
}
beforeEach(() => {
  vi.useFakeTimers(); Socket.instances = []; AudioNode.instances = []; Context.instances = []; sessions = [];
  track = { stop: vi.fn(), onended: null };
  getUserMedia = vi.fn().mockResolvedValue({ getTracks: () => [track] });
  Object.defineProperty(window, "isSecureContext", { configurable: true, value: true });
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { getUserMedia } });
  vi.stubGlobal("AudioContext", Context); vi.stubGlobal("AudioWorkletNode", AudioNode); vi.stubGlobal("WebSocket", Socket);
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true, json: async () => ({ ticket: "single-use", max_seconds: 180 }) }));
});
afterEach(() => { sessions.forEach(s => s.cancel()); vi.useRealTimers(); vi.unstubAllGlobals(); });

describe("browser voice transport", () => {
  it("replaces repeated snapshots, flushes the last PCM before EOF, and completes exactly once on acknowledgement", async () => {
    const { session, socket, node, states, onComplete, onError } = await record();
    expect(socket.protocols).toEqual(["voice.v1", "ticket.single-use"]);
    expect(socket.url.search).toBe("");
    const snapshot = { lines: [{ text: "공구", speaker: 1 }, { text: null, speaker: -2 }], buffer_transcription: "오류" };
    socket.message(snapshot); socket.message(snapshot);
    expect(states.at(-1)?.committed).toBe("공구"); expect(onComplete).not.toHaveBeenCalled();
    node.port.onmessage?.({ data: { type: "pcm", buffer: new ArrayBuffer(3200), rms: .1 } });
    await session.stop();
    expect(socket.send.mock.calls.map(c => c[0].byteLength)).toEqual([3200, 2, 0]);
    expect(states.at(-1)?.phase).toBe("finishing"); expect(onComplete).not.toHaveBeenCalled();
    socket.message({ lines: [{ text: "공구 오류 원인은 무엇인가요?" }], buffer_transcription: "" });
    socket.message({ type: "ready_to_stop" }); socket.message({ type: "ready_to_stop" }); await tick();
    expect(onComplete).toHaveBeenCalledExactlyOnceWith("공구 오류 원인은 무엇인가요?");
    expect(onError).not.toHaveBeenCalled(); expect(track.stop).toHaveBeenCalled(); expect(socket.close).toHaveBeenCalledTimes(1);
  });

  it("stops a microphone permission grant arriving after cancellation", async () => {
    let grant!: (value: object) => void;
    getUserMedia.mockReturnValue(new Promise(resolve => { grant = resolve; }));
    const { session, onComplete, onError } = create(); const started = session.start(); session.cancel();
    grant({ getTracks: () => [track] }); await started;
    expect(track.stop).toHaveBeenCalledTimes(1); expect(fetch).not.toHaveBeenCalled();
    expect(onComplete).not.toHaveBeenCalled(); expect(onError).not.toHaveBeenCalled();
  });

  it("cancelling during final drain never accepts late text", async () => {
    const { session, socket, onComplete, onError } = await record(); await session.stop();
    session.cancel();
    socket.message({ lines: [{ text: "늦은 결과" }], buffer_transcription: "" }); socket.message({ type: "ready_to_stop" });
    await tick(); expect(onComplete).not.toHaveBeenCalled(); expect(onError).not.toHaveBeenCalled();
  });

  it("refuses to insert unfinished text even if the upstream acknowledges", async () => {
    const { session, socket, onComplete, onError } = await record();
    socket.message({ lines: [{ text: "확정" }], buffer_transcription: "미확정" });
    await session.stop(); socket.message({ type: "ready_to_stop" }); await tick();
    expect(onComplete).not.toHaveBeenCalled(); expect(onError).toHaveBeenCalledTimes(1);
  });

  it("releases microphone on network failure and reports only one error", async () => {
    const { socket, onComplete, onError } = await record();
    socket.onerror?.(); socket.onclose?.(); await tick();
    expect(track.stop).toHaveBeenCalled(); expect(Context.instances[0].state).toBe("closed");
    expect(onError).toHaveBeenCalledTimes(1); expect(onComplete).not.toHaveBeenCalled();
  });

  it("bounds queued audio when network cannot keep up", async () => {
    const { socket, node, onError } = await record(); socket.bufferedAmount = 160001;
    node.port.onmessage?.({ data: { type: "pcm", buffer: new ArrayBuffer(3200), rms: .1 } });
    await tick(); expect(socket.send).not.toHaveBeenCalled(); expect(onError).toHaveBeenCalledTimes(1);
  });

  it("times out handshake and final drain", async () => {
    const first = create(); const started = first.session.start(); await tick();
    await vi.advanceTimersByTimeAsync(15001); await started;
    expect(first.onError).toHaveBeenCalledTimes(1); expect(track.stop).toHaveBeenCalled();
    Socket.instances = [];
    const second = await record(); await second.session.stop(); await vi.advanceTimersByTimeAsync(65001);
    expect(second.onError).toHaveBeenCalledTimes(1); expect(second.onComplete).not.toHaveBeenCalled();
  });

  it("rejects insecure public HTTP before requesting microphone access", async () => {
    Object.defineProperty(window, "isSecureContext", { configurable: true, value: false });
    const { session, onError } = create(); await session.start();
    expect(getUserMedia).not.toHaveBeenCalled(); expect(onError.mock.calls[0][0]).toContain("HTTPS");
  });
});
