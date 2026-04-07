"use client";

import { useEffect, useState } from "react";
import Answer from "./answer/answer";
import Citation from "./citation/citation";
import History from "./history/history";
import PromptSetting from "./promptSetting/promptSetting";
import type { LlmModel, PromptRow } from "@/types/prompt";
import Question, { type QuestionPayload } from "./question/question";
import ThemeSwitcher, { type ThemeKey } from "./themeSwitcher/themeSwitcher";
import { useChat } from "@/hooks/useChat";
import styles from "./chat.module.css";

export default function Chat() {
  // ============================================================
  // 상태(State)
  // - 화면 표시 상태와 사용자 입력 상태를 관리한다.
  // ============================================================

  // In: 환경변수 NEXT_PUBLIC_FACTORY_THEME
  // Out: 화면 테마 키
  const themeKey =
    (process.env.NEXT_PUBLIC_FACTORY_THEME as ThemeKey) || "default";

  // In: 사용자 토글 클릭
  // Out: 출처 패널 접힘/펼침 상태
  const [isCitationCollapsed, setIsCitationCollapsed] = useState(false);

  // In: 프롬프트 설정 패널 입력값
  // Out: 질문자 이름
  const [questioner, setQuestioner] = useState("");

  // In: 프롬프트 선택 이벤트
  // Out: 현재 선택 프롬프트
  const [selectedPrompt, setSelectedPrompt] = useState<PromptRow | null>(null);

  // In: 모델 선택 이벤트
  // Out: 현재 선택 LLM
  const [selectedLlm, setSelectedLlm] = useState<LlmModel>("ollama");

  /**
   * 채팅 도메인 상태/함수 훅
   * In: 없음 (훅 내부에서 API 상태 관리)
   * Out:
   * - chats: 이력 목록
   * - messages: 현재 채팅 메시지
   * - currentChatId: 선택된 채팅 ID
   * - loadChats/selectChat/sendQuestion/resetCurrentChat: 도메인 액션
   */
  const {
    chats,
    messages,
    currentChatId,
    loadChats,
    selectChat,
    sendQuestion,
    resetCurrentChat,
  } = useChat();

  // In: questioner, selectedPrompt
  // Out: 필수값 미입력 여부 (설정 패널 강조용)
  const isPromptRequiredMissing =
    questioner.trim().length === 0 || selectedPrompt === null;

  // ============================================================
  // 함수(Functions)
  // - 사용자 이벤트를 받아 useChat 액션으로 위임한다.
  // ============================================================

  /**
   * 초기 이력 로드
   * In: 컴포넌트 마운트
   * Out: chats 상태 갱신
   */
  useEffect(() => {
    void loadChats();
  }, [loadChats]);

  /**
   * 새 질문 시작
   * In: History의 "새 질문" 버튼 클릭
   * Out: currentChatId 해제, 메시지 초기화
   */
  const handleNewChat = () => {
    resetCurrentChat();
  };

  /**
   * 질문 전송
   * In: QuestionPayload(question, questioner, promptNo, promptName, promptTxt, llmModel)
   * Out:
   * - chat_id // 새채팅인 경우 new chat_id를 반환
   * - user 메시지
   * - assistant 메시지 스트리밍 형식으로 return
   */
  const handleSendQuestion = async (payload: QuestionPayload) => {
    console.log('질문전송', payload)
    await sendQuestion({
      question: payload.question,
      // questioner: payload.questioner,
      // promptNo: payload.promptNo,
      // promptName: payload.promptName,
      // promptTxt: payload.promptTxt,
      llmModel: payload.llmModel,
      // selectedChatId: currentChatId,
    });
  };

  /**
   * 이력 채팅 선택
   * In: HistoryCard 클릭(chatId)
   * Out: currentChatId 변경 + 해당 메시지 로드
   */
  const handleSelectChat = (chatId: number) => {
    void selectChat(chatId);
  };

  // ============================================================
  // 최종 렌더(Render)
  // - 좌: 출처, 중: 답변/질문, 우: 이력/프롬프트 설정
  // ============================================================

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
              // selectedPrompt={selectedPrompt}
              selectedLlm={selectedLlm}
              onSend={handleSendQuestion}
            />
          </section>
        </main>

        <aside className="tw-chat-right">
          <section className={styles.chatHistoryPane}>
            <History
              onNewChat={handleNewChat}
              hasMessages={currentChatId !== null || messages.length > 0}
              chats={chats}
              selectedChatId={currentChatId}
              onSelectChat={handleSelectChat}
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
              selectedLlm={selectedLlm}
              onSelectLlm={setSelectedLlm}
              onSelectPrompt={setSelectedPrompt}
            />
          </section>
        </aside>
      </div>
    </div>
  );
}
