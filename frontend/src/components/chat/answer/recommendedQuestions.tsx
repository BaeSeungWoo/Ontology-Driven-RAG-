import { useEffect, useState } from "react";
import { API_BASE_URL } from "@/services/api";
import type { LlmModel } from "@/constants/llmOptions";
import styles from "./answer.module.css";

const WELCOME_QUESTIONS = {
  manual: [
    "작업 시작 전에 확인해야 할 안전 점검 항목을 알려주세요.",
    "장비를 가동하고 정지할 때 지켜야 할 기본 절차를 알려주세요.",
    "장비 사용 중 이상이 발견되면 어떻게 조치해야 하나요?",
  ],
  ladder: [
    "장비가 동작하지 않을 때 어떤 조건과 신호부터 확인해야 하나요?",
    "인터록 때문에 동작이 제한되는지 확인하는 방법을 알려주세요.",
    "센서 입력과 출력 신호를 점검하는 기본 순서를 알려주세요.",
  ],
  electrical: [
    "장비가 동작하지 않을 때 전기도면에서 무엇부터 확인해야 하나요?",
    "모터나 펌프가 작동하지 않을 때 관련 회로를 어떻게 점검하나요?",
    "센서와 제어 신호의 연결 관계를 전기도면으로 확인하고 싶어요.",
  ],
  cms_manager: [
    "현재 확인 가능한 장비 가동 현황을 요약해 주세요.",
    "장비의 비가동 원인을 파악하려면 어떤 지표를 확인해야 하나요?",
    "생산 현황을 점검할 때 우선 확인해야 할 항목을 알려주세요.",
  ],
};

type Props = {
  machineCode?: string;
  llmModel?: LlmModel;
  source?: "electrical" | "manual" | "ladder" | "cms_manager";
  sessionId: number | null;
  question: string;
  answer: string;
  canSend: boolean;
  visible?: boolean;
  welcome?: boolean;
  onSelect: (question: string) => void;
};

export default function RecommendedQuestions({ machineCode, llmModel = "vllm_config", source = "manual", sessionId, question, answer, canSend, visible = true, welcome = false, onSelect }: Props) {
  const [questions, setQuestions] = useState<string[]>([]);
  const [loading, setLoading] = useState(true);
  const [message, setMessage] = useState("");
  const [failed, setFailed] = useState(false);
  const [attempt, setAttempt] = useState(0);
  const [machineLabel, setMachineLabel] = useState("");

  useEffect(() => {
    if (welcome) return;
    const controller = new AbortController();
    setMachineLabel("");
    if (source.startsWith("cms_")) {
      void fetch(`${API_BASE_URL}/api/recommendations/context`, {
        method: "POST", headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ session_id: sessionId === null ? null : String(sessionId), source, llm_model: llmModel, machine_code: machineCode }),
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
  }, [sessionId, source, llmModel, welcome, machineCode]);

  useEffect(() => {
    if (welcome) return;
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
          body: JSON.stringify({ session_id: sessionId === null ? null : String(sessionId), question, answer, source, llm_model: llmModel, machine_code: machineCode }),
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
  }, [sessionId, question, answer, source, attempt, llmModel, welcome, machineCode]);

  if (!visible) return null;
  if (welcome) return (
    <section className={styles.welcomeRecommendations} aria-label="추천질문">
      <div className={styles.welcomeCards}>
        {WELCOME_QUESTIONS[source].map((text, index) => (
          <button key={text} type="button" disabled={!canSend} onClick={() => onSelect(text)}>
            <span className={styles.recommendationNumber} aria-hidden="true">{index + 1}</span>
            <span>{text}</span>
          </button>
        ))}
      </div>
    </section>
  );

  return (
    <section className={styles.recommendations} aria-label="추천질문" aria-busy={loading}>
      <h3>{question ? "추천 질문" : {
        electrical: "전기도면 고장진단 QA · DHF8000 / DHF8000 #2", manual: "장비 매뉴얼에 물어보세요", ladder: "래더 정보에 물어보세요",
        cms_manager: "현재 장비의 CMS 현황에 물어보세요",
      }[source]}</h3>
      {source === "cms_manager" && <p>테스트 기준일: 2026-10-19{machineLabel ? ` · ${machineLabel}` : ""}</p>}
      {loading && (
        <p className={styles.assistantGenerationStatus} role="status">
          <span className={styles.assistantThinkingSpinner} aria-hidden="true" />
          추천질문 생성 중
        </p>
      )}
      {message && <p role={failed ? "alert" : "status"}>{message}</p>}
      {questions.length > 0 && <div className={styles.recommendationList}>
        {questions.map(text => (
          <button key={text} type="button" disabled={!canSend} onClick={() => onSelect(text)}>
            <span>{text}</span>
          </button>
        ))}
      </div>}
      {questions.length > 0 && !canSend && <p>서비스 설정에서 질문자와 프롬프트를 입력해 주세요.</p>}
      {failed && <button type="button" onClick={() => setAttempt(value => value + 1)}>추천질문 다시 불러오기</button>}
    </section>
  );
}
