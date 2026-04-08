import styles from "./history.module.css";

export type HistoryItem = {
  id: number;
  title: string;
  questioner: string;
  recentAt: string;
  isActive?: boolean;
};

type HistoryCardProps = {
  item: HistoryItem;
  onSelect: (chatId: number) => void;
};

export default function HistoryCard({ item, onSelect }: HistoryCardProps) {
  return (
    <button
      type="button"
      className={`${styles.historyCard} ${item.isActive ? styles.historyCardActive : ""}`}
      aria-label="질문 이력 카드"
      onClick={() => onSelect(item.id)}
    >
      <p className={styles.cardTitle}>{item.title}</p>
      <p className={styles.cardMeta}>질문자: {item.questioner}</p>
      <p className={styles.cardMeta}>최근 대화시각: {item.recentAt}</p>
    </button>
  );
}
