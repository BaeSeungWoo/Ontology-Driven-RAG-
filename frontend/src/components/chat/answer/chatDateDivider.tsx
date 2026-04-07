import styles from "./answer.module.css";
import { formatDateLabel } from "./chatDate";

type ChatDateDividerProps = {
  createdAt: number;
};

export default function ChatDateDivider({ createdAt }: ChatDateDividerProps) {
  // 메시지 날짜 경계마다 중앙 배지로 날짜를 표시
  return (
    <div className={styles.dateDividerWrap}>
      <span className={styles.dateDivider}>{formatDateLabel(createdAt)}</span>
    </div>
  );
}
