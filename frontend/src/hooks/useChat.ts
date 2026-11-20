import { useEffect, useRef, useState, useSyncExternalStore } from "react";
import { startAnswer, stopAnswer, watchAnswer, createSession, getMessages } from "@/services/chatApi";
import { factoryHeaders } from "@/services/api";
import type { LlmModel, LlmMode } from "@/constants/llmOptions";
import type { PersonaType } from "@/constants/personaOptions";
import type { MessageItem, ResolvedDocument } from "@/types/chatApi";

type UseChatParams = {
  selectedSessionId: number | null;
  onSessionId: (id: number) => void;
  factoryId?: string;
  onDocument?: (document: ResolvedDocument) => void;
  selectedCitation?: { message_id: number; chunk_index: number };
};

export type SendQuestionParams = {
  machineCode?: string;
  question: string;
  questioner: string;
  llmModel: LlmModel;
  llmMode: LlmMode;
  personaType: PersonaType;
  forceNewSession?: boolean;
};

type Conversation = {
  stop?: () => Promise<void>;
  messages: MessageItem[];
  busy: boolean;
  restoreMemory: boolean;
  error: string | null;
};

function emptyConversation(): Conversation {
  return { messages: [], busy: false, restoreMemory: false, error: null };
}

// Keep in-flight streams reachable if the chat page is opened again in this tab.
const pending = new Map<number, Conversation>();
const unreadKey = "chat.unreadAnswers";
function loadUnreadAnswers(): Map<number, number> {
  try {
    return new Map(JSON.parse(window.sessionStorage.getItem(unreadKey) ?? "[]"));
  } catch {
    return new Map();
  }
}
const unreadAnswers = typeof window === "undefined" ? new Map<number, number>() : loadUnreadAnswers();
function saveUnreadAnswers() {
  try {
    window.sessionStorage.setItem(unreadKey, JSON.stringify([...unreadAnswers]));
  } catch { /* Keep the indicators in memory when storage is unavailable. */ }
}
function markAnswerRead(sessionId: number, messageId: number) {
  if (unreadAnswers.get(sessionId) !== messageId) return;
  unreadAnswers.delete(sessionId);
  saveUnreadAnswers();
  publish();
}
const listeners = new Set<() => void>();
let revision = 0;
let historyRevision = 0;
function publish() {
  revision++;
  listeners.forEach(listener => listener());
}
function subscribe(listener: () => void) {
  listeners.add(listener);
  return () => { listeners.delete(listener); };
}
const snapshot = () => revision;
const serverSnapshot = () => 0;

