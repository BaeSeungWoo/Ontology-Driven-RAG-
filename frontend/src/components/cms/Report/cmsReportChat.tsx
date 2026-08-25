"use client";

import { FormEvent, useId, useState } from "react";
import { MessageCircle, X } from "lucide-react";
import { askCmsReport, type CmsChatMessage, type CmsReport } from "@/services/cmsApi";
import styles from "../cms.module.css";

const WELCOME_MESSAGE: CmsChatMessage = {
  role: "assistant",
  content: "현재 전일 리포트의 가동률, 알람 요약, 최다 알람 장비와 최장 알람 이력을 기준으로 답변합니다.",
};

const RECOMMENDED_QUESTIONS = [
  "기준일 계획가동률은 얼마야?",
  "가장 낮은 시간대 가동률은?",
  "총 알람 발생 건수는?",
  "알람이 가장 많이 발생한 장비는?",
  "가장 오래 지속된 알람은?",
];

type CmsReportChatProps = {
  report: CmsReport;
};

export default function CmsReportChat({ report }: CmsReportChatProps) {
  const chatPanelId = useId();
  const [isOpen, setIsOpen] = useState(false);
  const [messages, setMessages] = useState<CmsChatMessage[]>([WELCOME_MESSAGE]);
  const [question, setQuestion] = useState("");
  const [isLoading, setIsLoading] = useState(false);

  const sendQuestion = async (nextQuestion: string) => {
    const trimmedQuestion = nextQuestion.trim();
    if (!trimmedQuestion || isLoading) return;

    const userMessage: CmsChatMessage = { role: "user", content: trimmedQuestion };
    const history = messages.slice(1).slice(-6);
    setMessages((current) => [...current, userMessage]);
    setQuestion("");
    setIsLoading(true);

    try {
      const answer = await askCmsReport(trimmedQuestion, history, report);
      setMessages((current) => [...current, { role: "assistant", content: answer }]);
    } catch (error) {
      setMessages((current) => [
        ...current,
        {
          role: "assistant",
          content: error instanceof Error ? error.message : "답변을 생성하지 못했습니다.",
        },
      ]);
    } finally {
      setIsLoading(false);
    }
  };

  const submitQuestion = async (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    await sendQuestion(question);
  };

  return (
    <div className={styles.reportChat}>
      <button
        type="button"
        className={styles.reportChatLauncher}
        aria-expanded={isOpen}
        aria-controls={chatPanelId}
        aria-label={isOpen ? "리포트 질의 닫기" : "리포트 질의 열기"}
        onClick={() => setIsOpen((open) => !open)}
      >
        {isOpen ? <X aria-hidden="true" /> : <MessageCircle aria-hidden="true" />}
        <span>리포트 질의</span>
      </button>

      {isOpen && (
        <aside id={chatPanelId} className={styles.reportChatPanel} aria-label="CMS 데이터 질의">
          <header>
            <p>CMS DATA CHAT</p>
            <h2>리포트 질의</h2>
            <span>현재 리포트 데이터만 답변합니다.</span>
          </header>
          <div className={styles.reportChatMessages}>
            {messages.length === 1 && (
              <div className={styles.reportChatRecommendations}>
                <span>추천 질문</span>
                {RECOMMENDED_QUESTIONS.map((recommendedQuestion) => (
                  <button
                    key={recommendedQuestion}
                    type="button"
                    onClick={() => sendQuestion(recommendedQuestion)}
                    disabled={isLoading}
                  >
                    {recommendedQuestion}
                  </button>
                ))}
              </div>
            )}
            {messages.map((message, index) => (
              <p key={`${message.role}-${index}`} className={styles[`reportChat_${message.role}`]}>
                {message.content}
              </p>
            ))}
            {isLoading && <p className={styles.reportChat_assistant}>데이터를 확인하고 있습니다.</p>}
          </div>
          <form className={styles.reportChatForm} onSubmit={submitQuestion}>
            <input
              value={question}
              onChange={(event) => setQuestion(event.target.value)}
              placeholder="리포트 데이터를 질문하세요"
              disabled={isLoading}
            />
            <button type="submit" disabled={isLoading || !question.trim()}>전송</button>
          </form>
        </aside>
      )}
    </div>
  );
}
