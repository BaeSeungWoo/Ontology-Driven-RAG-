import { useEffect, useRef, useState } from "react";
import { Contrast, Search, SlidersHorizontal, ThumbsDown, ThumbsUp, X } from "lucide-react";
import { searchHistory } from "@/services/historyApi";
import type { HistorySearchMode, HistorySearchResponse } from "@/types/historyApi";
import type { MessageFeedback } from "@/types/chatApi";
import { toHistoryItem } from "@/hooks/useHistoryPanel";
import type { HistoryItem } from "./historyCard";
import styles from "./history.module.css";

const FEEDBACK_OPTIONS = [
  { value: null, icon: null },
  { value: "도움됨", icon: ThumbsUp },
  { value: "틀림", icon: ThumbsDown },
  { value: "부분도움", icon: Contrast },
] as const;

export default function HistorySearch({ onClose, onSelect }: {
  onClose: () => void;
  onSelect: (item: HistoryItem) => void;
}) {
  const dialogRef = useRef<HTMLDialogElement>(null);
  const inputRef = useRef<HTMLInputElement>(null);
  const [query, setQuery] = useState("");
  const [items, setItems] = useState<HistorySearchResponse[]>([]);
  const [mode, setMode] = useState<HistorySearchMode>("sessions");
  const [feedback, setFeedback] = useState<MessageFeedback | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
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
    searchHistory(mode, feedback).then(rows => {
      if (active) setItems(rows);
    }).catch(() => {
      if (active) setError("검색할 이력을 불러오지 못했습니다.");
    }).finally(() => {
      if (active) setIsLoading(false);
    });
    return () => { active = false; };
  }, [retry, mode, feedback]);

  const keyword = query.trim().toLocaleLowerCase();
  const results = items.filter(item =>
    `${mode === "messages" ? item.question ?? item.title : item.title} ${item.questioner}`.toLocaleLowerCase().includes(keyword)
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
        <div className={styles.searchToolbar}>
          <p className={styles.searchCount} role="status">{isLoading ? "조회 중…" : error ? "조회 실패" : `${results.length}개의 ${mode === "sessions" ? "이력" : "질문·답변"}`}</p>
          <button type="button" className={styles.filterButton} data-feedback={feedback ?? "전체"} data-active={feedback !== null} aria-expanded={filtersOpen} aria-controls="history-filters" onClick={() => setFiltersOpen(value => !value)}>
            <SlidersHorizontal size={14} aria-hidden="true" /> 필터{feedback ? ` · ${feedback}` : ""}
          </button>
        </div>
        <div className={styles.searchModes} role="group" aria-label="검색 결과 표시 방식">
          {([ ["sessions", "세션별"], ["messages", "질문·답변별"] ] as const).map(([value, label]) => (
            <button key={value} type="button" aria-pressed={mode === value} onClick={() => { if (mode !== value) { setIsLoading(true); setError(""); setMode(value); } }}>{label}</button>
          ))}
        </div>
        {filtersOpen && <div id="history-filters" className={`${styles.searchModes} ${styles.feedbackFilters}`} role="group" aria-label="피드백 필터">
          {FEEDBACK_OPTIONS.map(({ value, icon: Icon }) => (
            <button key={value ?? "all"} type="button" data-feedback={value ?? "전체"} aria-pressed={feedback === value} onClick={() => { if (feedback !== value) { setIsLoading(true); setError(""); setFeedback(value); } }}>
              {Icon && <Icon size={15} aria-hidden="true" />}{value ?? "전체"}
            </button>
          ))}
        </div>}
        <div className={styles.searchResults}>
          {isLoading ? <p role="status">이력을 불러오는 중…</p> : error ? (
            <div role="alert">{error} <button type="button" onClick={() => { setIsLoading(true); setError(""); setRetry(value => value + 1); }}>다시 시도</button></div>
          ) : <>
            {results.map(item => (
              <button type="button" key={item.messageId ?? item.sessionId} className={styles.searchResult} onClick={() => onSelect({ ...toHistoryItem(item, null), targetMessageId: item.targetMessageId })}>
                <strong>{mode === "messages" ? item.question || item.title : item.title}</strong>
                {mode === "messages" && <span className={styles.answerPreview}>{item.answerPreview}</span>}
                {item.reason?.trim() && <span className={styles.reasonPreview} title={item.reason}>평가사유 · {item.reason}</span>}
                <span>{item.questioner} · {toHistoryItem({ ...item, updatedAt: item.messageCreatedAt ?? item.updatedAt }, null).recentAt}{mode === "messages" ? ` · ${item.feedback ?? "피드백 없음"}` : ""}</span>
              </button>
            ))}
            {results.length === 0 && <p>검색 결과가 없습니다.</p>}
          </>}
        </div>
      </div>
    </dialog>
  );
}
