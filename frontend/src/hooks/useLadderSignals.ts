import { useEffect, useState } from "react";
import axios from "axios";
import { useMachine } from "@/components/machineProvider";
import { readTestSignals, type PmcSnapshot } from "@/services/ladderApi";

export default function useLadderSignals(addresses: string[], paused: boolean) {
  const { executionMachineCode: machineCode, status } = useMachine();
  const [snapshot, setSnapshot] = useState<PmcSnapshot | null>(null);
  const [error, setError] = useState("");
  const [isReading, setIsReading] = useState(false);

  useEffect(() => {
    if (paused || !addresses.length || !machineCode || machineCode === "ALL" || status !== "ready") return;
    setSnapshot(null);
    setError("");
    setIsReading(false);
    let active = true;
    let reading = false;
    let timer: ReturnType<typeof setTimeout>;
    const controller = new AbortController();
    const poll = async () => {
      if (!active || reading || document.hidden) return;
      reading = true;
      setIsReading(true);
      try {
        const result = await readTestSignals(addresses, controller.signal, machineCode);
        if (active) { setSnapshot(result); setError(""); }
      } catch (err) {
        if (active) {
          // 이전 ON 값을 현재 상태로 오인하지 않도록 실패 시 색칠 근거를 비운다.
          setSnapshot(null);
          const detail = axios.isAxiosError(err) ? err.response?.data?.detail : null;
          setError(typeof detail === "string" ? detail : "신호를 읽지 못했습니다. 에이전트 연결을 확인하세요.");
        }
      } finally {
        reading = false;
        // 응답이 끝난 뒤 예약하여 느린 장비에서도 요청이 겹치지 않게 한다.
        if (active) { setIsReading(false); timer = setTimeout(poll, 2000); }
      }
    };
    const onVisible = () => { clearTimeout(timer); if (!document.hidden) void poll(); };
    void poll();
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      active = false;
      // 일시정지·페이지 변경·닫기 시 진행 중인 조회와 다음 예약을 함께 취소한다.
      controller.abort();
      clearTimeout(timer);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, [paused, addresses, machineCode, status]);

  return { snapshot: status === "ready" && snapshot?.machine.code === machineCode ? snapshot : null, error, isReading };
}
