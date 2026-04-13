import styles from "./answer.module.css";
import { formatDateLabel } from "./chatDate";

type ChatDateDividerProps = {
  createdAt: number;
};

export default function ChatDateDivider({ createdAt }: ChatDateDividerProps) {
  // =========================
  // state
  // =========================

  // =========================
  // 함수
  // =========================
  /**
   * 기능: 날짜 구분선에 표시할 날짜 라벨을 생성한다.
   * 목적: 타임라인 날짜 경계에서 사용자에게 명확한 기준 날짜를 제공한다.
   * In: createdAt(number)
   * Out: dateLabel(string)
   */
  const getDividerLabel = () => {
    return formatDateLabel(createdAt);
  };

  const dateLabel = getDividerLabel();

  // =========================
  // useEffect
  // =========================

  // =========================
  // render(return)
  // =========================
  return (
    <div className={styles.dateDividerWrap}>
      <span className={styles.dateDivider}>{dateLabel}</span>
    </div>
  );
}
