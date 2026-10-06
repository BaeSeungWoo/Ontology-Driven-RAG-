import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Plus, Search } from "lucide-react";
import { formatHistoryDateGroup } from "./historyTime";
import { useHistoryPanel } from "@/hooks/useHistoryPanel";
import { deleteHistorySession } from "@/services/historyApi";
import HistoryCard, { type HistoryItem } from "./historyCard";
import HistorySearch from "./historySearch";
import styles from "./history.module.css";

type HistoryProps = {
  selectedSessionId: number | null;
  onSelectSession: (sessionId: number, sessionMeta?: HistoryItem) => void;
  onStartNewChat?: () => void;
  onDeleteSession?: (sessionId: number) => void;
  onHistoryRefresh?: () => void;
  refreshKey?: number;
};

export default function History({ selectedSessionId, onSelectSession, onStartNewChat,
  onDeleteSession, onHistoryRefresh, refreshKey = 0 }: HistoryProps) {
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const [collapsedDates, setCollapsedDates] = useState<Set<string>>(() => new Set());
  const [now, setNow] = useState(() => Date.now());
  const listRef = useRef<HTMLDivElement>(null);
  const moreRef = useRef<HTMLDivElement>(null);
  const searchButtonRef = useRef<HTMLButtonElement>(null);
  const { historyItems, isLoading, hasMore, error, loadMore } = useHistoryPanel({ selectedSessionId, refreshKey });

  useEffect(() => {
    const timer = window.setInterval(() => setNow(Date.now()), 60_000);
    return () => window.clearInterval(timer);
  }, []);

  useEffect(() => {
    if (!hasMore || isLoading || error) return;
    const observer = new IntersectionObserver(entries => {
      if (entries.some(entry => entry.isIntersecting)) void loadMore();
    }, { root: listRef.current, rootMargin: "100px" });
    if (moreRef.current) observer.observe(moreRef.current);
    return () => observer.disconnect();
  }, [hasMore, isLoading, error, loadMore]);

  const closeSearch = () => {
    setIsSearchOpen(false);
    requestAnimationFrame(() => searchButtonRef.current?.focus());
  };
  const handleDeleteChat = async (sessionId: number) => {
    await deleteHistorySession(sessionId);
    onDeleteSession?.(sessionId);
    onHistoryRefresh?.();
  };
  const historyGroups = new Map<string, HistoryItem[]>();
  for (const item of historyItems) {
    const label = formatHistoryDateGroup(item.recentAtTimestamp, now);
    const group = historyGroups.get(label) ?? [];
    group.push(item);
    historyGroups.set(label, group);
  }

  return (
    <div className={styles.historyRoot}>
      <button type="button" className={styles.newChatButton} onClick={onStartNewChat} aria-label="새 질문 시작">
        <Plus size={18} aria-hidden="true" /><span>새 질문</span>
      </button>
      <div className={styles.headerRow}>
        <h2 className={styles.historyTitle}>질문 이력</h2>
        <button ref={searchButtonRef} type="button" className={styles.searchButton} onClick={() => setIsSearchOpen(true)} aria-label="질문 이력 검색" aria-haspopup="dialog">
          <Search size={18} aria-hidden="true" />
        </button>
      </div>
      <div ref={listRef} className={styles.historyList} aria-label="질문 이력 목록" tabIndex={0}>
        {Array.from(historyGroups, ([label, items]) => {
          const timestamp = items[0].recentAtTimestamp;
          const dateKey = Number.isFinite(timestamp)
            ? new Intl.DateTimeFormat("sv-SE", { timeZone: "Asia/Seoul" }).format(timestamp)
            : "unknown";
          const isCollapsed = collapsedDates.has(dateKey);
          const listId = `history-date-${dateKey}`;
          return (
            <section key={dateKey} className={styles.dateGroup} aria-label={label}>
              <h3 className={styles.dateHeading}>
                <button type="button" className={styles.dateToggle} aria-expanded={!isCollapsed} aria-controls={listId}
                  tabIndex={-1}
                  onKeyDown={event => {
                    if (event.key === "Enter" || event.key === " ") event.preventDefault();
                  }}
                  onClick={() => setCollapsedDates(previous => {
                    const next = new Set(previous);
                    if (next.has(dateKey)) next.delete(dateKey);
                    else next.add(dateKey);
                    return next;
                  })}>
                  <span>{label}</span>
                  {isCollapsed ? <ChevronRight size={14} aria-hidden="true" /> : <ChevronDown size={14} aria-hidden="true" />}
                </button>
              </h3>
              <div id={listId} hidden={isCollapsed}>
                {items.map(item => (
                  <HistoryCard key={item.id} item={item} onSelect={() => onSelectSession(item.id, item)} onDelete={handleDeleteChat} />
                ))}
              </div>
            </section>
          );
        })}
        {!isLoading && !error && historyItems.length === 0 && <p className={styles.emptyHistoryText}>질문 이력이 없습니다.</p>}
        <div ref={moreRef} className={styles.loadMore}>
          {isLoading ? <span role="status">불러오는 중…</span> : error ? (
            <div role="alert">{error}<button type="button" onClick={() => void loadMore()}>다시 시도</button></div>
          ) : hasMore ? <button type="button" onClick={() => void loadMore()}>더 보기</button>
            : historyItems.length > 0 ? <span>모든 이력을 확인했습니다.</span> : null}
        </div>
      </div>
      {isSearchOpen && <HistorySearch onClose={closeSearch} onSelect={item => { onSelectSession(item.id, item); closeSearch(); }} />}
    </div>
  );
}
