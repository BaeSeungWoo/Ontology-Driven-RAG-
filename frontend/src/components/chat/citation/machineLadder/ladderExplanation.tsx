import { useContext, useMemo } from "react";
import useLadderSignals from "@/hooks/useLadderSignals";
import { getMachineSignals, type MachineLadderNet } from "@/services/ladderApi";
import { LadderEvidence, useLadderAnalysis } from "../../figureExplanationProvider";
import figure from "../../figureExplanation.module.css";

export default function LadderExplanation({ messageId, addresses, nets, paused }: {
  addresses: ReadonlySet<string>; messageId: number; nets: MachineLadderNet[]; paused: boolean;
}) {
  const signals = useMemo(() => getMachineSignals(nets), [nets]);
  const { snapshot, error } = useLadderSignals(signals, paused);
  const chunks = useContext(LadderEvidence);
  const { open } = useLadderAnalysis();
  const readings = new Map(snapshot?.signals.map(item => [item.address, item.value]));
  const hasValues = signals.some(address => readings.get(address) != null);

  function explain() {
    if (!nets.length || !snapshot || !hasValues) return;
    open({
      message_id: messageId, machine_code: snapshot.machine.code, program: nets[0].program, read_completed: snapshot.read_completed,
      signals: Object.fromEntries(signals.map(address => [address, readings.get(address) ?? null])),
      evidence_count: nets.length,
      nets,
    }, { addresses, chunks });
  }

  return <>
    <button type="button" className={figure.explainButton} disabled={!nets.length || !hasValues} aria-haspopup="dialog" onClick={explain}>
      <span className={figure.aiBadge} aria-hidden="true">AI</span> 수신 신호로 질문 분석
    </button>
    {!nets.length ? <small role="status">질문 근거와 일치하는 장비 회로를 찾지 못했습니다.</small>
      : !hasValues && <small role="status">{error || "질문 관련 신호 수신 대기 중"}</small>}
  </>;
}