export const useChat = ({ selectedSessionId, onSessionId, onDocument, selectedCitation, factoryId = factoryHeaders()["X-Factory-Id"] }: UseChatParams) => {
  useSyncExternalStore(subscribe, snapshot, serverSnapshot);
  const view = useRef<Conversation>(emptyConversation());
  const [isSessionLoading, setIsSessionLoading] = useState(false);

  const viewEpoch = useRef(0);
  useEffect(() => () => { viewEpoch.current++; }, [factoryId]);

  const resetChatState = () => {
    viewEpoch.current++;
    view.current = emptyConversation();
    setIsSessionLoading(false);
    publish();
  };

  const loadSessionMessages = async (sessionId: number, promptName?: string | null) => {
    viewEpoch.current++;
    const running = pending.get(sessionId);
    const conversation = running ?? emptyConversation();
    view.current = conversation;
    setIsSessionLoading(!running);
    publish();
    if (running) return running.messages;
    try {
      const rows = await getMessages(sessionId);
      if (view.current !== conversation) return false;
      conversation.messages = rows.map(message => ({ ...message, prompt_name: message.prompt_name ?? promptName }));
      conversation.restoreMemory = true;
      const last = rows.at(-1);
      if (last?.metadata?.generation_status === "running") {
        void observeAnswer(conversation, sessionId, last.message_id, String(last.metadata.generation_id));
      }
      return rows;
    } catch (err) {
      if (view.current !== conversation) return false;
      conversation.error = err instanceof Error ? err.message : "세션 메시지를 불러오지 못했습니다.";
      return false;
    } finally {
      if (view.current === conversation) setIsSessionLoading(false);
      publish();
    }
  };

  function finish(conversation: Conversation, sessionId: number | null) {
    conversation.busy = false;
    if (sessionId !== null && pending.get(sessionId) === conversation) pending.delete(sessionId);
    publish();
  }

  /**
   * 기능: 질문 전송, 세션 생성, 메시지 저장, 스트리밍 응답 반영을 한 번에 처리한다.
   * 목적: 채팅 전송 플로우를 훅 내부에서 일관되게 수행한다.
   * In: question/questioner/llmModel/llmMode/forceNewSession
   * Out: 성공 여부(boolean), messages/isLoading/error/session 상태 반영
   */
  const sendQuestion = async ({
    machineCode,
    question,
    questioner,
    llmModel,
    llmMode,
    personaType,
    forceNewSession = false,
  }: SendQuestionParams) => {
    const epoch = viewEpoch.current;
    const normalizedQuestion = question.trim();
    if (!normalizedQuestion) return false;

    const normalizedQuestioner = questioner.trim();
    if (!normalizedQuestioner || view.current.busy || isSessionLoading) return false;
    const conversation = forceNewSession ? emptyConversation() : view.current;
    view.current = conversation;
    conversation.busy = true;
    conversation.error = null;
    let sessionId = forceNewSession ? null : selectedSessionId;
    publish();

    if (sessionId === null) {
      try {
        const created = await createSession({
          machine_code: machineCode,
          questioner: normalizedQuestioner,
          title: normalizedQuestion,
          llm_model: llmModel,
          llm_mode: llmMode,
          llm_persona: personaType,
        }, factoryId);
        sessionId = created.session_id;
        if (view.current === conversation) onSessionId(sessionId);
        historyRevision++;
      } catch (err) {
        conversation.error = err instanceof Error ? err.message : "세션 생성에 실패했습니다.";
        finish(conversation, null);
        return false;
      }
    }
    pending.set(sessionId, conversation);
    publish();

    const now = new Date().toISOString();
    let started;
    try {
      started = await startAnswer(factoryId, llmModel, sessionId, normalizedQuestion, llmMode, personaType, conversation.restoreMemory,
        undefined, forceNewSession ? undefined : selectedCitation);
    } catch (err) {
      conversation.error = err instanceof Error ? err.message : "답변을 시작하지 못했습니다.";
      finish(conversation, sessionId);
      return false;
    }
    const userMessageId = started.user_message_id;
    const assistantMessageId = started.message_id;

    const userMessage: MessageItem = {
      message_id: userMessageId,
      session_id: sessionId,
      role: "user",
      content: normalizedQuestion,
      created_at: now,
      questioner: normalizedQuestioner,
      model: llmModel,
      llm_mode: llmMode,
    };

    const assistantPlaceholder: MessageItem = {
      message_id: assistantMessageId,
      session_id: sessionId,
      role: "assistant",
      content: "",
      created_at: new Date().toISOString(),
      questioner: normalizedQuestioner,
      model: llmModel,
      llm_mode: llmMode,
    };

    conversation.messages = [...conversation.messages, userMessage, assistantPlaceholder];
    publish();

    return observeAnswer(conversation, sessionId, assistantMessageId, String(started.metadata.generation_id), epoch);
  };

  const observeAnswer = async (conversation: Conversation, sessionId: number, messageId: number, generationId: string, epoch?: number) => {
    let cancelled = false;
    pending.set(sessionId, conversation);
    conversation.busy = true;
    conversation.error = null;
    const stop = async () => {
      cancelled = true;
      conversation.stop = undefined;
      publish();
      try {
        await stopAnswer(factoryId, sessionId, messageId, generationId);
      } catch {
        if (conversation.busy) {
          conversation.stop = stop;
          conversation.error = "중단 요청을 전달하지 못했습니다. 다시 시도해 주세요.";
          publish();
        }
      }
    };
    conversation.stop = stop;
    publish();
    try {
      const saved = await watchAnswer(factoryId, sessionId, messageId, answer => {
        conversation.messages = conversation.messages.map(item => item.message_id === messageId
          ? { ...item, content: answer.content, metadata: answer.metadata } : item);
        publish();
      });
      conversation.restoreMemory = saved.status !== "completed";
      if (saved.status === "completed") {
        if (!cancelled && epoch === viewEpoch.current && conversation === view.current
            && saved.message_id === messageId && saved.metadata.generation_id === generationId) {
          const action = saved.metadata.ui_action;
          if (action?.type === "open_document" && typeof action.document?.document_name === "string"
              && typeof action.document.asset_url === "string" && action.document.asset_url.startsWith("/assets/")
              && Number.isSafeInteger(action.document.page) && Number(action.document.page) > 0) {
            onDocument?.(action.document);
          }
        }
        unreadAnswers.set(sessionId, messageId);
        saveUnreadAnswers();
      } else if (saved.status === "save_failed") {
        conversation.error = "답변을 이력에 저장하지 못했습니다.";
      }
      return saved.status === "completed" || saved.status === "cancelled";
    } catch {
      conversation.error = "답변 상태를 확인하지 못했습니다. 질문 이력을 다시 열어 확인해 주세요.";
      return false;
    } finally {
      conversation.stop = undefined;
      finish(conversation, sessionId);
    }
  };

  const retryLastAnswer = async (settings: Pick<SendQuestionParams, "llmModel" | "llmMode" | "personaType">) => {
    const conversation = view.current;
    const epoch = viewEpoch.current;
    const { messages } = conversation;
    if (conversation.busy || isSessionLoading) return false;
    const assistant = messages[messages.length - 1];
    const user = messages[messages.length - 2];
    if (!assistant || assistant.role !== "assistant" || !user || user.role !== "user") return false;
    if (assistant.content.trim() && assistant.content !== "(응답 생성 중...)" && !assistant.metadata?.request_failed) return false;
    const mode = (assistant.llm_mode as LlmMode) || settings.llmMode;
    const persona = (assistant.metadata?.persona_type as PersonaType) || settings.personaType;
    if (mode === "cms" && persona !== "manager") {
      conversation.error = "CMS는 관리자 모드에서만 사용할 수 있습니다. 현재 모드로 질문을 다시 전송해 주세요.";
      publish();
      return false;
    }
    conversation.busy = true;
    pending.set(assistant.session_id, conversation);
    publish();
    try {
      const started = await startAnswer(factoryId, assistant.model || settings.llmModel, assistant.session_id,
        user.content, mode, persona, true, assistant.message_id, selectedCitation);
      return await observeAnswer(conversation, assistant.session_id, assistant.message_id, String(started.metadata.generation_id), epoch);
    } catch {
      conversation.error = "답변을 다시 시작하지 못했습니다.";
      finish(conversation, assistant.session_id);
      return false;
    }
  };

  // =========================
  // useEffect
  // =========================

  // =========================
  // render(return)
  // =========================
  return {
    messages: view.current.messages,
    historyRevision,
    stopAnswer: view.current.stop,
    pendingSessions: pending,
    unreadAnswers,
    markAnswerRead,
    sendQuestion,
    retryLastAnswer,
    loadSessionMessages,
    resetChatState,
    isLoading: view.current.busy,
    isSessionLoading,
    error: view.current.error,
  };
};
