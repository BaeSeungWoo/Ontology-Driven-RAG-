import { memo } from "react";
import { getMachineSignals, type MachineLadderNet } from "@/services/ladderApi";
import LadderNetSvg from "./components/LadderNetSvg";
import { requiredRailGap } from "./utils/ladderLayoutUtils";
import styles from "../citation.module.css";

export default memo(function AnalysisCircuits({ nets, signals, onOpen }: {
  onOpen?: (net: MachineLadderNet) => void; nets: MachineLadderNet[]; signals: Record<string, 0 | 1 | null>;
}) {
  const readings = Object.entries(signals);
  const known = new Set(readings.filter(([, value]) => value !== null).map(([address]) => address));
  const on = new Set(readings.filter(([, value]) => value === 1).map(([address]) => address));
  return <aside className={styles.analysisCircuits} aria-label="질문 분석에 사용한 회로">
    <small className={styles.snapshotNote}>분석 버튼을 눌렀을 때의 수신값입니다.</small>
    {nets.map((net, index) => {
      const missing = getMachineSignals([net]).filter(address => !known.has(address));
      return <figure key={`${net.program}:${net.netIndex}`}>
        <figcaption><strong>{index === 0 ? "기능 회로" : "입력 조건 회로"}</strong> · {net.program} · NET {net.netIndex}</figcaption>
        <button type="button" disabled={!onOpen} aria-label={`${net.program} · NET ${net.netIndex} 회로로 이동`}
          title="전체 래더에서 이 회로 보기" onClick={() => onOpen?.(net)}
          className={`${styles.machineCanvas} ${styles.analysisCircuitCanvas}`}>
          <LadderNetSvg net={net} knownSet={known} energizedSet={on} railGap={requiredRailGap(net, 180)}
            zoom={0.95} selectedKey={null} onSelect={undefined} onJump={undefined} />
        </button>
        {missing.length > 0 && <small>미수신 · {missing.join(", ")}</small>}
      </figure>;
    })}
  </aside>;
});
