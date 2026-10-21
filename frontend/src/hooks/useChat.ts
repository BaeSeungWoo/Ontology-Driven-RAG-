import { useRef, useState } from "react";
import { askApi } from "@/services/chatApi";
import { createMessage, createSession, getMessages, updateMessage } from "@/services/chatApi";
import type { LlmModel, LlmMode } from "@/constants/llmOptions";
import type { PersonaType } from "@/constants/personaOptions";
import type { ChatMetadata, MessageItem } from "@/types/chatApi";

type UseChatParams = {
  selectedSessionId: number | null;
  onSessionId: (id: number) => void;
  onHistoryRefresh?: () => void;
};

export type SendQuestionParams = {
  question: string;
  questioner: string;
  llmModel: LlmModel;
  llmMode: LlmMode;
  personaType: PersonaType;
  forceNewSession?: boolean;
};

/**
 * 기능: 최종 답변에 실제 표기된 chunk 인용만 metadata.used_chunks로 추려낸다.
 * 목적: 이미지/표/인용근거 패널이 답변에 사용된 참조를 우선 표시하게 한다.
 * In: metadata(ChatMetadata | undefined), answer(string)
 * Out: used_chunks가 포함된 ChatMetadata | undefined
 */
function withUsedChunks(metadata: ChatMetadata | undefined, answer: string): ChatMetadata | undefined {
  if (!metadata) return undefined;
  const chunks = Array.isArray(metadata.chunks) ? metadata.chunks : [];
  if (chunks.length === 0) return metadata;

  const usedIndexes = new Set<number>();
  const citationPattern = /\[chunk:(\d+)\]/gi;
  let match: RegExpExecArray | null;

  while ((match = citationPattern.exec(answer)) !== null) {
    const index = Number(match[1]);
    if (Number.isInteger(index)) {
      usedIndexes.add(index);
    }
  }

  return {
    ...metadata,
    used_chunks: chunks.filter((chunk) => usedIndexes.has(chunk.index)),
  };
}

