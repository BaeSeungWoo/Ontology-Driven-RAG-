import { useEffect, useMemo, useRef, useState } from "react";
import axios from "axios";
import { createPortal } from "react-dom";
import { getMachineNodeSignals, getMachineSignals, getTestLadder, type MachineLadderDocument, type MachineLadderNet } from "@/services/ladderApi";
import useLadderSignals from "@/hooks/useLadderSignals";
import LadderNetSvg from "./components/LadderNetSvg";
import { requiredRailGap } from "./utils/ladderLayoutUtils";
import styles from "../citation.module.css";

const NETS_PER_PAGE = 10;
type SelectedSignal = { address: string; symbol: string; comment: string };
type Destination = { netIndex: number; revision: number };

function LiveCanvas({ nets, highlightedNetIndexes, selectedAddress, focusedNetIndex, onAddressSelect, destination, headerHost, paused, onTogglePaused }: {
  paused: boolean; onTogglePaused: () => void;
  headerHost: HTMLDivElement | null;
  nets: MachineLadderNet[]; highlightedNetIndexes: number[]; selectedAddress: string;
  focusedNetIndex: number | null;
  onAddressSelect: (address: string, netIndex: number) => void; destination: Destination | null;
}) {
  const canvasRef = useRef<HTMLDivElement>(null);
  // 페이지 전환으로 SVG가 렌더링된 뒤 내부 스크롤만 이동한다.
  useEffect(() => {
    const canvas = canvasRef.current;
    const target = canvas?.querySelector<HTMLElement>(`[data-net="${destination?.netIndex}"]`);
    if (canvas && target) {
      canvas.scrollTop += target.getBoundingClientRect().top - canvas.getBoundingClientRect().top;
      canvas.scrollLeft = 0;
    }
  }, [destination]);
  const addresses = useMemo(() => getMachineSignals(nets), [nets]);
  const { snapshot, error, isReading } = useLadderSignals(addresses, paused);
  const [zoom, setZoom] = useState(1);
  const [selected, setSelected] = useState<SelectedSignal | null>(null);
  const knownSet = new Set(snapshot?.signals.filter(item => item.value !== null).map(item => item.address));
  const energizedSet = new Set(snapshot?.signals.filter(item => item.value === 1).map(item => item.address));
  const values = new Map(snapshot?.signals.map(item => [item.address, item]));
  const railGap = Math.max(900, ...nets.map(requiredRailGap));
  const selectedValue = selected ? values.get(selected.address)?.value : null;
  const state = paused ? "일시정지 · 마지막 수신 상태" : isReading ? "갱신 중"
    : !snapshot ? "연결 대기" : knownSet.size === addresses.length ? "실시간 수신 중" : "일부 신호 미확인";

  // 조회 상태와 조작은 캔버스가 소유하고, 표시는 오버레이 헤더에 배치한다.
  return <>
    {headerHost && createPortal(<>
    <div className={styles.ladderLiveToolbar}>
      <div><strong>{snapshot ? `${snapshot.machine.name} · ${snapshot.machine.code} · ${snapshot.machine.ip}` : "M019 테스트 장비"}</strong>
        <p role="status">{state} · {knownSet.size}/{addresses.length}개 주소 확인
          {snapshot && ` · ${new Date(snapshot.read_completed).toLocaleTimeString("ko-KR", { timeZone: "Asia/Seoul" })} KST`}</p>
      </div>
      <div className={styles.ladderCanvasActions}>
        <label>배율 <select aria-label="래더 배율" value={zoom} onChange={event => setZoom(Number(event.target.value))}>
          {[0.6, 0.8, 1, 1.2, 1.5].map(value => <option key={value} value={value}>{Math.round(value * 100)}%</option>)}
        </select></label>
        <button type="button" className={styles.openDocumentButton} disabled={!addresses.length}
          onClick={onTogglePaused}>{paused ? "조회 재개" : "일시정지"}</button>
      </div>
    </div>
    <p className={styles.ladderLiveNote}><span className={styles.ladderOnLegend}>●</span> 녹색: a접점 1 / b접점 0 / 코일 1 · 미수신 주소는 색칠하지 않습니다. 선 색상은 파일 논리로 계산합니다.</p>
    {error && <p className={styles.documentError} role="alert">{error}</p>}
    </>, headerHost)}
    <div ref={canvasRef} className={styles.machineCanvas} role="region" aria-label="장비 전체 래더 실시간 신호" tabIndex={0}>
      {nets.map(net => <div key={net.netIndex} data-net={net.netIndex}
        className={styles.ladderNetFrame} data-focused={Boolean(selectedAddress && focusedNetIndex === net.netIndex)}>
        {selectedAddress && focusedNetIndex === net.netIndex && <span className={styles.ladderFocusBadge}>현재 탐색 · NET {net.netIndex} · {selectedAddress}</span>}
        <LadderNetSvg net={net} energizedSet={energizedSet} knownSet={knownSet}
        railGap={railGap} zoom={zoom} displayMode="both" selectedKey={null} selectedAddress={selectedAddress}
        highlighted={highlightedNetIndexes.includes(net.netIndex)}
        onSelect={(element: SelectedSignal) => {
          const deselect = selectedAddress === element.address && focusedNetIndex === net.netIndex;
          setSelected(deselect ? null : element);
          onAddressSelect(deselect ? "" : element.address, net.netIndex);
        }}
        onJump={undefined} /></div>)}
    </div>
    {selected && selectedAddress && <p className={styles.ladderSelectedSignal}><strong>{selected.address} · {selected.symbol}</strong>
      {` — ${selectedValue === 1 ? "ON · 1" : selectedValue === 0 ? "OFF · 0" : "미확인"}`} · {selected.comment}</p>}
    <details className={styles.ladderSource}>
      <summary>주소별 수신값 ({addresses.length})</summary>
      <div className={styles.ladderSignalTableWrap}><table className={styles.ladderSignalTable}>
        <thead><tr><th>PMC 주소</th><th>M019 수신값</th></tr></thead>
        <tbody>{addresses.map(address => {
          const result = values.get(address);
          return <tr key={address}><td>{address}</td><td>{result?.value === 1 ? "ON · 1" : result?.value === 0 ? "OFF · 0" : "미확인"}
            {result?.error && <small>{result.error}</small>}</td></tr>;
        })}</tbody>
      </table></div>
    </details>
  </>;
}

