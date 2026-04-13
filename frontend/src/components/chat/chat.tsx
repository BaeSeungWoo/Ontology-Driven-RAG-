"use client";

import { useEffect, useRef, useState } from "react";
import Answer from "./answer/answer";
import Citation from "./citation/citation";
import History from "./history/history";
import PromptSetting from "./promptSetting/promptSetting";
import type { PromptRow } from "@/types/prompt";
import type { LlmModel, LlmMode } from "@/constants/llmOptions";
import Question, { type QuestionPayload } from "./question/question";
import ThemeSwitcher, { type ThemeKey } from "./themeSwitcher/themeSwitcher";
import { useChat } from "@/hooks/useChat";
import styles from "./chat.module.css";

export default function Chat() {
  // =========================
  // state
  // =========================
  const themeKey =
    (process.env.NEXT_PUBLIC_FACTORY_THEME as ThemeKey) || "default";

  const [isCitationCollapsed, setIsCitationCollapsed] = useState(false);
  const [questioner, setQuestioner] = useState("");
  const [selectedPrompt, setSelectedPrompt] = useState<PromptRow | null>(null);
  const [selectedLlmModel, setSelectedLlmModel] = useState<LlmModel>("ollama_config");
  const [selectedLlmMode, setSelectedLlmMode] = useState<LlmMode>("base");

  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);
  const isSessionResetPendingRef = useRef(false);

  const { messages, sendQuestion, loadSessionMessages, resetChatState } = useChat({
    selectedSessionId,
    onSessionId: (id) => setSelectedSessionId(id),
    onHistoryRefresh: () => setHistoryRefreshKey((prev) => prev + 1),
  });

  const previousSettingsRef = useRef<{
    questioner: string;
    promptNo: number | null;
    llmModel: LlmModel;
    llmMode: LlmMode;
  }>({
    questioner: questioner.trim(),
    promptNo: selectedPrompt?.prompt_no ?? null,
    llmModel: selectedLlmModel,
    llmMode: selectedLlmMode,
  });

  const isPromptRequiredMissing =
    questioner.trim().length === 0 || selectedPrompt === null;

  // =========================
  // 함수
  // =========================
  /**
   * 기능: 새 질문 시작 상태로 채팅 컨텍스트를 초기화한다.
   * 목적: 현재 세션 연결과 메시지를 비우고 다음 전송을 새 세션으로 시작하게 한다.
   * In: 새 질문 확정 이벤트
   * Out: selectedSessionId=null, isSessionResetPendingRef=false, chat state 초기화
   */
  const resetToNewSession = () => {
    setSelectedSessionId(null);
    isSessionResetPendingRef.current = false;
    resetChatState();
  };

  /**
   * 기능: 질문 payload를 전송하고 필요 시 새 세션 강제 생성을 적용한다.
   * 목적: 설정 변경 이후 전송 시점에 새 세션으로 분기하는 정책을 일관되게 처리한다.
   * In: payload(QuestionPayload)
   * Out: sendQuestion 호출, 성공 시 pending reset
   */
  const handleSendQuestion = async (payload: QuestionPayload) => {
    const shouldForceNewSession = isSessionResetPendingRef.current;
    const isSuccess = await sendQuestion({
      ...payload,
      forceNewSession: shouldForceNewSession,
    });
    if (isSuccess && shouldForceNewSession) {
      isSessionResetPendingRef.current = false;
    }
  };

  /**
   * 기능: 히스토리에서 선택한 세션을 로드한다.
   * 목적: 선택 세션의 메시지를 복원하고 질문자 입력값을 이력 질문자와 동기화한다.
   * In: sessionId(number), sessionQuestioner(string | undefined)
   * Out: selectedSessionId/questioner/messages 상태 갱신
   */
  const handleSelectSession = async (sessionId: number, sessionQuestioner?: string) => {
    isSessionResetPendingRef.current = false;
    setSelectedSessionId(sessionId);
    if (sessionQuestioner && sessionQuestioner.trim().length > 0) {
      setQuestioner(sessionQuestioner);
    }
    await loadSessionMessages(sessionId);
  };

  // =========================
  // useEffect
  // =========================
  useEffect(() => {
    const nextSettings = {
      questioner: questioner.trim(),
      promptNo: selectedPrompt?.prompt_no ?? null,
      llmModel: selectedLlmModel,
      llmMode: selectedLlmMode,
    };

    const previousSettings = previousSettingsRef.current;
    const isSettingsChanged =
      previousSettings.questioner !== nextSettings.questioner ||
      previousSettings.promptNo !== nextSettings.promptNo ||
      previousSettings.llmModel !== nextSettings.llmModel ||
      previousSettings.llmMode !== nextSettings.llmMode;

    if (isSettingsChanged && selectedSessionId !== null) {
      isSessionResetPendingRef.current = true;
    }

    previousSettingsRef.current = nextSettings;
  }, [questioner, selectedPrompt, selectedLlmModel, selectedLlmMode, selectedSessionId]);

  // =========================
  // render(return)
  // =========================
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
              questioner={questioner}
              selectedPrompt={selectedPrompt}
              selectedLlmModel={selectedLlmModel}
              selectedLlmMode={selectedLlmMode}
              onSend={handleSendQuestion}
            />
          </section>
        </main>

        <aside className="tw-chat-right">
          <section className={styles.chatHistoryPane}>
            <History
              selectedSessionId={selectedSessionId}
              onSelectSession={handleSelectSession}
              onStartNewChat={resetToNewSession}
              refreshKey={historyRefreshKey}
            />
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
              onSelectPrompt={setSelectedPrompt}
              selectedLlmModel={selectedLlmModel}
              onSelectLlmModel={setSelectedLlmModel}
              selectedLlmMode={selectedLlmMode}
              onSelectLlmMode={setSelectedLlmMode}
            />
          </section>
        </aside>
      </div>
    </div>
  );
}
