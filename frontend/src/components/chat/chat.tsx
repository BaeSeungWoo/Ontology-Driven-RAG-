"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { ChartNoAxesCombined, Check, Cpu, HardHat, Info, Wrench } from "lucide-react";
import Answer from "./answer/answer";
import RecommendedQuestions from "./answer/recommendedQuestions";
import RecommendationPopover from "./question/recommendationPopover";
import Citation from "./citation/citation";
import { usePdfDocument } from "./figureExplanationProvider";
import History from "./history/history";
import type { HistoryItem } from "./history/historyCard";
import PromptSetting from "./promptSetting/promptSetting";
import {
  LLM_MODEL_OPTIONS,
  LLM_MODE_OPTIONS,
  type LlmModel,
  type LlmMode,
} from "@/constants/llmOptions";
import { PERSONA_OPTIONS, type PersonaType } from "@/constants/personaOptions";
import Question, { type QuestionPayload } from "./question/question";
import { useChat } from "@/hooks/useChat";
import AppHeader from "@/components/navigation/appHeader";
import {
  type SelectedCitation,
} from "./citation/citationUtils";
import styles from "./chat.module.css";
import personaStyles from "./persona.module.css";

type HistorySessionMeta = Pick<
  HistoryItem,
  "questioner" | "llmModel" | "llmMode" | "promptNo" | "promptName" | "personaType"
>;

const PERSONA_CARDS = {
  operator: { icon: HardHat, description: "장비 조작과 안전 점검을 매뉴얼로 확인하세요.", mode: "rag" },
  maintenance: { icon: Wrench, description: "래더와 신호를 살펴 고장 원인을 찾아보세요.", mode: "ladder" },
  engineer: { icon: Cpu, description: "설비 알람과 기술 자료를 함께 분석하세요.", mode: "cms" },
  manager: { icon: ChartNoAxesCombined, description: "가동 현황과 운영 지표를 한눈에 확인하세요.", mode: "cms" },
} satisfies Record<PersonaType, { icon: typeof HardHat; description: string; mode: LlmMode }>;

