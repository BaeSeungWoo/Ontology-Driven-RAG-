import styles from "./citation.module.css";

type CitationProps = {
  isCollapsed: boolean;
  onToggle: () => void;
};

export default function Citation({ isCollapsed, onToggle }: CitationProps) {
  return (
    <div className={styles.citationRoot}>
      <div
        className={`${styles.citationHeader} ${
          isCollapsed ? styles.citationHeaderCollapsed : ""
        }`}
      >
        {!isCollapsed && <h2 className="pane-title">인용 근거</h2>}
        <button
          type="button"
          className={styles.citationToggle}
          onClick={onToggle}
          aria-expanded={!isCollapsed}
          aria-label={isCollapsed ? "Expand citation panel" : "Collapse citation panel"}
        >
          {isCollapsed ? "+" : "-"}
        </button>
      </div>
      {!isCollapsed && (
        <p className="pane-placeholder">Reference and evidence panel</p>
      )}
    </div>
  );
}
