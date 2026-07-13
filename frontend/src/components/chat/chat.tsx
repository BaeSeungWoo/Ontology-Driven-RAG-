"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { MessageSquareMore } from "lucide-react";
import Answer from "./answer/answer";
import AssetPanel from "./assetPanel";
import Citation from "./citation/citation";
import PdfDocumentViewer from "./citation/pdfDocumentViewer";
import History from "./history/history";
import type { HistoryItem } from "./history/historyCard";
import PromptSetting from "./promptSetting/promptSetting";
import type { PromptRow } from "@/types/prompt";
import {
  LLM_MODEL_OPTIONS,
  LLM_MODE_OPTIONS,
  type LlmModel,
  type LlmMode,
} from "@/constants/llmOptions";
import type { PersonaType } from "@/constants/personaOptions";
import Question, { type QuestionPayload } from "./question/question";
import ThemeSwitcher, { type ThemeKey } from "./themeSwitcher/themeSwitcher";
import { useChat } from "@/hooks/useChat";
import PageTabs from "@/components/navigation/pageTabs";
import { resolveDocument } from "@/services/documentApi";
import type { ResolvedDocument } from "@/types/chatApi";
import {
  getCitationDocumentRequest,
  getLatestAssistantMessage,
  type CitationDocumentRequest,
  type SelectedCitation,
} from "./citation/citationUtils";
import styles from "./chat.module.css";

const ENABLE_DEV_ASSET_PANEL = true;

