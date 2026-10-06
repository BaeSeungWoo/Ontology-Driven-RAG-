import { useEffect, useRef, useState } from "react";
import { Search, X } from "lucide-react";
import { getHistory } from "@/services/historyApi";
import { toHistoryItem } from "@/hooks/useHistoryPanel";
import type { HistoryItem } from "./historyCard";
import styles from "./history.module.css";

export default function HistorySearch({ onClose, onSelect }: {
  onClose: () => void;
  onSelect: (item: HistoryItem) => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<HistoryItem[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);

  useEffect(() => {
    const dialog = dialogRef.current;
    dialog?.showModal();
    inputRef.current?.focus();
    return () => dialog?.close();
  }, []);

  useEffect(() => {
    let active = true;
    getHistory().then(rows => {
      if (active) setItems(rows.map(row => toHistoryItem(row, null)));
    }).catch(() => {
      if (active) setError("검색할 이력을 불러오지 못했습니다.");
    }).finally(() => {
      if (active) setIsLoading(false);
    });
    return () => { active = false; };
  }, [retry]);

  const keyword = query.trim().toLocaleLowerCase();
  const results = items.filter(item =>
    `${item.title} ${item.questioner}`.toLocaleLowerCase().includes(keyword)
  );

  return (
    <dialog ref={dialogRef} className={styles.searchDialog} aria-labelledby="history-search-title"
      onCancel={event => { event.preventDefault(); onClose(); }} onClick={event => { if (event.target === event.currentTarget) onClose(); }}>
      <div className={styles.searchContent}>
        <div className={styles.headerRow}>
          <h2 id="history-search-title" className={styles.historyTitle}>질문 이력 검색</h2>
          <button type="button" className={styles.searchButton} aria-label="검색 닫기" onClick={onClose}><X size={18} /></button>
        </div>
        <label className={styles.searchField}>
          <Search size={18} aria-hidden="true" />
          <input ref={inputRef} aria-label="제목 또는 질문자 검색" placeholder="제목 또는 질문자명으로 검색" value={query} onChange={event => setQuery(event.target.value)} />
        </label>
        <div className={styles.searchResults}>
          {isLoading ? <p role="status">이력을 불러오는 중…</p> : error ? (
            <div role="alert">{error} <button type="button" onClick={() => { setIsLoading(true); setError(""); setRetry(value => value + 1); }}>다시 시도</button></div>
          ) : <>
            <p className={styles.searchCount} role="status">{results.length}개의 이력</p>
            {results.map(item => (
              <button type="button" key={item.id} className={styles.searchResult} onClick={() => onSelect(item)}>
                <strong>{item.title}</strong>
                <span>{item.questioner} · {item.recentAt}</span>
              </button>
            ))}
            {results.length === 0 && <p>검색 결과가 없습니다.</p>}
          </>}
        </div>
      </div>
    </dialog>
  );
}
