import { useCallback, useMemo, useState } from "react";
import {
  createChat,
  createMessage,
  getChats,
  getMessages,
  askQuestion
} from "@/services/chatApi";
import type { LlmModel } from "@/types/prompt";
import type {
  ChatItem,
  CreateMessagePayload,
  MessageItem,
} from "@/types/chatApi";

/**
 * useChat
 *
 * 목적:
 * - 채팅 이력 화면에서 필요한 상태와 API 호출 흐름을 한 곳에서 관리한다.
 * - 컴포넌트는 "무엇을 렌더링할지"에 집중하고,
 *   이 훅은 "어떤 순서로 데이터를 불러오고 저장할지"를 담당한다.
 *
 * 계층 역할:
 * - services/chatApi.ts: HTTP 호출만 담당 (stateless)
 * - hooks/useChat.ts: 서비스 함수 조합 + 상태/로딩/에러 관리
 */
export const useChat = () => {
  /** 채팅 목록(우측 이력 카드 데이터) */
  const [chats, setChats] = useState<ChatItem[]>([]);
  /** 현재 선택된 채팅 ID */
  const [currentChatId, setCurrentChatId] = useState<number | null>(null);
  /** 현재 선택된 채팅의 메시지 목록 */
  const [messages, setMessages] = useState<MessageItem[]>([]);
  /** API 진행 상태 */
  const [isLoading, setIsLoading] = useState(false);
  /** UI 알림용 에러 메시지 */
  const [error, setError] = useState<string | null>(null);

  /**
   * 공통 에러 처리
   * - 서버/네트워크 에러를 사용자 친화적인 문자열로 변환한다.
   */
  const handleError = useCallback((unknownError: unknown) => {
    if (unknownError instanceof Error) {
      setError(unknownError.message);
      return;
    }
    setError("요청 처리 중 알 수 없는 오류가 발생했습니다.");
  }, []);

  /** 에러 초기화 (토스트/알럿 닫을 때 사용) */
  const clearError = useCallback(() => {
    setError(null);
  }, []);

  /**
   * 새 질문 시작 시 현재 선택 채팅을 해제한다.
   * - 질문자/모델/프롬프트 설정은 유지하고 대화 타임라인만 비움
   */
  const resetCurrentChat = useCallback(() => {
    setCurrentChatId(null);
    setMessages([]);
  }, []);

  /**
   * 질문 전송 시나리오 입력값
   * - question: 메시지에 함께 기록할 질문
   * - questioner: 메시지에 함께 기록할 질문자
   * - promptNo/promptName: 채팅 이력 저장용 프롬프트 식별 정보
   * - promptTxt: 백엔드 LLM 실행 시 사용할 실제 프롬프트 본문
   * - llmModel: 백엔드 LLM 실행 시 사용할 모델
   * - selectedChatId: 이력에서 선택된 채팅 ID (없으면 null)
   */
  type SendQuestionParams = {
    question: string;
    // questioner: string;
    // promptNo: number;
    // promptName: string | null;
    // promptTxt: string | null;
    llmModel: LlmModel;
    // selectedChatId?: number | null;
  };

  /**
   * 채팅 목록 로드
   * @param asker 질문자 필터(선택)
   */
  const loadChats = useCallback(
    async (asker?: string) => {
      setIsLoading(true);
      setError(null);
      try {
        const nextChats = await getChats(asker);
        setChats(nextChats);
      } catch (unknownError) {
        handleError(unknownError);
      } finally {
        setIsLoading(false);
      }
    },
    [handleError],
  );

  /**
   * 특정 채팅 선택 + 메시지 목록 로드
   * - 이력 카드 클릭 시 호출하는 진입점
   */
  const selectChat = useCallback(
    async (chatId: number) => {
      setIsLoading(true);
      setError(null);
      try {
        const nextMessages = await getMessages(chatId);
        setCurrentChatId(chatId);
        setMessages(nextMessages);
      } catch (unknownError) {
        handleError(unknownError);
      } finally {
        setIsLoading(false);
      }
    },
    [handleError],
  );

  /**
   * 새 채팅 시작
   * - 채팅 1개를 생성하고 즉시 현재 채팅으로 선택한다.
   * - 생성 직후 메시지는 비어 있으므로 messages는 빈 배열로 초기화한다.
   */
  const startChat = useCallback(
    async (params: { asker: string; title: string }) => {
      setIsLoading(true);
      setError(null);
      try {
        const created = await createChat(params);
        setChats((prev) => [created, ...prev]);
        setCurrentChatId(created.chat_id);
        setMessages([]);
        return created;
      } catch (unknownError) {
        handleError(unknownError);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [handleError],
  );

  /**
   * 현재 채팅에 메시지 1건 추가
   * - chatId를 인자로 받지 않으면 currentChatId를 사용한다.
   * - 생성 성공 시 로컬 메시지 상태에도 즉시 반영한다.
   */
  const appendMessage = useCallback(
    async (payload: CreateMessagePayload, chatId?: number) => {
      const targetChatId = chatId ?? currentChatId;
      if (!targetChatId) {
        setError("메시지를 저장할 채팅이 선택되지 않았습니다.");
        return null;
      }

      setIsLoading(true);
      setError(null);
      try {
        const created = await createMessage(targetChatId, payload);
        setMessages((prev) => [...prev, created]);
        return created;
      } catch (unknownError) {
        handleError(unknownError);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [currentChatId, handleError],
  );

  const sendQuestion = useCallback(
    async ({
      question,
      // questioner,
      // promptNo,
      // promptName,
      // promptTxt,
      llmModel,
      // selectedChatId = null,
    }: SendQuestionParams) => {
      /**
       * sendQuestion (주석 설계안)
       *
       * 목적:
       * - 프론트에서 질문 전송 1회 호출로 백엔드 오케스트레이션을 실행한다.
       * - 백엔드가 반환한 chatId/userMessage/assistantMessage로 훅 상태를 갱신한다.
       *
       * In:
       * - question: string
       * - questioner: string
       * - promptNo: number
       * - promptName: string | null
       * - promptTxt: string | null   // LLM 실행용
       * - llmModel: LlmModel         // LLM 실행용
       * - selectedChatId?: number | null
       *
       * Out:
       * - 성공: { chatId, userMessage, assistantMessage }
       * - 실패: null (error 상태 갱신)
       *
       * 상태 변경:
       * - setIsLoading(true/false)
       * - setError(...)
       * - setCurrentChatId(chatId)
       * - setMessages(prev => [...prev, userMessage, assistantMessage])
       */

      // const sendQuestion = useCallback(async (params: SendQuestionParams) => {
      //   // 1) 입력값 검증
      //   // - question/questioner 비어있으면 setError 후 null 반환
      //
      //   // 2) 로딩 시작 + 에러 초기화
      //   // setIsLoading(true); setError(null);
      //
      //   // 3) 백엔드 단일 엔드포인트 호출
      //   // 예: POST /api/chats/ask
      //   // body: {
      //   //   question, questioner, promptNo, promptName, promptTxt, llmModel, selectedChatId
      //   // }
      //
      //   // 4) 백엔드 응답 파싱
      //   // - response.chatId
      //   // - response.userMessage
      //   // - response.assistantMessage
      //
      //   // 5) 훅 상태 갱신 (여기서만 상태 변경)
      //   // setCurrentChatId(response.chatId);
      //   // setMessages(prev => [...prev, response.userMessage, response.assistantMessage]);
      //
      //   // 6) 필요 시 chats 목록도 최신화
      //   // - 새 chat이면 목록 prepend
      //   // - 기존 chat이면 last_message_at 갱신
      //
      //   // 7) 결과 반환
      //   // return { chatId, userMessage, assistantMessage };
      //
      //   // 8) 예외 처리
      //   // - catch: setError(...); return null;
      //
      //   // 9) finally
      //   // setIsLoading(false);
      // }, []);


      setIsLoading(true);
      setError(null);
      try {
        const response = await askQuestion({
          question,
          llmModel,
        });

        const responseRecord =
          response && typeof response === "object"
            ? (response as Record<string, unknown>)
            : {};

        const toMessageItem = (
          raw: unknown,
          fallbackRole: MessageItem["role"],
        ): MessageItem | null => {
          if (!raw || typeof raw !== "object") {
            return null;
          }

          const item = raw as Record<string, unknown>;
          const content = String(item.content ?? item.text ?? item.message ?? "").trim();
          if (!content) {
            return null;
          }

          const roleValue = item.role === "assistant" ? "assistant" : "user";
          const nextChatId = Number(item.chat_id ?? item.chatId ?? currentChatId ?? 0) || 0;
          const nextMessageId =
            Number(item.message_id ?? item.messageId ?? Date.now()) || Date.now();
          const createdAt = String(item.created_at ?? item.createdAt ?? new Date().toISOString());

          return {
            message_id: nextMessageId,
            chat_id: nextChatId,
            role: item.role ? roleValue : fallbackRole,
            content,
            created_at: createdAt,
          };
        };

        const userMessage = toMessageItem(
          responseRecord.userMessage ?? responseRecord.user_message,
          "user",
        );
        let assistantMessage = toMessageItem(
          responseRecord.assistantMessage ?? responseRecord.assistant_message,
          "assistant",
        );

        // assistantMessage 구조가 없고 answer 문자열만 내려오는 테스트 응답도 지원
        if (!assistantMessage) {
          const answerText = String(responseRecord.answer ?? "").trim();
          if (answerText) {
            assistantMessage = {
              message_id: Date.now() + 1,
              chat_id: currentChatId || 0,
              role: "assistant",
              content: answerText,
              created_at: new Date().toISOString(),
            };
          }
        }

        const nextMessages = [userMessage, assistantMessage].filter(
          (msg): msg is MessageItem => msg !== null,
        );
        if (nextMessages.length > 0) {
          setMessages((prev) => [...prev, ...nextMessages]);
        }

        return response;
      } catch (unknownError) {
        handleError(unknownError);
        return null;
      } finally {
        setIsLoading(false);
      }
    },
    [currentChatId, handleError],
  );

  /** 현재 선택된 채팅의 메타 정보 (UI 표시용) */
  const currentChat = useMemo(
    () => chats.find((chat) => chat.chat_id === currentChatId) ?? null,
    [chats, currentChatId],
  );

  return {
    chats,
    currentChatId,
    currentChat,
    messages,
    isLoading,
    error,
    loadChats,
    selectChat,
    startChat,
    appendMessage,
    sendQuestion,
    resetCurrentChat,
    clearError,
  };
};
