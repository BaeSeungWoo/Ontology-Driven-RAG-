import { useEffect, useRef, useState } from "react";
import { Workflow, X } from "lucide-react";
import type { LadderNode } from "@/types/ladder";
import type { ChatChunk } from "@/types/chatApi";
import { getLadderSignals } from "@/services/ladderApi";
import MachineLadderView from "./machineLadder/machineLadderView";
import styles from "./citation.module.css";

// 입력 접점만 모은다. 자기유지 회로에서는 같은 주소가 입력과 출력 양쪽에 표시될 수 있다.
function inputAddresses(node: LadderNode): string[] {
  if (node.kind === "contact") return [node.addr];
  if (node.kind === "function") return inputAddresses(node.input);
  return node.children.flatMap(inputAddresses);
}

export default function LadderSignalOverlay({ chunks, onClose }: {
  chunks: ChatChunk[]; onClose: () => void;
}) {
  const [headerHost, setHeaderHost] = useState<HTMLDivElement | null>(null);
  const dialogRef = useRef<HTMLDialogElement>(null);
  const [selectedIndex, setSelectedIndex] = useState<number | null>(null);
  const selected = chunks.find(chunk => chunk.index === selectedIndex);
  const relatedAddresses = getLadderSignals(selected?.metadata.ladder_diagram).map(item => item.address);

  useEffect(() => {
    const dialog = dialogRef.current;
    const previousFocus = document.activeElement;
    dialog?.showModal();
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      dialog?.close();
      document.body.style.overflow = previousOverflow;
      if (previousFocus instanceof HTMLElement && previousFocus.isConnected) previousFocus.focus();
    };
  }, []);

  return <dialog ref={dialogRef} className={styles.ladderSignalDialog} aria-labelledby="ladder-signal-title"
    onCancel={event => { event.preventDefault(); onClose(); }}>
    <div className={styles.ladderSignalContent}>
      <header className={styles.ladderSignalHeader}>
        <h2 id="ladder-signal-title">연결 장비 래더 신호 확인</h2>
        <div ref={setHeaderHost} className={styles.ladderHeaderStatus} />
        <button type="button" className={styles.pdfModalIconButton} onClick={onClose} aria-label="래더 신호 확인 닫기">
          <X size={22} aria-hidden="true" />
        </button>
      </header>
      <div className={styles.ladderWorkspace}>
        <aside className={styles.ladderEvidenceList} aria-label="질문의 래더 근거">
          {chunks.map((chunk, index) => {
            const diagram = chunk.metadata.ladder_diagram;
            const isSelected = selected?.index === chunk.index;
            return <button type="button" key={chunk.index}
              aria-pressed={isSelected} onClick={() => setSelectedIndex(value => value === chunk.index ? null : chunk.index)}>
              <Workflow size={16} aria-hidden="true" />
              <span className={styles.ladderEvidenceSummary}>래더 근거 {index + 1} · {diagram?.nblock ?? "원문"}
                {diagram?.status === "supported" ? <>
                  <span>입력: {[...new Set(inputAddresses(diagram.logic))].join(", ") || "없음"}</span>
                  <span>출력: {(diagram.coils ?? [diagram.coil]).map(coil => coil.addr).join(", ")}</span>
                </> : <span>입출력: 원문 확인</span>}
                <small>{String(chunk.metadata.source_doc_name ?? "문서명 없음")}</small>
              </span>
            </button>;
          })}
          {selected && <div className={styles.ladderEvidenceDetail}>
            <p>근거와 주소 집합이 일치하는 출력 회로로 자동 이동하고 해당 NET을 파란 배경으로 표시합니다. 사용처 탐색은 선택 주소를 주황 테두리로 표시합니다.</p>
            <details><summary>근거 원문</summary><p>{selected.document}</p></details>
          </div>}
        </aside>
        <MachineLadderView relatedAddresses={relatedAddresses} headerHost={headerHost} />
      </div>
    </div>
  </dialog>;
}
