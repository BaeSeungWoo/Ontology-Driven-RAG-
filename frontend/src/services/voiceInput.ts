import { API_BASE_URL } from "./api";

export type VoiceState = {
  phase: "connecting" | "recording" | "finishing";
  committed: string;
  partial: string;
  level: number;
};
type Line = { text?: string | null; speaker?: number };
type VoiceMessage = {
  type?: string; error?: string; status?: string; sampleRate?: number;
  useAudioWorklet?: boolean; lines?: Line[]; buffer_transcription?: string;
};
type Callbacks = {
  onState: (state: VoiceState) => void;
  onComplete: (text: string) => void;
  onError: (message: string) => void;
};

export function voiceError(error: unknown): string {
  const e = error instanceof Error ? error : new Error(String(error));
  return ({
    NotAllowedError: "마이크 권한을 허용해 주세요. 브라우저의 사이트 설정에서 변경할 수 있습니다.",
    NotFoundError: "마이크를 찾지 못했습니다. 마이크나 헤드셋을 연결해 주세요.",
    NotReadableError: "마이크를 사용할 수 없습니다. 다른 앱의 사용 여부를 확인해 주세요.",
    OverconstrainedError: "선택한 마이크가 없습니다. 기본 마이크로 다시 시도해 주세요.",
  } as Record<string, string>)[e.name] ?? e.message;
}

/** One microphone turn. WLK snapshots update the preview; only EOF acknowledgement completes it. */
export class VoiceSession {
  private state: VoiceState = { phase: "connecting", committed: "", partial: "", level: 0 };
  private stream?: MediaStream;
  private context?: AudioContext;
  private node?: AudioWorkletNode;
  private source?: MediaStreamAudioSourceNode;
  private mute?: GainNode;
  private socket?: WebSocket;
  private abort = new AbortController();
  private timers = new Set<ReturnType<typeof setTimeout>>();
  private pending = new Set<(error: Error) => void>();
  private done = false;
  private cancelled = false;
  private eofSent = false;
  private flushResolve?: () => void;

  constructor(private callbacks: Callbacks) {}

  private emit(update: Partial<VoiceState>) {
    if (this.done) return;
    this.state = { ...this.state, ...update };
    this.callbacks.onState(this.state);
  }
  private assertActive() {
    if (this.done) throw new DOMException("Cancelled", "AbortError");
  }
  private timer(fn: () => void, ms: number) {
    const timer = setTimeout(() => { this.timers.delete(timer); fn(); }, ms);
    this.timers.add(timer);
    return timer;
  }

  async start(deviceId = ""): Promise<void> {
    try {
      this.emit({ phase: "connecting" });
      if (!window.isSecureContext || !navigator.mediaDevices?.getUserMedia) {
        throw new Error("음성 입력은 HTTPS 또는 localhost에서 사용할 수 있습니다.");
      }
      this.stream = await navigator.mediaDevices.getUserMedia({ audio: {
        ...(deviceId ? { deviceId: { exact: deviceId } } : {}), channelCount: 1,
        echoCancellation: true, noiseSuppression: true, autoGainControl: true,
      } });
      // Permission may arrive after the user has cancelled or changed conversations.
      if (this.done) this.stream.getTracks().forEach(track => track.stop());
      this.assertActive();
      this.context = new AudioContext({ sampleRate: 16000 });
      await this.context.resume(); this.assertActive();
      if (this.context.sampleRate !== 16000) throw new Error("이 브라우저는 필요한 음성 형식을 지원하지 않습니다. Chrome 또는 Edge를 사용해 주세요.");
      await this.context.audioWorklet.addModule("/voice/pcm-worklet.js"); this.assertActive();

      const requestTimer = this.timer(() => this.abort.abort(), 15000);
      let response: Response;
      try {
        response = await fetch(`${API_BASE_URL}/api/voice/sessions`, {
          method: "POST", headers: { "Content-Type": "application/json" },
          credentials: "same-origin", body: "{}", signal: this.abort.signal,
        });
      } finally { clearTimeout(requestTimer); this.timers.delete(requestTimer); }
      this.assertActive();
      if (!response.ok) {
        const body = await response.json().catch(() => ({}));
        throw new Error(typeof body.detail === "string" ? body.detail : "음성 서버를 연결하지 못했습니다. 잠시 후 다시 시도해 주세요.");
      }
      const session: { ticket: string; max_seconds: number } = await response.json();
      this.assertActive();
      if (!session.ticket || !Number.isFinite(session.max_seconds)) throw new Error("음성 서버 설정이 올바르지 않습니다.");
      await this.connect(session.ticket); this.assertActive();
      this.node = new AudioWorkletNode(this.context, "pcm-capture", {
        numberOfInputs: 1, numberOfOutputs: 1, outputChannelCount: [1],
      });
      this.node.onprocessorerror = () => void this.fail(new Error("마이크 처리에 실패했습니다. 다시 시작해 주세요."));
      this.node.port.onmessage = ({ data }) => {
        if (this.done) return;
        if (data.type === "flushed") { this.flushResolve?.(); return; }
        if (data.type !== "pcm") return;
        if (this.socket?.readyState !== WebSocket.OPEN) {
          void this.fail(new Error("음성 연결이 끊겼습니다. 다시 시작해 주세요.")); return;
        }
        if (this.socket.bufferedAmount > 160000) {
          void this.fail(new Error("음성 전송이 지연되었습니다. 네트워크 연결을 확인해 주세요.")); return;
        }
        this.socket.send(data.buffer);
        this.emit({ level: Math.min(1, data.rms * 5) });
      };
      this.source = this.context.createMediaStreamSource(this.stream);
      this.mute = this.context.createGain(); this.mute.gain.value = 0;
      this.source.connect(this.node); this.node.connect(this.mute); this.mute.connect(this.context.destination);
      for (const track of this.stream.getTracks()) track.onended = () => void this.fail(new Error("마이크 연결이 해제되었습니다."));
      this.context.onstatechange = () => {
        if (this.state.phase === "recording" && this.context?.state !== "running") {
          void this.fail(new Error("브라우저가 음성 입력을 중단했습니다. 다시 시작해 주세요."));
        }
      };
      this.emit({ phase: "recording" });
      this.timer(() => void this.stop(), Math.max(1, session.max_seconds - 2) * 1000);
    } catch (error) { if (!this.done) await this.fail(error); }
  }