export default function MachineLadderView({ relatedAddresses, headerHost }: {
  relatedAddresses: string[]; headerHost: HTMLDivElement | null;
}) {
  const [document, setDocument] = useState<MachineLadderDocument | null>(null);
  const [error, setError] = useState("");
  const [retry, setRetry] = useState(0);
  // 페이지별 캔버스가 재생성되어도 사용자가 정한 조회 상태는 유지한다.
  const [paused, setPaused] = useState(false);
  const [programIndex, setProgramIndex] = useState(0);
  const [page, setPage] = useState(0);
  const [selectedAddress, setSelectedAddress] = useState("");
  const [focusedNet, setFocusedNet] = useState<{ programIndex: number; netIndex: number } | null>(null);
  const [destination, setDestination] = useState<Destination | null>(null);
  const addressKey = [...relatedAddresses].sort().join(",");
  const locations = useMemo(() => document?.ladders.flatMap((program, programIndex) =>
    program.nets.filter(net => net.outputs.length > 0).map((net, index) => ({
      programIndex, label: program.label, page: Math.floor(index / NETS_PER_PAGE), net,
    }))) ?? [], [document]);
  // 파란 배경과 자동 이동은 근거의 전체 주소 집합으로만 결정한다(논리 동등성 검증은 아님).
  const exactMatches = useMemo(() => locations.filter(({ net }) => addressKey && net.outputs.some(output =>
    getMachineNodeSignals([output]).sort().join(",") === addressKey)), [locations, addressKey]);
  // 주황 강조는 별도의 선택 주소이며, 근거 일치 결과를 변경하지 않는다.
  const usages = locations.filter(({ net }) => selectedAddress && getMachineSignals([net]).includes(selectedAddress));
  const jump = (location: typeof locations[number]) => {
    setFocusedNet({ programIndex: location.programIndex, netIndex: location.net.netIndex });
    setProgramIndex(location.programIndex);
    setPage(location.page);
    // 같은 NET을 다시 선택해도 스크롤을 되돌릴 수 있도록 이동 요청을 구분한다.
    setDestination(value => ({ netIndex: location.net.netIndex, revision: (value?.revision ?? 0) + 1 }));
  };
  // 근거/문서가 바뀔 때만 최초 일치 위치로 이동하고 사용자의 탐색 중에는 위치를 유지한다.
  const [previousMatches, setPreviousMatches] = useState(exactMatches);
  if (previousMatches !== exactMatches) {
    setPreviousMatches(exactMatches);
    setSelectedAddress("");
    const first = exactMatches[0];
    if (first) {
      setProgramIndex(first.programIndex);
      setPage(first.page);
      setDestination(value => ({ netIndex: first.net.netIndex, revision: (value?.revision ?? 0) + 1 }));
    }
  }
  const program = document?.ladders[programIndex];
  const nets = useMemo(() => program?.nets.filter(net => net.outputs.length > 0) ?? [], [program]);
  const visibleNets = useMemo(() => nets.slice(page * NETS_PER_PAGE, page * NETS_PER_PAGE + NETS_PER_PAGE), [nets, page]);

  useEffect(() => {
    const controller = new AbortController();
    getTestLadder(controller.signal).then(result => {
      if (!controller.signal.aborted) setDocument(result);
    }).catch(err => {
      if (controller.signal.aborted) return;
      const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
      setError(typeof detail === "string" ? detail : "장비 래더 파일을 불러오지 못했습니다.");
    });
    return () => controller.abort();
  }, [retry]);

  return <section className={styles.machineLadderView} aria-label="장비 래더 뷰어">
    {error ? <div role="alert"><p>{error}</p><button type="button" className={styles.openDocumentButton}
      onClick={() => { setError(""); setRetry(value => value + 1); }}>다시 불러오기</button></div>
      : !document ? <p role="status">M019 장비의 전체 래더를 불러오는 중…</p> : <>
        <aside className={styles.ladderNavigatorPanel} aria-label="래더 탐색 패널">
          <div className={styles.ladderFileToolbar}>
            <strong>장비 전체 래더 · {document.meta.filename}</strong>
            <label>프로그램 <select aria-label="래더 프로그램" value={programIndex}
              onChange={event => { setProgramIndex(Number(event.target.value)); setPage(0); }}>
              {document.ladders.map((item, index) => <option key={item.name} value={index}>{item.label}</option>)}
            </select></label>
            <span>NET {nets.length ? page * NETS_PER_PAGE + 1 : 0}–{Math.min(page * NETS_PER_PAGE + NETS_PER_PAGE, nets.length)} / {nets.length}</span>
            <button type="button" disabled={page === 0} onClick={() => setPage(value => value - 1)}>이전 회로</button>
            <button type="button" disabled={(page + 1) * NETS_PER_PAGE >= nets.length} onClick={() => setPage(value => value + 1)}>다음 회로</button>
          </div>
          {addressKey && <div className={styles.ladderNavigation} aria-label="근거 일치 회로">
            <span>{exactMatches.length ? `주소 집합 일치 ${exactMatches.length}곳 · 논리 동일 여부는 별도 확인` : "주소 집합이 일치하는 회로가 없습니다."}</span>
            {exactMatches.map(location => <button type="button" key={`${location.programIndex}:${location.net.netIndex}`}
              onClick={() => { setSelectedAddress(""); jump(location); }}>{location.label} · NET {location.net.netIndex}</button>)}
          </div>}
          {selectedAddress && <div className={styles.ladderNavigation} role="region" aria-label="신호 사용처 탐색">
            <strong>{selectedAddress} 사용처 · {usages.length}곳</strong>
            <span>진한 주황: 현재 탐색 위치 · 옅은 점선: 다른 회로의 같은 주소. 출력은 다른 접점 조건에도 영향을 받습니다.</span>
            <button type="button" onClick={() => setSelectedAddress("")}>탐색 닫기</button>
            <div className={styles.ladderUsageList}>{usages.map(location => {
              const written = location.net.outputs.some(output => output.address === selectedAddress);
              const read = location.net.outputs.some(output => output.input && getMachineNodeSignals([output.input]).includes(selectedAddress));
              return <button type="button" key={`${location.programIndex}:${location.net.netIndex}`}
                aria-pressed={focusedNet?.programIndex === location.programIndex && focusedNet.netIndex === location.net.netIndex}
                onClick={() => jump(location)}>{location.label} · NET {location.net.netIndex} · {read ? "접점 사용" : ""}{read && written ? " / " : ""}{written ? "출력" : ""}
                {` → ${location.net.outputs.filter(output => getMachineNodeSignals([output]).includes(selectedAddress)).map(output => output.address || output.subName || "기능 명령").join(", ")}`}</button>;
            })}</div>
          </div>}
          {!selectedAddress && <p className={styles.ladderLiveNote}>회로의 접점이나 코일을 선택하면 전체 사용처가 여기에 표시됩니다.</p>}
        </aside>
        <div className={styles.ladderCircuitPanel}>
          {nets.length ? <LiveCanvas key={`${programIndex}-${page}`} nets={visibleNets} headerHost={headerHost}
            paused={paused} onTogglePaused={() => setPaused(value => !value)}
            highlightedNetIndexes={exactMatches.filter(location => location.programIndex === programIndex).map(location => location.net.netIndex)}
            selectedAddress={selectedAddress} focusedNetIndex={focusedNet?.programIndex === programIndex ? focusedNet.netIndex : null}
            onAddressSelect={(address, netIndex) => {
              setSelectedAddress(address);
              setFocusedNet(address ? { programIndex, netIndex } : null);
            }} destination={destination} />
            : <p>이 프로그램에는 표시할 회로가 없습니다.</p>}
        </div>
      </>}
  </section>;
}
