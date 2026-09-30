import { useEffect, useState } from "react";
import { API_BASE_URL } from "@/services/api";
import styles from "./answer.module.css";

type Props = {
  source?: "manual" | "ladder" | "cms_engineer" | "cms_manager";
  sessionId: number | null;
  question: string;
  answer: string;
  canSend: boolean;
  visible?: boolean;
  onSelect: (question: string) => void;
};

export default function RecommendedQuestions({ source = "manual", sessionId, question, answer, canSend, visible = true, onSelect }: Props) {
  const [questions, setQuestions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [machineLabel, setMachineLabel] = useState("");

  useEffect(() => {
    const controller = new AbortController();
    setMachineLabel("");
    if (source.startsWith("cms_")) {
      void fetch(`${API_BASE_URL}/api/recommendations/context`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId === null ? null : String(sessionId), source }),
        signal: controller.signal,
      }).then(async response => {
        if (!response.ok) return;
        const data = await response.json();
        if (!controller.signal.aborted && typeof data.machine_code === "string" && data.machine_code) {
          setMachineLabel(typeof data.machine_name === "string" && data.machine_name !== data.machine_code
            ? `${data.machine_name} (${data.machine_code})` : data.machine_code);
        }
      }).catch(() => {});
    }
    return () => controller.abort();
  }, [sessionId, source]);

  useEffect(() => {
    const controller = new AbortController();
    async function load() {
      setLoading(true);
      setFailed(false);
      setQuestions([]);
      setMessage("");
      try {
        const response = await fetch(`${API_BASE_URL}/api/recommendations`, {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify({ session_id: sessionId === null ? null : String(sessionId), question, answer, source }),
          signal: controller.signal,
        });
        if (!response.ok) throw new Error("추천질문을 불러오지 못했습니다.");
        const data = await response.json();
        if (!Array.isArray(data.questions) || !data.questions.every((item: unknown) => typeof item === "string")) {
          throw new Error("추천질문 응답이 올바르지 않습니다.");
        }
        if (controller.signal.aborted) return;
        setQuestions(data.questions);
        if (typeof data.machine_code === "string" && data.machine_code) {
          setMachineLabel(typeof data.machine_name === "string" && data.machine_name !== data.machine_code
            ? `${data.machine_name} (${data.machine_code})` : data.machine_code);
        }
        setMessage(data.message || "");
      } catch {
        if (controller.signal.aborted) return;
        setFailed(true);
        setMessage("추천질문을 불러오지 못했습니다. 다시 시도해 주세요.");
      } finally {
        if (!controller.signal.aborted) setLoading(false);
      }
    }
    void load();
    return () => controller.abort();
  }, [sessionId, question, answer, source, attempt]);

  if (!visible) return null;

  return (
    <section className={styles.recommendations} aria-label="추천질문" aria-busy={loading}>
      <h3>{question ? "추천 질문" : {
        manual: "장비 매뉴얼에 물어보세요", ladder: "래더 정보에 물어보세요",
        cms_engineer: "현재 장비의 CMS 알람에 물어보세요", cms_manager: "현재 장비의 CMS 현황에 물어보세요",
      }[source]}</h3>
      {source.startsWith("cms_") && <p>테스트 기준일: 2026-08-11{machineLabel ? ` · ${machineLabel}` : ""}</p>}
      {loading && (
        <p className={styles.assistantGenerationStatus} role="status">
          <span className={styles.assistantThinkingSpinner} aria-hidden="true" />
          추천질문 생성 중
        </p>
      )}
      {message && <p role={failed ? "alert" : "status"}>{message}</p>}
      {questions.map(text => (
        <button key={text} type="button" disabled={!canSend} onClick={() => onSelect(text)}>{text}</button>
      ))}
      {questions.length > 0 && !canSend && <p>서비스 설정에서 질문자와 프롬프트를 입력해 주세요.</p>}
      {failed && <button type="button" onClick={() => setAttempt(value => value + 1)}>추천질문 다시 불러오기</button>}
    </section>
  );
}
