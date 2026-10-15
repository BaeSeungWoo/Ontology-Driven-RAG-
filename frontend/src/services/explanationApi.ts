import { API_BASE_URL } from "@/services/api";

export type ManualSource = { index: number; document_name: string; page: string; excerpt: string };
type Explanation = { answer: string; sources: ManualSource[] };

export async function streamExplanation(
  path: string, payload: unknown, signal: AbortSignal,
  onUpdate: (result: Explanation) => void,
): Promise<Explanation> {
  const controller = new AbortController();
  const abort = () => controller.abort();
  signal.addEventListener("abort", abort, { once: true });
  if (signal.aborted) controller.abort();
  let timer: ReturnType<typeof setTimeout>;
  let reader: ReadableStreamDefaultReader<Uint8Array> | undefined;
  const resetTimeout = () => {
    clearTimeout(timer);
    timer = setTimeout(abort, 120_000);
  };
  resetTimeout();
  try {
    const response = await fetch(`${API_BASE_URL}${path}`, {
      method: "POST", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(payload), signal: controller.signal,
    });
    if (!response.ok) {
      const data = await response.json().catch(() => null);
      throw new Error(typeof data?.detail === "string" ? data.detail : `설명 요청 실패: ${response.status}`);
    }
    if (!response.body) throw new Error("스트리밍 응답 본문이 없습니다.");
    reader = response.body.getReader();
    const decoder = new TextDecoder();
    let pending = "";
    const result: Explanation = { answer: "", sources: [] };
    while (true) {
      resetTimeout();
      const { done, value } = await reader.read();
      if (done) throw new Error("답변이 완료되기 전에 연결이 종료되었습니다. 다시 시도해 주세요.");
      pending += decoder.decode(value, { stream: true });
      let newline: number;
      while ((newline = pending.indexOf("\n")) >= 0) {
        const line = pending.slice(0, newline);
        pending = pending.slice(newline + 1);
        if (!line.trim()) continue;
        const event = JSON.parse(line);
        if (event.error) throw new Error(event.error);
        if (event.sources) result.sources = event.sources;
        if (event.delta) result.answer += event.delta;
        if (event.done) {
          if (!result.answer.trim()) throw new Error("설명 답변이 비어 있습니다. 다시 시도해 주세요.");
          return result;
        }
        if (result.answer) onUpdate({ ...result });
      }
    }
  } catch (error) {
    if (controller.signal.aborted && !signal.aborted) {
      throw new Error("2분 동안 서버 응답이 없어 연결을 중단했습니다. 다시 시도해 주세요.");
    }
    throw error;
  } finally {
    clearTimeout(timer!);
    signal.removeEventListener("abort", abort);
    controller.abort();
    void reader?.cancel().catch(() => {});
  }
}