export default function Chat() {
  // 내부 state: 화면 접힘/선택 상태
  // 기능/목적: 좌/우 패널, 활성 답변과 선택 참조를 화면 전체에서 공유한다.
  const [isCitationCollapsed, setIsCitationCollapsed] = useState(false);
  const [activeAssistantMessageId, setActiveAssistantMessageId] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<SelectedCitation>(null);
  const handleDocumentOpen = usePdfDocument();

  // 내부 state: 세션/설정 상태
  // 기능/목적: 질문자, 프롬프트, LLM 설정, 선택 세션을 질문 전송과 히스토리에 연결한다.
  const [questioner, setQuestioner] = useState("");
  const [selectedLlmModel, setSelectedLlmModel] = useState<LlmModel>("ollama_config");
  const [selectedLlmMode, setSelectedLlmMode] = useState<LlmMode>("rag");
  const [selectedPersonaType, setSelectedPersonaType] = useState<PersonaType>("operator");
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);
  const [composerEpoch, setComposerEpoch] = useState(0);
  const [isSending, setIsSending] = useState(false);
  const [recommendationsEnabled, setRecommendationsEnabled] = useState(true);
  const [isSettingsOpen, setIsSettingsOpen] = useState(false);
  const settingsAtOpenRef = useRef<{ mode: LlmMode; persona: PersonaType } | null>(null);
  const [recommendationSendError, setRecommendationSendError] = useState("");
  const sendingRef = useRef(false);
  const isSessionResetPendingRef = useRef(false);
  const isHistorySessionSyncingRef = useRef(false);

  useEffect(() => {
    const today = new Intl.DateTimeFormat("sv-SE", {
      timeZone: "Asia/Seoul", year: "numeric", month: "2-digit", day: "2-digit",
    }).format(new Date()).replaceAll("-", "");
    setQuestioner(`${today}-User-01`);
  }, []);

  const { messages, sendQuestion, retryLastAnswer, loadSessionMessages, resetChatState, isLoading, isSessionLoading, error } = useChat({
    selectedSessionId,
    onSessionId: (id) => {
      setSelectedSessionId(id);
      isSessionResetPendingRef.current = false;
    },
    onHistoryRefresh: () => setHistoryRefreshKey((prev) => prev + 1),
  });

  const previousSettingsRef = useRef<{
    questioner: string;
    llmModel: LlmModel;
    llmMode: LlmMode;
    personaType: PersonaType;
  }>({
    questioner: questioner.trim(),
    llmModel: selectedLlmModel,
    llmMode: selectedLlmMode,
    personaType: selectedPersonaType,
  });

  const isPromptRequiredMissing =
    questioner.trim().length === 0;

  // 함수: 세션 초기화/전송
  // 기능/목적: 새 질문 시작과 질문 전송 시 세션 생성 정책을 한곳에서 처리한다.
  // In: QuestionPayload / Out: 메시지 전송, 세션 상태 초기화 또는 갱신
  const resetToNewSession = () => {
    if (sendingRef.current) return;
    setRecommendationSendError("");
    setComposerEpoch(previous => previous + 1);
    setSelectedSessionId(null);
    setActiveAssistantMessageId(null);
    setSelectedCitation(null);
    isSessionResetPendingRef.current = false;
    resetChatState();
  };

  const handleSettingsOpen = () => {
    settingsAtOpenRef.current = { mode: selectedLlmMode, persona: selectedPersonaType };
    setIsSettingsOpen(true);
    setRecommendationsEnabled(false);
  };

  const handleSettingsClose = (applied?: { mode: LlmMode; persona: PersonaType }) => {
    const previous = settingsAtOpenRef.current;
    settingsAtOpenRef.current = null;
    if (previous && applied && (previous.mode !== applied.mode || previous.persona !== applied.persona)
      && (selectedSessionId !== null || messages.length > 0)) {
      window.alert("모드 또는 페르소나가 변경되어 새 질문 화면으로 전환합니다. 기존 대화는 질문 이력에서 다시 확인할 수 있습니다.");
      resetToNewSession();
    }
    setIsSettingsOpen(false);
    setRecommendationsEnabled(true);
  };

  const handleDeleteSession = (sessionId: number) => {
    if (selectedSessionId !== sessionId) return;
    resetToNewSession();
  };

  const handleSendQuestion = async (payload: QuestionPayload) => {
    if (sendingRef.current || isSessionLoading) return false;
    setRecommendationSendError("");
    sendingRef.current = true;
    setIsSending(true);
    try {
      const shouldForceNewSession = isSessionResetPendingRef.current;
      const isSuccess = await sendQuestion({
        ...payload,
        forceNewSession: shouldForceNewSession,
      });

      if (isSuccess && shouldForceNewSession) {
        isSessionResetPendingRef.current = false;
      }
      return isSuccess;
    } finally {
      sendingRef.current = false;
      setIsSending(false);
    }
  };

  const handleRetryAnswer = async () => {
    if (sendingRef.current || isSessionLoading) return;
    sendingRef.current = true;
    setIsSending(true);
    setRecommendationSendError("");
    try {
      await retryLastAnswer({
        llmModel: selectedLlmModel, llmMode: selectedLlmMode, personaType: selectedPersonaType,
      });
    } finally {
      sendingRef.current = false;
      setIsSending(false);
    }
  };

  // 함수: 히스토리 세션 복원
  // 기능/목적: 선택한 히스토리의 메시지와 질문 설정을 현재 화면에 동기화한다.
  // In: sessionId, sessionMeta / Out: 세션 메시지 로드 및 설정 state 갱신
  const handleSelectSession = async (sessionId: number, sessionMeta?: HistorySessionMeta) => {
    if (sendingRef.current) return;
    setRecommendationsEnabled(false);
    setRecommendationSendError("");
    setComposerEpoch(previous => previous + 1);
    isHistorySessionSyncingRef.current = true;
    isSessionResetPendingRef.current = false;
    setActiveAssistantMessageId(null);
    setSelectedCitation(null);
    setSelectedSessionId(sessionId);

    if (sessionMeta?.questioner && sessionMeta.questioner.trim().length > 0) {
      setQuestioner(sessionMeta.questioner);
    }

    if (sessionMeta?.llmModel) {
      const matchedModel = LLM_MODEL_OPTIONS.find((option) => option.value === sessionMeta.llmModel);
      if (matchedModel) setSelectedLlmModel(matchedModel.value);
    }

    if (sessionMeta?.llmMode) {
      // Restore sessions saved before the repair-history mode was renamed.
      const savedMode = sessionMeta.llmMode === "maintenance" ? "repairHistory" : sessionMeta.llmMode;
      const matchedMode = LLM_MODE_OPTIONS.find((option) => option.value === savedMode);
      if (matchedMode) setSelectedLlmMode(matchedMode.value);
    }

    const loaded = await loadSessionMessages(sessionId, sessionMeta?.promptName);
    if (loaded) {
      const lastAnswer = loaded.findLast(message => message.role === "assistant");
      const savedPersona = sessionMeta?.personaType ?? lastAnswer?.metadata?.persona_type;
      const mode = sessionMeta?.llmMode ?? lastAnswer?.llm_mode ?? selectedLlmMode;
      const intent = lastAnswer?.metadata?.intent as { type?: string } | undefined;
      const restoredPersona = PERSONA_OPTIONS.find(option => option.value === savedPersona)?.value
        ?? (mode === "rag" ? "operator" : mode === "ladder" ? "maintenance"
          : mode === "cms" ? (intent?.type === "concept_explanation" ? "manager"
            : intent?.type === "root_cause_analysis" ? "engineer"
            : selectedPersonaType === "manager" ? "manager" : "engineer") : selectedPersonaType);
      isHistorySessionSyncingRef.current = true;
      setSelectedPersonaType(restoredPersona);
      setRecommendationsEnabled(true);
    }
  };

  // 함수: 답변/참조 연동
  // 기능/목적: Answer와 Citation이 같은 assistant 메시지와 chunk를 보도록 맞춘다.
  // In: messageId, chunkIndex / Out: activeAssistantMessageId, selectedCitation 갱신
  const clearReferencePanels = useCallback(() => {
    setSelectedCitation(null);
  }, []);

  const handleAssistantSelect = useCallback(
    (messageId: string) => {
      setActiveAssistantMessageId(messageId);
      clearReferencePanels();
    },
    [clearReferencePanels]
  );

  const handleActiveAssistantChange = useCallback(
    (messageId: string | null) => {
      if (activeAssistantMessageId !== messageId) {
        clearReferencePanels();
      }
      setActiveAssistantMessageId(messageId);
    },
    [activeAssistantMessageId, clearReferencePanels]
  );

  const handleCitationSelect = useCallback((messageId: string, chunkIndex: number) => {
    setActiveAssistantMessageId(messageId);
    setSelectedCitation({ messageId, chunkIndex });
  }, []);

  const handleCitationToggle = useCallback(() => {
    setIsCitationCollapsed((prev) => !prev);
  }, []);

  // 함수: 설정 변경 감지
  // 기능/목적: 기존 세션에서 질문 설정이 바뀌면 다음 전송을 새 세션으로 분기한다.
  // In: 질문자/프롬프트/LLM 설정 / Out: isSessionResetPendingRef 갱신
  useEffect(() => {
    if (isSettingsOpen) return;
    const nextSettings = {
      questioner: questioner.trim(),
      llmModel: selectedLlmModel,
      llmMode: selectedLlmMode,
      personaType: selectedPersonaType,
    };

    const previousSettings = previousSettingsRef.current;
    if (isHistorySessionSyncingRef.current) {
      previousSettingsRef.current = nextSettings;
      isHistorySessionSyncingRef.current = false;
      return;
    }

    const isSettingsChanged =
      previousSettings.questioner !== nextSettings.questioner ||
      previousSettings.llmModel !== nextSettings.llmModel ||
      previousSettings.llmMode !== nextSettings.llmMode ||
      previousSettings.personaType !== nextSettings.personaType;

    if (isSettingsChanged && selectedSessionId !== null) {
      isSessionResetPendingRef.current = true;
    }

    previousSettingsRef.current = nextSettings;
  }, [questioner, selectedLlmModel, selectedLlmMode, selectedPersonaType, selectedSessionId, isSettingsOpen]);

  const isWelcome = messages.length === 0 && selectedSessionId === null && !isSessionLoading;
  const lastUserMessage = messages.findLast(message => message.role === "user");
  const lastAnswerMessage = messages.findLast(message => message.role === "assistant");
  const recommendationSource = selectedLlmMode === "ladder" && selectedPersonaType === "maintenance"
    ? "ladder" : selectedLlmMode === "rag" && selectedPersonaType === "operator" ? "manual"
    : selectedLlmMode === "cms" && selectedPersonaType === "engineer" ? "cms_engineer"
    : selectedLlmMode === "cms" && selectedPersonaType === "manager" ? "cms_manager" : null;
  const prepareRecommendations = (recommendationsEnabled || (isSettingsOpen && messages.length === 0 && selectedSessionId === null)) &&
    !isSending && !isLoading && !isSessionLoading && !error &&
    (selectedLlmModel === "ollama_config" || selectedLlmModel === "vllm_config") && recommendationSource !== null;
  const recommendations = prepareRecommendations && recommendationSource ? (
    <RecommendedQuestions
      key={`${selectedLlmModel}:${recommendationSource}:${selectedSessionId}:${lastAnswerMessage?.message_id ?? "initial"}`}
      llmModel={selectedLlmModel}
      welcome={isWelcome}
      source={recommendationSource}
      visible={recommendationsEnabled}
      sessionId={selectedSessionId}
      question={lastUserMessage?.content ?? ""}
      answer={lastAnswerMessage?.content ?? ""}
      canSend={!isPromptRequiredMissing}
      onSelect={async question => {
        if (isPromptRequiredMissing) return;
        const success = await handleSendQuestion({
          question, questioner,
          llmModel: selectedLlmModel, llmMode: selectedLlmMode, personaType: selectedPersonaType,
        });
        if (!success) setRecommendationSendError("추천질문을 전송하지 못했습니다. 질문 입력창에서 다시 시도해 주세요.");
      }}
    />
  ) : null;

  // render
  return (
    <div className={`${styles.chatPage} tw-chat-page`}>
      <AppHeader>
        <div className={styles.headerSettings} inert={isSending}>
          <PromptSetting
            onOpen={handleSettingsOpen}
            onClose={handleSettingsClose}
            questioner={questioner}
            onQuestionerChange={setQuestioner}
            selectedLlmModel={selectedLlmModel}
            onSelectLlmModel={setSelectedLlmModel}
            selectedLlmMode={selectedLlmMode}
            onSelectLlmMode={setSelectedLlmMode}
            selectedPersonaType={selectedPersonaType}
            onSelectPersonaType={setSelectedPersonaType}
          />
        </div>
      </AppHeader>

      <div
        className={`${styles.chatTypographyScope} tw-chat-layout ${isCitationCollapsed ? "tw-chat-layout-right-collapsed" : ""}`}
      >
        <aside className="tw-chat-left" inert={isSending}>
          <section
            className={styles.chatHistoryPane}
          >
            <History
              selectedSessionId={selectedSessionId}
              onSelectSession={handleSelectSession}
              onStartNewChat={resetToNewSession}
              onDeleteSession={handleDeleteSession}
              onHistoryRefresh={() => setHistoryRefreshKey((prev) => prev + 1)}
              refreshKey={historyRefreshKey}
            />
          </section>

        </aside>

        <main className={`tw-chat-center ${isWelcome ? styles.welcomeCenter : ""}`}>
          {isWelcome ? (
            <>
            <div className={styles.welcomeHero}>
              <Image src="/logo3.png" alt="" width={112} height={112} loading="eager" />
              <p className={styles.welcomeEyebrow}>YOUR KNOWLEDGE, CONNECTED</p>
              <h2>현장의 질문에,<br />근거 있는 답을.</h2>
              <p className={styles.welcomeDescription}>복잡한 매뉴얼부터 설비 문제까지.<br />질문하고, 답변의 근거까지 함께 확인하세요.</p>
            </div>
            <section className={styles.personaPicker} aria-label="페르소나 선택">
              <p className={styles.personaGuide}>질문하기 전에 업무에 맞는 역할을 선택해 주세요. 선택한 역할에 맞춰 답변과 추천질문을 제공합니다.</p>
              <div className={styles.personaCards}>
                {PERSONA_OPTIONS.map(persona => {
                  const card = PERSONA_CARDS[persona.value];
                  const Icon = card.icon;
                  return (
                    <button key={persona.value} type="button" className={`${styles.personaCard} ${personaStyles.theme}`} data-persona={persona.value}
                      aria-pressed={selectedPersonaType === persona.value}
                      disabled={isSending || isLoading}
                      onClick={() => {
                        setSelectedPersonaType(persona.value);
                        setSelectedLlmMode(card.mode);
                        setRecommendationsEnabled(true);
                      }}
                    >
                      <span className={styles.personaCardTop}><Icon size={23} aria-hidden="true" />
                        {selectedPersonaType === persona.value && <Check size={15} aria-hidden="true" />}
                      </span>
                      <strong>{persona.label}</strong>
                      <span className={styles.personaDescription}>{card.description}</span>
                    </button>
                  );
                })}
              </div>
            </section>
            </>
          ) : <section className={styles.chatAnswerPane}>
            <div className={styles.chatAnswerSplit}>
              <div className={styles.chatAnswerMain}>
                <Answer
                  canExplainFigure={selectedLlmModel === "vllm_config"}
                  recommendations={messages.length === 0 ? recommendations : null}
                  messages={messages}
                  selectedCitation={selectedCitation}
                  onAssistantSelect={handleAssistantSelect}
                  onActiveAssistantChange={handleActiveAssistantChange}
                  onCitationSelect={handleCitationSelect}
                  isGenerating={isLoading}
                  onRetry={handleRetryAnswer}
                  showHeader={false}
                />
              </div>
            </div>
          </section>}

          {isWelcome && recommendations}
          <section className={styles.chatQuestionPane}>
            {error && <p role="alert">{error}</p>}
            {recommendationSendError && <p role="alert">{recommendationSendError}</p>}
            <Question
              key={composerEpoch}
              welcome={isWelcome}
              isBusy={isSending || isLoading || isSessionLoading}
              questioner={questioner}
              selectedLlmModel={selectedLlmModel}
              selectedLlmMode={selectedLlmMode}
              selectedPersonaType={selectedPersonaType}
              onSend={handleSendQuestion}
              recommendations={lastAnswerMessage && recommendations ? (
                <RecommendationPopover key={`${recommendationSource}:${selectedSessionId}:${lastAnswerMessage.message_id}`}>
                  {recommendations}
                </RecommendationPopover>
              ) : null}
            />
          </section>
          {isWelcome && <>
            <p className={styles.welcomeNotice}><Info size={17} aria-hidden="true" />AI 답변은 참고 자료와 함께 확인해 주세요.</p>
          </>}
        </main>

        <aside className="tw-chat-right">
          <section
            className={`${styles.chatCitationPane} ${
              isCitationCollapsed ? styles.chatCitationPaneCollapsed : ""
            }`}
          >
            <Citation
              canExplainFigure={selectedLlmModel === "vllm_config"}
              isNewQuestion={isWelcome}
              isCollapsed={isCitationCollapsed}
              onToggle={handleCitationToggle}
              messages={messages}
              isLoading={isLoading}
              activeAssistantMessageId={activeAssistantMessageId}
              selectedCitation={selectedCitation}
              onCitationSelect={handleCitationSelect}
              onDocumentOpen={handleDocumentOpen}
            />
          </section>
        </aside>


      </div>
    </div>
  );
}
