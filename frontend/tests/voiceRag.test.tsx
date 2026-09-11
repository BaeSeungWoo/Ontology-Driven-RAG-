import { useState } from "react";
import { act, cleanup, fireEvent, render, screen, waitFor } from "@testing-library/react";
import { afterEach, beforeEach, expect, it, vi } from "vitest";
import Question from "@/components/chat/question/question";
import { useChat } from "@/hooks/useChat";
import type { VoiceState } from "@/services/voiceInput";

const mock = vi.hoisted(() => ({
  post: vi.fn(), put: vi.fn(),
  callbacks: null as null | { onState: (s: VoiceState) => void; onComplete: (s: string) => void },
}));
vi.mock("@/services/api", () => ({ API_BASE_URL: "", default: { post: mock.post, put: mock.put } }));
vi.mock("@/services/voiceInput", () => ({
  voiceError: (e: Error) => e.message,
  VoiceSession: class {
    constructor(callbacks: NonNullable<typeof mock.callbacks>) { mock.callbacks = callbacks; }
    start() { mock.callbacks?.onState({ phase: "recording", committed: "", partial: "", level: 0 }); }
    cancel() {} stop() {}
  },
}));
function ChatHarness() {
  const [selectedSessionId, onSessionId] = useState<number | null>(null);
  const chat = useChat({ selectedSessionId, onSessionId });
  return <>
    <Question questioner="테스트 작업자" selectedLlmModel="ollama_config" selectedLlmMode="rag"
      selectedPersonaType="maintenance" selectedPrompt={{ prompt_no: 7, prompt_name: "설비", prompt_txt: "", create_user: "" }}
      onSend={chat.sendQuestion} isBusy={chat.isLoading} />
    <output data-testid="messages">{JSON.stringify(chat.messages)}</output>
  </>;
}
beforeEach(() => {
  mock.post.mockReset(); mock.put.mockReset().mockResolvedValue({ data: {} });
  mock.post.mockImplementation(async (url: string, payload: { role?: string }) => ({ data:
    url.endsWith("newSession") ? { session_id: 42 } : { message_id: payload.role === "user" ? 1 : 2 },
  }));
  Object.defineProperty(navigator, "mediaDevices", { configurable: true, value: { enumerateDevices: vi.fn().mockResolvedValue([]) } });
});
afterEach(() => { cleanup(); vi.unstubAllGlobals(); });
function voiceQuestion() {
  render(<ChatHarness />);
  fireEvent.click(screen.getByRole("button", { name: "음성으로 질문 입력" }));
  act(() => mock.callbacks?.onComplete("M08 공구 오류의 원인은 무엇인가요?"));
  expect(mock.post).not.toHaveBeenCalled();
  fireEvent.click(screen.getByRole("button", { name: "질문 전송" }));
}

it("uses real chatApi and useChat to stream the answer and preserve citations and history after voice input", async () => {
  const metadata = { chunks: [{ index: 1, text: "설비 점검", source: "manual.pdf" }] };
  const encoder = new TextEncoder();
  const response = new Response(new ReadableStream({ start(controller) {
    for (const text of ["META", "DATA:" + JSON.stringify(metadata) + "\n", "\n공구를 ", "확인하세요. [1]"]) {
      controller.enqueue(encoder.encode(text));
    }
    controller.close();
  } }));
  const fetchMock = vi.fn().mockResolvedValue(response); vi.stubGlobal("fetch", fetchMock);
  voiceQuestion();
  await waitFor(() => expect(mock.put).toHaveBeenCalledTimes(1));
  expect(fetchMock.mock.calls[0][0]).toBe("/api/chat/ollama_config");
  expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toMatchObject({ session_id: "42", question: "M08 공구 오류의 원인은 무엇인가요?",
    mode: "rag", prompt_no: 7, persona_type: "maintenance" });
  expect(mock.post).toHaveBeenCalledTimes(3);
  expect(mock.put.mock.calls[0][1]).toMatchObject({ content: "공구를 확인하세요. [1]", metadata: { ...metadata, used_chunks: metadata.chunks } });
  expect(screen.getByTestId("messages").textContent).toContain("공구를 확인하세요.");
  await waitFor(() => expect((screen.getByPlaceholderText("무엇이든 물어보세요.") as HTMLInputElement).value).toBe(""));
});

it("an existing RAG request failure keeps the voice question available for editing", async () => {
  vi.stubGlobal("fetch", vi.fn().mockResolvedValue(new Response("unavailable", { status: 503 })));
  voiceQuestion();
  await waitFor(() => expect(screen.getByRole("alert").textContent).toContain("유지"));
  expect((screen.getByPlaceholderText("무엇이든 물어보세요.") as HTMLInputElement).value).toBe("M08 공구 오류의 원인은 무엇인가요?");
  expect(mock.put).not.toHaveBeenCalled();
});
