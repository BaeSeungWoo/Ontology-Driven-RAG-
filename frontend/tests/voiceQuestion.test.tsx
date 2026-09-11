import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import Question from "@/components/chat/question/question";
import type { VoiceState } from "@/services/voiceInput";

const mock = vi.hoisted(() => ({ sessions: [] as Array<{
  callbacks: { onState: (s: VoiceState) => void; onComplete: (t: string) => void; onError: (e: string) => void };
  cancel: ReturnType<typeof vi.fn>; stop: ReturnType<typeof vi.fn>;
}> }));
vi.mock("@/services/voiceInput", () => ({
  voiceError: (e: Error) => e.message,
  VoiceSession: class {
    cancel = vi.fn(); stop = vi.fn();
    constructor(public callbacks: typeof mock.sessions[number]["callbacks"]) { mock.sessions.push(this); }
    start() { this.callbacks.onState({ phase: "recording", committed: "", partial: "", level: 0 }); }
  },
}));
const props = {
  questioner: "작업자", selectedLlmModel: "ollama_config" as const,
  selectedLlmMode: "rag" as const, selectedPersonaType: "operator" as const,
  selectedPrompt: { prompt_no: 7, prompt_name: "설비", prompt_txt: "", create_user: "" },
};
const input = () => screen.getByPlaceholderText("무엇이든 물어보세요.") as HTMLInputElement;
const send = () => screen.getByRole("button", { name: "질문 전송" }) as HTMLButtonElement;
const mic = () => fireEvent.click(screen.getByRole("button", { name: "음성으로 질문 입력" }));
beforeEach(() => {
  mock.sessions.length = 0;
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { enumerateDevices: vi.fn().mockResolvedValue([]) } });
});
afterEach(cleanup);

describe("voice question integration", () => {
  it("previews snapshots without submitting, then appends final text and uses the existing question payload", async () => {
    const onSend = vi.fn().mockResolvedValue(true);
    render(<Question {...props} onSend={onSend} />);
    fireEvent.change(input(), { target: { value: "M08" } }); mic();
    act(() => mock.sessions[0].callbacks.onState({ phase: "recording", committed: "공구", partial: "오류", level: .4 }));
    expect(input().value).toBe("M08"); expect(send().disabled).toBe(true); expect(onSend).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "완료" }));
    expect(mock.sessions[0].stop).toHaveBeenCalledTimes(1);
    expect(input().value).toBe("M08");
    act(() => mock.sessions[0].callbacks.onComplete("공구 오류 원인은 무엇인가요?"));
    expect(input().value).toBe("M08 공구 오류 원인은 무엇인가요?");
    fireEvent.click(send());
    await waitFor(() => expect(input().value).toBe(""));
    expect(onSend).toHaveBeenCalledExactlyOnceWith({ question: "M08 공구 오류 원인은 무엇인가요?", questioner: "작업자",
      llmModel: "ollama_config", llmMode: "rag", personaType: "operator", prompt: props.selectedPrompt });
  });

  it("cancel preserves the draft and ignores late transcription", () => {
    render(<Question {...props} onSend={vi.fn()} />);
    fireEvent.change(input(), { target: { value: "기존 질문" } }); mic();
    fireEvent.click(screen.getByRole("button", { name: "취소" }));
    expect(mock.sessions[0].cancel).toHaveBeenCalledTimes(1);
    act(() => mock.sessions[0].callbacks.onComplete("취소한 음성"));
    expect(input().value).toBe("기존 질문"); expect(send().disabled).toBe(false);
  });

  it("settings changes cancel the active microphone but preserve typed text", () => {
    const onSend = vi.fn();
    const view = render(<Question {...props} onSend={onSend} />);
    fireEvent.change(input(), { target: { value: "작성 내용" } }); mic();
    view.rerender(<Question {...props} selectedPersonaType="engineer" onSend={onSend} />);
    expect(mock.sessions[0].cancel).toHaveBeenCalledTimes(1);
    act(() => mock.sessions[0].callbacks.onComplete("이전 설정의 음성"));
    expect(input().value).toBe("작성 내용"); expect(send().disabled).toBe(false);
  });

  it("conversation remount cancels recording and cannot insert into the new conversation", () => {
    const view = render(<Question key="conversation1" {...props} onSend={vi.fn()} />); mic();
    view.rerender(<Question key="conversation2" {...props} onSend={vi.fn()} />);
    expect(mock.sessions[0].cancel).toHaveBeenCalledTimes(1);
    act(() => mock.sessions[0].callbacks.onComplete("이전 대화"));
    expect(input().value).toBe("");
  });

  it("errors preserve the draft and leave text input usable", () => {
    render(<Question {...props} onSend={vi.fn()} />);
    fireEvent.change(input(), { target: { value: "기존 질문" } }); mic();
    act(() => mock.sessions[0].callbacks.onError("마이크 권한 오류"));
    expect(screen.getByRole("alert").textContent).toContain("마이크 권한 오류");
    expect(input().value).toBe("기존 질문"); expect(input().readOnly).toBe(false);
  });

  it("locks repeated submits through session creation and preserves input on failure", async () => {
    let resolve!: (result: boolean) => void;
    const onSend = vi.fn(() => new Promise<boolean>(r => { resolve = r; }));
    render(<Question {...props} onSend={onSend} />);
    fireEvent.change(input(), { target: { value: "질문" } });
    fireEvent.submit(input().closest("form")!); fireEvent.submit(input().closest("form")!);
    expect(onSend).toHaveBeenCalledTimes(1); expect(input().readOnly).toBe(true);
    await act(async () => resolve(false));
    expect(input().value).toBe("질문"); expect(send().disabled).toBe(false);
    expect(screen.getByRole("alert").textContent).toContain("유지");
  });

  it("requires the existing questioner and prompt before any submission", () => {
    const onSend = vi.fn();
    render(<Question {...props} questioner="" onSend={onSend} />);
    fireEvent.change(input(), { target: { value: "질문" } }); fireEvent.submit(input().closest("form")!);
    expect(onSend).not.toHaveBeenCalled();
  });
});