type HistorySessionMeta = Pick<
  HistoryItem,
  "questioner" | "llmModel" | "llmMode" | "promptNo" | "promptName"
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
  // 기능/목적: 좌/우 패널, 이미지/표 패널, 활성 답변과 선택 참조를 화면 전체에서 공유한다.
  const [isCitationCollapsed, setIsCitationCollapsed] = useState(false);
  const [isAssetPanelCollapsed, setIsAssetPanelCollapsed] = useState(false);
  const [isRightPanelCollapsed, setIsRightPanelCollapsed] = useState(false);
  const [activeAssistantMessageId, setActiveAssistantMessageId] = useState<string | null>(null);
  const [selectedCitation, setSelectedCitation] = useState<SelectedCitation>(null);
  const [activePdfDocument, setActivePdfDocument] = useState<ActivePdfDocument>(null);
  const [isPdfDocumentUpdating, setIsPdfDocumentUpdating] = useState(false);

  // 내부 state: 세션/설정 상태
  // 기능/목적: 질문자, 프롬프트, LLM 설정, 선택 세션을 질문 전송과 히스토리에 연결한다.
  const [questioner, setQuestioner] = useState("");
  const [selectedPrompt, setSelectedPrompt] = useState<PromptRow | null>(null);
  const [selectedLlmModel, setSelectedLlmModel] = useState<LlmModel>("ollama_config");
  const [selectedLlmMode, setSelectedLlmMode] = useState<LlmMode>("base");
  const [selectedPersonaType, setSelectedPersonaType] = useState<PersonaType>("operator");
  const [selectedSessionId, setSelectedSessionId] = useState<number | null>(null);
  const [historyRefreshKey, setHistoryRefreshKey] = useState(0);
  const isSessionResetPendingRef = useRef(false);
  const isHistorySessionSyncingRef = useRef(false);
  const lastSyncedDocumentKeyRef = useRef<string | null>(null);

  const { messages, sendQuestion, loadSessionMessages, resetChatState, isLoading } = useChat({
    selectedSessionId,
    onSessionId: (id) => setSelectedSessionId(id),
    onHistoryRefresh: () => setHistoryRefreshKey((prev) => prev + 1),
  });

  const latestAssistantMessage = getLatestAssistantMessage(messages);
  const activeAssistantMessage = useMemo(() => {
    if (!activeAssistantMessageId) return latestAssistantMessage;
    return (
      messages.find(
        (message) =>
          message.role === "assistant" &&
          String(message.message_id) === activeAssistantMessageId
      ) ?? latestAssistantMessage
    );
  }, [activeAssistantMessageId, latestAssistantMessage, messages]);
  const selectedDocumentRequest = useMemo(
    () => getCitationDocumentRequest(messages, selectedCitation, activeAssistantMessageId),
    [activeAssistantMessageId, messages, selectedCitation]
  );

  const previousSettingsRef = useRef<{
    questioner: string;
    promptNo: number | null;
    llmModel: LlmModel;
    llmMode: LlmMode;
    personaType: PersonaType;
  }>({
    questioner: questioner.trim(),
    promptNo: selectedPrompt?.prompt_no ?? null,
    llmModel: selectedLlmModel,
    llmMode: selectedLlmMode,
    personaType: selectedPersonaType,
  });

  const isPromptRequiredMissing =
    questioner.trim().length === 0 || selectedPrompt === null;

  // 함수: 세션 초기화/전송
  // 기능/목적: 새 질문 시작과 질문 전송 시 세션 생성 정책을 한곳에서 처리한다.
  // In: QuestionPayload / Out: 메시지 전송, 세션 상태 초기화 또는 갱신
  const resetToNewSession = () => {
    setSelectedSessionId(null);
    setActiveAssistantMessageId(null);
    setSelectedCitation(null);
    setActivePdfDocument(null);
    setIsPdfDocumentUpdating(false);
    lastSyncedDocumentKeyRef.current = null;
    isSessionResetPendingRef.current = false;
    resetChatState();
  };

  const handleDeleteSession = (sessionId: number) => {
    if (selectedSessionId !== sessionId) return;
    resetToNewSession();
  };

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

  // 함수: 히스토리 세션 복원
  // 기능/목적: 선택한 히스토리의 메시지와 질문 설정을 현재 화면에 동기화한다.
  // In: sessionId, sessionMeta / Out: 세션 메시지 로드 및 설정 state 갱신
  const handleSelectSession = async (sessionId: number, sessionMeta?: HistorySessionMeta) => {
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

    const promptNo = sessionMeta?.promptNo;
    if (promptNo !== null && promptNo !== undefined) {
      setSelectedPrompt((prev) => {
        if (prev?.prompt_no === promptNo) return prev;
        return {
          prompt_no: promptNo,
          prompt_name: sessionMeta?.promptName ?? prev?.prompt_name ?? "선택된 프롬프트",
          prompt_txt: prev?.prompt_txt ?? "",
          create_user: prev?.create_user ?? "",
        };
      });
    }

    await loadSessionMessages(sessionId);
  };

  // 함수: 답변/참조 연동
  // 기능/목적: Answer, Citation, 이미지/표 패널이 같은 assistant 메시지와 chunk를 보도록 맞춘다.
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
    setIsCitationCollapsed(true);
    setIsRightPanelCollapsed(true);

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
    const nextSettings = {
      questioner: questioner.trim(),
      promptNo: selectedPrompt?.prompt_no ?? null,
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
      previousSettings.promptNo !== nextSettings.promptNo ||
      previousSettings.llmModel !== nextSettings.llmModel ||
      previousSettings.llmMode !== nextSettings.llmMode ||
      previousSettings.personaType !== nextSettings.personaType;

    if (isSettingsChanged && selectedSessionId !== null) {
      isSessionResetPendingRef.current = true;
    }

    previousSettingsRef.current = nextSettings;
  }, [questioner, selectedPrompt, selectedLlmModel, selectedLlmMode, selectedPersonaType, selectedSessionId]);

  // render
  return (
    <div className="tw-chat-page">
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
        } ${activePdfDocument ? "tw-chat-layout-pdf-open" : ""}`}
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
            />
          </section>
        </aside>

        {activePdfDocument ? (
          <aside className={styles.chatPdfPane}>
            <PdfDocumentViewer
              document={activePdfDocument.document}
              pageLabel={activePdfDocument.pageLabel}
              chunkText={activePdfDocument.chunkText}
              referenceLabel={activePdfDocument.referenceLabel}
              onClose={() => {
                setActivePdfDocument(null);
                setIsPdfDocumentUpdating(false);
                lastSyncedDocumentKeyRef.current = null;
              }}
              variant="panel"
              isUpdating={isPdfDocumentUpdating}
            />
          </aside>
        ) : null}

        <main className="tw-chat-center">
          <section className={styles.chatAnswerPane}>
            {ENABLE_DEV_ASSET_PANEL ? (
              <div
                className={`${styles.chatAnswerSplit} ${
                  isAssetPanelCollapsed ? styles.chatAnswerSplitAssetCollapsed : ""
                }`}
              >
                <div className={styles.chatAnswerSplitHeader}>
                  <div className={styles.sectionTitleGroup}>
                    <h2 className="pane-title">답변</h2>
                    <MessageSquareMore className={styles.sectionTitleIcon} aria-hidden="true" />
                  </div>
                </div>
                <div className={styles.chatAnswerMain}>
                  <Answer
                    messages={messages}
                    selectedCitation={selectedCitation}
                    onAssistantSelect={handleAssistantSelect}
                    onActiveAssistantChange={handleActiveAssistantChange}
                    onCitationSelect={handleCitationSelect}
                    isGenerating={isLoading}
                    showHeader={false}
                  />
                </div>
                <AssetPanel
                  key={activeAssistantMessage?.message_id ?? "empty"}
                  activeAssistantMessage={activeAssistantMessage}
                  selectedCitation={selectedCitation}
                  isLoading={isLoading}
                  onCitationSelect={handleCitationSelect}
                  isCollapsed={isAssetPanelCollapsed}
                  onToggle={() => setIsAssetPanelCollapsed((prev) => !prev)}
                />
              </div>
            ) : (
              <Answer
                messages={messages}
                selectedCitation={selectedCitation}
                onAssistantSelect={handleAssistantSelect}
                onActiveAssistantChange={handleActiveAssistantChange}
                onCitationSelect={handleCitationSelect}
                isGenerating={isLoading}
              />
            )}
          </section>

          <section className={styles.chatQuestionPane}>
            <Question
              questioner={questioner}
              selectedPrompt={selectedPrompt}
              selectedLlmModel={selectedLlmModel}
              selectedLlmMode={selectedLlmMode}
              selectedPersonaType={selectedPersonaType}
              onSend={handleSendQuestion}
            />
          </section>
        </main>

        <aside className="tw-chat-right">
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
                questioner={questioner}
                onQuestionerChange={setQuestioner}
                selectedPrompt={selectedPrompt}
                onSelectPrompt={setSelectedPrompt}
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