  private connect(ticket: string): Promise<void> {
    const url = new URL(`${API_BASE_URL}/api/voice/stream`, window.location.origin);
    url.protocol = url.protocol === "https:" ? "wss:" : "ws:";
    if (window.location.protocol === "https:" && url.protocol !== "wss:") {
      throw new Error("음성 서버 주소를 HTTPS에 맞게 설정해 주세요.");
    }
    return new Promise((resolve, reject) => {
      this.pending.add(reject);
      const timer = this.timer(() => void this.fail(new Error("음성 서버 응답 시간이 초과되었습니다.")), 15000);
      this.socket = new WebSocket(url, ["voice.v1", `ticket.${ticket}`]);
      let configured = false;
      this.socket.onmessage = ({ data }) => {
        if (this.done) return;
        let message: VoiceMessage;
        try { message = JSON.parse(data); } catch { void this.fail(new Error("음성 서버 응답 형식이 잘못되었습니다.")); return; }
        if (message.error || message.type === "error" || message.status === "error") {
          void this.fail(new Error(message.error || "음성 인식에 실패했습니다.")); return;
        }
        if (message.type === "config") {
          if (configured || !message.useAudioWorklet || message.sampleRate !== 16000) {
            void this.fail(new Error("음성 서버의 입력 형식이 일치하지 않습니다.")); return;
          }
          configured = true; clearTimeout(timer); this.timers.delete(timer);
          this.pending.delete(reject); resolve(); return;
        }
        if (message.type === "ready_to_stop") {
          if (!this.eofSent) { void this.fail(new Error("음성 인식이 예기치 않게 종료되었습니다.")); return; }
          const text = this.state.committed.trim();
          if (this.state.partial.trim()) {
            void this.fail(new Error("음성이 완전히 확정되지 않았습니다. 다시 입력해 주세요.")); return;
          }
          if (!text) { void this.fail(new Error("인식된 음성이 없습니다. 마이크를 확인하고 다시 말해 주세요.")); return; }
          void this.complete(text); return;
        }
        if (!configured) return;
        const update: Partial<VoiceState> = {};
        if (Array.isArray(message.lines)) {
          update.committed = message.lines.filter(line => line.speaker !== -2 && typeof line.text === "string")
            .map(line => line.text!.trim()).filter(Boolean).join(" ");
        }
        if (typeof message.buffer_transcription === "string") update.partial = message.buffer_transcription;
        this.emit(update);
      };
      this.socket.onerror = () => void this.fail(new Error("음성 서버에 연결할 수 없습니다."));
      this.socket.onclose = () => { if (!this.done) void this.fail(new Error("음성 연결이 종료되었습니다. 작성 중인 질문은 유지됩니다.")); };
    });
  }

  async stop(): Promise<void> {
    if (this.done || this.state.phase !== "recording") return;
    this.emit({ phase: "finishing", level: 0 });
    for (const track of this.stream?.getTracks() ?? []) { track.onended = null; track.stop(); }
    try {
      await new Promise<void>((resolve, reject) => {
        this.pending.add(reject);
        const timer = this.timer(() => reject(new Error("마이크 종료 시간이 초과되었습니다.")), 3000);
        this.flushResolve = () => { clearTimeout(timer); this.timers.delete(timer); this.pending.delete(reject); resolve(); };
        this.node!.port.postMessage("flush");
      });
      this.assertActive();
      this.context!.onstatechange = null;
      await this.context!.close(); this.assertActive();
      this.eofSent = true;
      this.socket!.send(new ArrayBuffer(0));
      this.timer(() => void this.fail(new Error("마지막 음성 처리 시간이 초과되었습니다. 다시 입력해 주세요.")), 65000);
    } catch (error) { if (!this.done) await this.fail(error); }
  }

  cancel(): void {
    this.cancelled = true;
    void this.cleanup();
  }
  private async complete(text: string) {
    if (this.done) return;
    await this.cleanup();
    if (!this.cancelled) this.callbacks.onComplete(text);
  }
  private async fail(error: unknown) {
    if (this.done) return;
    await this.cleanup();
    if (!this.cancelled) this.callbacks.onError(voiceError(error));
  }
  private async cleanup() {
    if (this.done) return;
    this.done = true;
    this.abort.abort();
    for (const timer of this.timers) clearTimeout(timer);
    this.timers.clear();
    for (const reject of this.pending) reject(new DOMException("Cancelled", "AbortError"));
    this.pending.clear();
    if (this.socket) {
      this.socket.onmessage = null; this.socket.onerror = null; this.socket.onclose = null;
      this.socket.close();
    }
    for (const track of this.stream?.getTracks() ?? []) { track.onended = null; track.stop(); }
    this.source?.disconnect(); this.node?.disconnect(); this.mute?.disconnect();
    if (this.context) {
      this.context.onstatechange = null;
      if (this.context.state !== "closed") await this.context.close().catch(() => {});
    }
  }
}
