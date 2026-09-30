"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import Answer from "./answer/answer";
import RecommendedQuestions from "./answer/recommendedQuestions";
import RecommendationPopover from "./question/recommendationPopover";
import Citation from "./citation/citation";
import PdfDocumentViewer from "./citation/pdfDocumentViewer";
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
import ThemeSwitcher, { type ThemeKey } from "./themeSwitcher/themeSwitcher";
import { useChat } from "@/hooks/useChat";
import PageTabs from "@/components/navigation/pageTabs";
import { resolveDocument } from "@/services/documentApi";
import type { ResolvedDocument } from "@/types/chatApi";
import {
  getCitationDocumentRequest,
  type CitationDocumentRequest,
  type SelectedCitation,
} from "./citation/citationUtils";
import styles from "./chat.module.css";

type HistorySessionMeta = Pick<
  HistoryItem,
  "questioner" | "llmModel" | "llmMode" | "promptNo" | "promptName" | "personaType"
>;

type ActivePdfDocument = {
  documentKey: string;
  document: ResolvedDocument;
  pageLabel: string | null;
  chunkText: string;
  referenceLabel: string;
} | null;

export default function Chat() {
  const themeKey =
    (process.env.NEXT_PUBLIC_FACTORY_THEME as ThemeKey) || "default";

  // 내부 state: 화면 접힘/선택 상태
  // 기능/목적: 좌/우 패널, 활성 답변과 선택 참조를 화면 전체에서 공유한다.
  const [isCitationCollapsed, setIsCitationCollapsed] = useState(false);
  const [isRightPanelCollapsed, setIsRightPanelCollapsed] = useState(false);
  const [activeAssistantMessageId, setActiveAssistantMessageId] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<SelectedCitation>(null);
  const [activePdfDocument, setActivePdfDocument] = useState<ActivePdfDocument>(null);
  const [isPdfDocumentUpdating, setIsPdfDocumentUpdating] = useState(false);

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
  const lastSyncedDocumentKeyRef = useRef<string | null>(null);

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

  const selectedDocumentRequest = useMemo(
    () => getCitationDocumentRequest(messages, selectedCitation, activeAssistantMessageId),
    [activeAssistantMessageId, messages, selectedCitation]
  );

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
    setActivePdfDocument(null);
    setIsPdfDocumentUpdating(false);
    lastSyncedDocumentKeyRef.current = null;
    isSessionResetPendingRef.current = false;
    resetChatState();
  };

  const handleSettingsOpen = () => {
    settingsAtOpenRef.current = { mode: selectedLlmMode, persona: selectedPersonaType };
    setIsSettingsOpen(true);
    setRecommendationsEnabled(false);
  };

  const handleSettingsClose = () => {
    const previous = settingsAtOpenRef.current;
    settingsAtOpenRef.current = null;
    if (previous && (previous.mode !== selectedLlmMode || previous.persona !== selectedPersonaType)
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
    setActivePdfDocument(null);
    setIsPdfDocumentUpdating(false);
    lastSyncedDocumentKeyRef.current = null;
    setSelectedSessionId(sessionId);

    if (sessionMeta?.questioner && sessionMeta.questioner.trim().length > 0) {
      setQuestioner(sessionMeta.questioner);
    }

    if (sessionMeta?.llmModel) {
      const matchedModel = LLM_MODEL_OPTIONS.find((option) => option.value === sessionMeta.llmModel);
      if (matchedModel) setSelectedLlmModel(matchedModel.value);
    }

    if (sessionMeta?.llmMode) {
      const matchedMode = LLM_MODE_OPTIONS.find((option) => option.value === sessionMeta.llmMode);
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

  const handleDocumentOpen = useCallback(async (documentRequest: CitationDocumentRequest) => {
    lastSyncedDocumentKeyRef.current = documentRequest.documentKey;
    setIsPdfDocumentUpdating(true);

    try {
      const document = await resolveDocument(documentRequest.sourceDocName, documentRequest.pageRange);
      setActivePdfDocument({
        documentKey: documentRequest.documentKey,
        document,
        pageLabel: documentRequest.pageLabel,
        chunkText: documentRequest.chunkText,
        referenceLabel: documentRequest.referenceLabel,
      });
    } finally {
      setIsPdfDocumentUpdating(false);
    }
  }, []);

  const handlePdfDocumentClose = useCallback(() => {
    setActivePdfDocument(null);
    setIsPdfDocumentUpdating(false);
    lastSyncedDocumentKeyRef.current = null;
  }, []);

  useEffect(() => {
    if (!activePdfDocument || !selectedDocumentRequest) return;
    if (lastSyncedDocumentKeyRef.current === selectedDocumentRequest.documentKey) return;

    let isCurrent = true;
    lastSyncedDocumentKeyRef.current = selectedDocumentRequest.documentKey;
    setIsPdfDocumentUpdating(true);

    resolveDocument(selectedDocumentRequest.sourceDocName, selectedDocumentRequest.pageRange)
      .then((document) => {
        if (!isCurrent) return;
        setActivePdfDocument({
          documentKey: selectedDocumentRequest.documentKey,
          document,
          pageLabel: selectedDocumentRequest.pageLabel,
          chunkText: selectedDocumentRequest.chunkText,
          referenceLabel: selectedDocumentRequest.referenceLabel,
        });
      })
      .catch(() => {
        if (isCurrent) setIsPdfDocumentUpdating(false);
      })
      .finally(() => {
        if (isCurrent) setIsPdfDocumentUpdating(false);
      });

    return () => {
      isCurrent = false;
    };
  }, [activePdfDocument, selectedDocumentRequest]);

  const handleCitationToggle = useCallback(() => {
    setActivePdfDocument(null);
    setIsPdfDocumentUpdating(false);
    lastSyncedDocumentKeyRef.current = null;
    setIsCitationCollapsed((prev) => !prev);
  }, []);

  const handleRightPanelToggle = useCallback(() => {
    setActivePdfDocument(null);
    setIsPdfDocumentUpdating(false);
    lastSyncedDocumentKeyRef.current = null;
    setIsRightPanelCollapsed((prev) => !prev);
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

  const lastUserMessage = messages.findLast(message => message.role === "user");
  const lastAnswerMessage = messages.findLast(message => message.role === "assistant");
  const recommendationSource = selectedLlmMode === "ladder" && selectedPersonaType === "maintenance"
    ? "ladder" : selectedLlmMode === "rag" && selectedPersonaType === "operator" ? "manual"
    : selectedLlmMode === "cms" && selectedPersonaType === "engineer" ? "cms_engineer"
    : selectedLlmMode === "cms" && selectedPersonaType === "manager" ? "cms_manager" : null;
  const prepareRecommendations = (recommendationsEnabled || (isSettingsOpen && messages.length === 0 && selectedSessionId === null)) &&
    !isSending && !isLoading && !isSessionLoading && !error &&
    selectedLlmModel === "ollama_config" && recommendationSource !== null;
  const recommendations = prepareRecommendations && recommendationSource ? (
    <RecommendedQuestions
      key={`${recommendationSource}:${selectedSessionId}:${lastAnswerMessage?.message_id ?? "initial"}`}
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
      <div className="tw-chat-toolbar">
        <div className={styles.chatToolbarLeft}>
          <h1 className="tw-chat-title">Ontology-Driven-RAG</h1>
          <PageTabs />
        </div>
        <ThemeSwitcher initialTheme={themeKey} />
      </div>

      <div
        className={`${styles.chatTypographyScope} tw-chat-layout ${
          isCitationCollapsed ? "tw-chat-layout-collapsed" : ""
        } ${isRightPanelCollapsed ? "tw-chat-layout-right-collapsed" : ""} ${
          isCitationCollapsed && isRightPanelCollapsed ? "tw-chat-layout-both-collapsed" : ""
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
              onToggle={handleCitationToggle}
              messages={messages}
              isLoading={isLoading}
              activeAssistantMessageId={activeAssistantMessageId}
              selectedCitation={selectedCitation}
              onCitationSelect={handleCitationSelect}
              onDocumentOpen={handleDocumentOpen}
              onDetailClose={handlePdfDocumentClose}
              documentOverlay={
                activePdfDocument ? (
                  <PdfDocumentViewer
                    document={activePdfDocument.document}
                    pageLabel={activePdfDocument.pageLabel}
                    chunkText={activePdfDocument.chunkText}
                    referenceLabel={activePdfDocument.referenceLabel}
                    onClose={handlePdfDocumentClose}
                    variant="panel"
                    isUpdating={isPdfDocumentUpdating}
                  />
                ) : null
              }
            />
          </section>
        </aside>

        <main className="tw-chat-center">
          <section className={styles.chatAnswerPane}>
            <div className={styles.chatAnswerSplit}>
              <div className={styles.chatAnswerSplitHeader}>
                <div className={styles.sectionTitleGroup}>
                  <h2 className="pane-title">답변</h2>
                </div>
              </div>
              <div className={styles.chatAnswerMain}>
                <Answer
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
          </section>

          <section className={styles.chatQuestionPane}>
            {error && <p role="alert">{error}</p>}
            {recommendationSendError && <p role="alert">{recommendationSendError}</p>}
            <Question
              key={composerEpoch}
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
        </main>

        <aside className="tw-chat-right" inert={isSending}>
          <section
            className={`${styles.chatHistoryPane} ${
              isRightPanelCollapsed ? styles.chatHistoryPaneCollapsed : ""
            }`}
          >
            <History
              selectedSessionId={selectedSessionId}
              onSelectSession={handleSelectSession}
              onStartNewChat={resetToNewSession}
              onDeleteSession={handleDeleteSession}
              onHistoryRefresh={() => setHistoryRefreshKey((prev) => prev + 1)}
              refreshKey={historyRefreshKey}
              isCollapsed={isRightPanelCollapsed}
              onToggleCollapse={handleRightPanelToggle}
            />
          </section>

          {!isRightPanelCollapsed ? (
            <section
              className={`${styles.chatPromptSettingPane} ${
                isPromptRequiredMissing ? styles.chatPromptSettingPaneRequired : ""
              }`}
            >
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
            </section>
          ) : null}
        </aside>
      </div>
    </div>
  );
}