export const useChat = ({ selectedSessionId, onSessionId, onHistoryRefresh }: UseChatParams) => {
  // =========================
  // state
  // =========================
  const [messages, setMessages] = useState<MessageItem[]>([]);
  const [isLoading, setIsLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [shouldRestoreMemory, setShouldRestoreMemory] = useState(false);
  const [isSessionLoading, setIsSessionLoading] = useState(false);
  const sessionLoadVersion = useRef(0);

  // =========================
  // 함수
  // =========================
  /**
   * 기능: 채팅 화면 상태를 초기화한다.
   * 목적: 새 질문 시작 또는 외부 초기화 시 기존 메시지/오류/로딩 상태를 정리한다.
   * In: 호출 이벤트(새 질문/초기화 트리거)
   * Out: messages=[], error=null, isLoading=false
   */
  const resetChatState = () => {
    sessionLoadVersion.current += 1;
    setIsSessionLoading(false);
    setShouldRestoreMemory(false);
    setMessages([]);
    setError(null);
    setIsLoading(false);
  };

  /**
   * 기능: 특정 세션의 메시지 목록을 불러온다.
   * 목적: 히스토리 카드 선택 시 해당 세션 대화를 화면에 복원한다.
   * In: sessionId(number)
   * Out: messages 갱신 또는 error 갱신
   */
  const loadSessionMessages = async (sessionId: number, promptName?: string | null) => {
    const version = ++sessionLoadVersion.current;
    setIsSessionLoading(true);
    try {
      setError(null);
      const sessionMessages = await getMessages(sessionId);
      if (version !== sessionLoadVersion.current) return false;
      setMessages(sessionMessages.map((message) => ({
        ...message,
        prompt_name: message.prompt_name ?? promptName,
      })));
      setShouldRestoreMemory(true);
      return sessionMessages;
    } catch (err) {
      if (version !== sessionLoadVersion.current) return false;
      const message = err instanceof Error ? err.message : "세션 메시지 조회 중 오류가 발생했습니다.";
      setError(`세션 로드 실패: ${message}`);
      setMessages([]);
      return false;
    } finally {
      if (version === sessionLoadVersion.current) setIsSessionLoading(false);
    }
  };

  /**
   * 기능: 질문 전송, 세션 생성, 메시지 저장, 스트리밍 응답 반영을 한 번에 처리한다.
   * 목적: 채팅 전송 플로우를 훅 내부에서 일관되게 수행한다.
   * In: question/questioner/llmModel/llmMode/forceNewSession
   * Out: 성공 여부(boolean), messages/isLoading/error/session 상태 반영
   */
  const sendQuestion = async ({
    question,
    questioner,
    llmModel,
    llmMode,
    personaType,
    forceNewSession = false,
  }: SendQuestionParams) => {
    const normalizedQuestion = question.trim();
    if (!normalizedQuestion) return false;

    const normalizedQuestioner = questioner.trim();
    if (!normalizedQuestioner) {
      setError("질문자를 입력해 주세요.");
      return false;
    }

    let sessionId = forceNewSession ? null : selectedSessionId;

    if (sessionId === null) {
      try {
        const created = await createSession({
          questioner: normalizedQuestioner,
          title: normalizedQuestion,
          llm_model: llmModel,
          llm_mode: llmMode,
          llm_persona: personaType,
        });
        sessionId = created.session_id;
        onSessionId(sessionId);
        onHistoryRefresh?.();
      } catch (err) {
        const message = err instanceof Error ? err.message : "세션 생성 중 오류가 발생했습니다.";
        setError(`세션 생성 실패: ${message}`);
        return false;
      }
    }

    if (sessionId === null) {
      setError("세션 ID가 없어 요청을 보낼 수 없습니다.");
      return false;
    }

    if (forceNewSession) {
      setMessages([]);
      setShouldRestoreMemory(false);
    }

    setIsLoading(true);
    setError(null);

    const now = new Date().toISOString();
    let userMessageId = Date.now();
    let assistantMessageId = userMessageId + 1;

    try {
      const createdUser = await createMessage({
        session_id: sessionId,
        role: "user",
        content: normalizedQuestion,
      });
      userMessageId = createdUser.message_id;

      const createdAssistant = await createMessage({
        session_id: sessionId,
        role: "assistant",
        content: "",
      });
      assistantMessageId = createdAssistant.message_id;
    } catch (err) {
      const message = err instanceof Error ? err.message : "메시지 생성 중 오류가 발생했습니다.";
      setError(`메시지 생성 실패: ${message}`);
      setIsLoading(false);
      return false;
    }

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

    setMessages((prev) => [...prev, userMessage, assistantPlaceholder]);

    return generateAnswer(sessionId, assistantMessageId, {
      question: normalizedQuestion, llmModel, llmMode, personaType,
    }, shouldRestoreMemory);
  };

  const generateAnswer = async (
    sessionId: number,
    assistantMessageId: number,
    { question, llmModel, llmMode, personaType }: Pick<SendQuestionParams, "question" | "llmModel" | "llmMode" | "personaType">,
    restoreMemory: boolean,
  ) => {
    setIsLoading(true);
    setError(null);
    let progress: ChatMetadata = llmMode === "electrical" ? {
      progress_started_at: Date.now(),
      progress_history: [{ message: "전기도면 QA 요청을 보내는 중", at: Date.now() }],
    } : {};
    setMessages(prev => prev.map(item => item.message_id === assistantMessageId
      ? { ...item, content: "", metadata: { persona_type: personaType, ...progress } }
      : item));
    try {
      let streamedAnswer = "";

      const requestStartedAt = performance.now();
      const result = await askApi({
        sessionId,
        question,
        llmModel,
        llmMode,
        personaType,
        restoreMemory,
        onProgress: (message, detail) => {
          const at = Date.now();
          const history = progress.progress_history ?? [];
          const last = history.at(-1);
          progress = { ...progress, progress_message: message, progress_updated_at: at,
            progress_history: last?.message === message
              ? detail && detail !== last.detail ? [...history.slice(0, -1), { ...last, detail }] : history
              : [...history, { message, detail, at }] };
          setMessages(prev => prev.map(item => item.message_id === assistantMessageId
            ? { ...item, metadata: { ...item.metadata, ...progress } }
            : item));
        },
        onRetry: (attempt) => {
          streamedAnswer = "";
          setMessages(prev => prev.map(item => item.message_id === assistantMessageId
            ? { ...item, content: "", metadata: { persona_type: personaType, retry_attempt: attempt } }
            : item));
        },
        onChunk: (chunk) => {
          streamedAnswer += chunk;
          setMessages((prev) =>
            prev.map((item) =>
              item.message_id === assistantMessageId
                ? { ...item, content: streamedAnswer || "(응답 생성 중...)" }
                : item
            )
          );
        },
      });

      const finalAnswer = result.answer || streamedAnswer || "(응답 없음)";
      const metadataWithUsedChunks = {
        ...withUsedChunks(result.metadata, finalAnswer),
        ...progress,
        ...(llmMode === "electrical" ? { progress_finished_at: Date.now() } : {}),
        elapsed_ms: Math.round(performance.now() - requestStartedAt),
        persona_type: personaType,
      };

      setMessages((prev) =>
        prev.map((item) =>
          item.message_id === assistantMessageId
            ? { ...item, content: finalAnswer, metadata: metadataWithUsedChunks }
            : item
        )
      );

      try {
        await updateMessage(assistantMessageId, {
          content: finalAnswer,
          metadata: metadataWithUsedChunks,
        });
      } catch {
        setError("답변은 생성되었지만 이력에 저장하지 못했습니다.");
        return false;
      }

      setShouldRestoreMemory(false);
      onHistoryRefresh?.();
    } catch (err) {
      const message = err instanceof Error ? err.message : "질문 요청 중 오류가 발생했습니다.";
      setError(message);
      setShouldRestoreMemory(true);
      const failedMetadata: ChatMetadata = { persona_type: personaType, request_failed: true, ...progress,
        ...(llmMode === "electrical" ? { progress_finished_at: Date.now() } : {}) };

      setMessages((prev) =>
        prev.map((item) =>
          item.message_id === assistantMessageId
            ? { ...item, content: `요청 실패: ${message}`, metadata: failedMetadata }
            : item
        )
      );
      if (llmMode === "electrical") {
        try {
          await updateMessage(assistantMessageId, { content: `요청 실패: ${message}`, metadata: failedMetadata });
          onHistoryRefresh?.();
        } catch {
          setError(`${message} (작업 이력을 저장하지 못했습니다.)`);
        }
      }
      return false;
    } finally {
      setIsLoading(false);
    }

    return true;
  };

  const retryLastAnswer = async (settings: Pick<SendQuestionParams, "llmModel" | "llmMode" | "personaType">) => {
    if (isLoading || isSessionLoading) return false;
    const assistant = messages[messages.length - 1];
    const user = messages[messages.length - 2];
    if (!assistant || assistant.role !== "assistant" || !user || user.role !== "user") return false;
    if (assistant.content.trim() && assistant.content !== "(응답 생성 중...)" && !assistant.metadata?.request_failed) return false;
    const mode = (assistant.llm_mode as LlmMode) || settings.llmMode;
    const persona = (assistant.metadata?.persona_type as PersonaType) || settings.personaType;
    if (mode === "cms" && persona !== "manager") {
      setError("CMS는 관리자 모드에서만 사용할 수 있습니다. 현재 모드로 질문을 다시 전송해 주세요.");
      return false;
    }
    return generateAnswer(assistant.session_id, assistant.message_id, {
      ...settings,
      question: user.content,
      llmModel: (assistant.model as LlmModel) || settings.llmModel,
      llmMode: mode,
      personaType: persona,
    }, true);
  };

  // =========================
  // useEffect
  // =========================

  // =========================
  // render(return)
  // =========================
  return {
    messages,
    sendQuestion,
    retryLastAnswer,
    loadSessionMessages,
    resetChatState,
    isLoading,
    isSessionLoading,
    error,
  };
};
