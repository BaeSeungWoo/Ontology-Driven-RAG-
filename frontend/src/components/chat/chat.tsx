"use client";

import { useState } from "react";
import Answer from "./answer/answer";
import Citation from "./citation/citation";
import PromptSetting from "./promptSetting/promptSetting";
import type { PromptRow } from "@/types/prompt";
import type { LlmModel, LlmMode } from "@/constants/llmOptions";
import Question, { type QuestionPayload } from "./question/question";
import ThemeSwitcher, { type ThemeKey } from "./themeSwitcher/themeSwitcher";
import { useChat } from "@/hooks/useChat";
import styles from "./chat.module.css";

/**
 * 기능: 채팅 페이지 컨테이너
 * 이유: 좌/중/우 패널과 질문 전송 플로우를 한 곳에서 조합하기 위해
 * In: 사용자 입력(질문자/프롬프트/모델/모드/질문 텍스트)
 * Out: Answer 타임라인 렌더, sendQuestion 호출, 패널 UI 상태
 */
export default function Chat() {
  const themeKey =
    (process.env.NEXT_PUBLIC_FACTORY_THEME as ThemeKey) || "default";

  const [isCitationCollapsed, setIsCitationCollapsed] = useState(false);
  const [questioner, setQuestioner] = useState("");
  const [selectedPrompt, setSelectedPrompt] = useState<PromptRow | null>(null);
  const [selectedLlmModel, setSelectedLlmModel] = useState<LlmModel>("ollama_config");
  const [selectedLlmMode, setSelectedLlmMode] = useState<LlmMode>("base");

  const { messages, sendQuestion } = useChat();

  const isPromptRequiredMissing =
    questioner.trim().length === 0 || selectedPrompt === null;

  /**
   * 기능: Question payload와 우측 설정 패널 메타를 합쳐 전송
   * 이유: 질문 버블 좌측 메타(질문자/프롬프트명)를 함께 표시하기 위해
   * In: QuestionPayload + questioner + selectedPrompt
   * Out: useChat.sendQuestion 호출
   */
  const handleSendQuestion = async (payload: QuestionPayload) => {
    await sendQuestion({
      question: payload.question,
      llmModel: payload.llmModel,
      llmMode: payload.llmMode,
      questioner,
      promptName: selectedPrompt?.prompt_name ?? null,
    });
  };

  return (
    <div className="tw-chat-page">
      <div className="tw-chat-toolbar">
        <h1 className="tw-chat-title">
          Ontology-Driven-RAG
        </h1>
        <ThemeSwitcher initialTheme={themeKey} />
      </div>

      <div
        className={`${styles.chatTypographyScope} tw-chat-layout ${
          isCitationCollapsed ? "tw-chat-layout-collapsed" : ""
        }`}
      >
        <aside className="tw-chat-left">
          <section
            className={`${styles.chatCitationPane} ${
              isCitationCollapsed ? styles.chatCitationPaneCollapsed : ""
            }`}
          >
            <Citation
              isCollapsed={isCitationCollapsed}
              onToggle={() => setIsCitationCollapsed((prev) => !prev)}
            />
          </section>
        </aside>

        <main className="tw-chat-center">
          <section className={styles.chatAnswerPane}>
            <Answer messages={messages} />
          </section>
          <section className={styles.chatQuestionPane}>
            <Question
              selectedLlmModel={selectedLlmModel}
              selectedLlmMode={selectedLlmMode}
              onSend={handleSendQuestion}
            />
          </section>
        </main>

        <aside className="tw-chat-right">
          <section className={styles.chatHistoryPane}>
            {/* <History ... /> */}
          </section>
          <section
            className={`${styles.chatPromptSettingPane} ${
              isPromptRequiredMissing ? styles.chatPromptSettingPaneRequired : ""
            }`}
          >
            <PromptSetting
              questioner={questioner}
              onQuestionerChange={setQuestioner}
              selectedPrompt={selectedPrompt}
              selectedLlmModel={selectedLlmModel}
              onSelectLlmModel={setSelectedLlmModel}
              selectedLlmMode={selectedLlmMode}
              onSelectLlmMode={setSelectedLlmMode}
              onSelectPrompt={setSelectedPrompt}
            />
          </section>
        </aside>
      </div>
    </div>
  );
}
