import styles from "./history.module.css";

/**
 * 기능: 히스토리 목록에서 카드 렌더링에 사용하는 데이터 타입을 정의한다.
 * 목적: 상위 목록/카드 컴포넌트가 표시용 라벨과 동기화용 원본값을 함께 다루도록 한다.
 * In: 히스토리 API를 화면용으로 매핑한 데이터
 * Out: HistoryItem 타입 정보
 */
export type HistoryItem = {
  id: number;
  title: string;
  questioner: string;
  llmModel: string;
  llmMode: string;
  promptNo: number | null;
  llmModelLabel: string;
  llmModeLabel: string;
  promptName: string;
  recentAt: string;
  isActive?: boolean;
};

/**
 * 기능: HistoryCard 컴포넌트 입력 props 타입을 정의한다.
 * 목적: 카드 단위 렌더링에 필요한 데이터와 이벤트를 명확히 한다.
 * In: item, onSelect
 * Out: HistoryCardProps 타입 정보
 */
type HistoryCardProps = {
  item: HistoryItem;
  onSelect: (chatId: number) => void;
};

/**
 * 기능: 단일 대화 이력 카드를 렌더링한다.
 * 목적: 제목/모델/모드/프롬프트/최근 시각/질문자를 한 번에 보여주고 선택 이벤트를 전달한다.
 * In: item(HistoryItem), onSelect(chatId)
 * Out: JSX Element
 */
export default function HistoryCard({ item, onSelect }: HistoryCardProps) {
  // =========================
  // State
  // =========================
  // 이 컴포넌트는 로컬 상태를 사용하지 않는다.

  // =========================
  // 함수: 표시 데이터 계산
  // =========================
  /**
   * 기능: 활성 카드 여부에 따라 카드 클래스 문자열을 계산한다.
   * 목적: 선택된 이력을 시각적으로 강조한다.
   * In: item.isActive
   * Out: cardClassName(string)
   */
  const cardClassName = `${styles.historyCard} ${item.isActive ? styles.historyCardActive : ""}`;

  /**
   * 기능: 모델/모드/프롬프트 라인을 한 줄 텍스트로 구성한다.
   * 목적: 메타 정보를 compact하게 표시한다.
   * In: item.llmModelLabel, item.llmModeLabel, item.promptName
   * Out: modelModePromptText(string)
   */
  const modelModePromptText = `· ${item.llmModelLabel} | ${item.llmModeLabel} | ${item.promptName}`;

  /**
   * 기능: 카드 클릭 시 선택된 chat id를 상위로 전달한다.
   * 목적: 상위 컴포넌트에서 해당 대화 이력을 로드하도록 연결한다.
   * In: item.id
   * Out: onSelect(item.id) 호출
   */
  const handleSelect = () => {
    onSelect(item.id);
  };

  // =========================
  // Render
  // =========================
  return (
    <button
      type="button"
      className={cardClassName}
      aria-label="질문 이력 카드"
      onClick={handleSelect}
    >
      <p className={styles.cardTitle}>{item.title}</p>
      <p className={styles.cardModelMode}>{modelModePromptText}</p>
      <div className={styles.cardBottomRow}>
        <p className={styles.cardMeta}>· {item.recentAt}</p>
        <p className={styles.cardQuestioner}>{item.questioner}</p>
      </div>
    </button>
  );
}
