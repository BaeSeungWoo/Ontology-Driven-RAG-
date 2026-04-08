import styles from "./answer.module.css";
import type { AnswerMessage } from "@/types/chat";
import { LLM_MODEL_OPTIONS, LLM_MODE_OPTIONS } from "@/constants/llmOptions";
import { formatTimeLabel } from "./chatDate";

/**
 * 기능: 사용자(질문) 말풍선 렌더링 + 좌측 메타 정보 표시
 * 이유: 질문 본문과 실행 메타(질문자/프롬프트/모델/모드/시각)를 함께 보여주기 위해
 * In: AnswerMessage(질문)
 * Out: 우측 질문 버블 + 좌측 메타 리스트
 */
type UserMessageBubbleProps = {
  message: AnswerMessage;
};

const formatMeta = (value?: string | null) => {
  const normalized = value?.trim();
  return normalized && normalized.length > 0 ? normalized : "-";
};

export default function UserMessageBubble({ message }: UserMessageBubbleProps) {
  /**
   * 기능: value -> label 변환
   * 이유: 내부 키(ollama_config/base) 대신 사용자 친화 라벨(Ollama/Base) 노출
   * In: message.llmModel, message.llmMode
   * Out: llmModelLabel, llmModeLabel
   */
  const llmModelLabel =
    LLM_MODEL_OPTIONS.find((option) => option.value === message.llmModel)?.label ??
    message.llmModel;
  const llmModeLabel =
    LLM_MODE_OPTIONS.find((option) => option.value === message.llmMode)?.label ??
    message.llmMode;

  return (
    <article className={`${styles.messageItem} ${styles.userMessage}`}>
      <ul className={styles.userMetaColumn} aria-label="질문 메타 정보">
        <li className={styles.userMetaLabel}>- 질문자: {formatMeta(message.questioner)}</li>
        <li className={styles.userMetaLabel}>- 프롬프트명: {formatMeta(message.promptName)}</li>
        <li className={styles.userMetaLabel}>- 모델명: {formatMeta(llmModelLabel)}</li>
        <li className={styles.userMetaLabel}>- 모드: {formatMeta(llmModeLabel)}</li>
        <li className={styles.userTimeLabel}>- 질문시각: {formatTimeLabel(message.createdAt)}</li>
      </ul>

      <div className={styles.messageBody}>
        <p className={styles.messageRole}>질문</p>
        <div className={styles.messageText}>
          {message.text.split("\n").map((line, textLineIndex) => (
            <p key={`${message.id}-${textLineIndex}`}>{line || "\u00A0"}</p>
          ))}
        </div>
      </div>
    </article>
  );
}
