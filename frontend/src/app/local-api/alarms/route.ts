export const runtime = "nodejs";

export async function GET(request: Request) {
  const code = process.env.MCODE?.trim() || "";
  if (!/^[A-Za-z0-9_-]+$/.test(code)) {
    return Response.json({ detail: "장비 코드 설정이 올바르지 않습니다." }, { status: 503 });
  }
  const base = (process.env.LADDER_AGENT_URL || "http://127.0.0.1:5001").replace(/\/+$/, "");
  try {
    const response = await fetch(`${base}/api/agent/fanuc/machines/${code}`, {
      cache: "no-store",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(5000)]),
    });
    if (!response.ok) throw new Error();
    const machine = await response.json();
    if (machine.MachineCode !== code) throw new Error();
    const tags = machine.Tags;
    // Agent의 OccurDate는 한국 현지 시각이며 시간대 정보가 없다.
    const rawTime = typeof tags?.OccurDate === "string" ? tags.OccurDate : "";
    const collectedAt = /^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}(\.\d{1,3})?$/.test(rawTime)
      ? `${rawTime.replace(" ", "T")}+09:00` : "";
    const age = Date.now() - Date.parse(collectedAt);
    if (machine.IsConnected !== true || String(tags?.MachineStatus) === "3") {
      return Response.json({ detail: `${code} 장비 연결을 확인할 수 없습니다.` }, { status: 503 });
    }
    if (!Number.isFinite(age) || age > 15000 || age < -5000) {
      return Response.json({ detail: `${code} 장비 데이터 갱신이 지연되고 있습니다.` }, { status: 503 });
    }
    const clean = (value: string) => value.replace(/\0/g, "").trim();
    const alarms: { type: "system" | "operate"; code: string; message: string }[] = [];
    for (const [type, codeTag, messageTag] of [
      ["system", "AlarmCode", "AlarmMsg"], ["operate", "OperateCode", "OperateMsg"],
    ] as const) {
      // 누락된 태그를 알람 해제로 오인하지 않는다.
      if (typeof tags[codeTag] !== "string" || typeof tags[messageTag] !== "string") {
        return Response.json({ detail: `${codeTag}/${messageTag}를 받지 못했습니다. Agent 버전과 수집 상태를 확인하세요.` }, { status: 502 });
      }
      const alarmCode = clean(tags[codeTag]);
      const message = clean(tags[messageTag]);
      if (alarmCode && alarmCode !== "-") alarms.push({ type, code: alarmCode, message: message === "-" ? "" : message });
    }
    return Response.json({
      machine: { code, name: machine.MachineName || code },
      collectedAt,
      alarms,
    });
  } catch {
    return Response.json({ detail: "로컬 Agent에서 알람 정보를 받지 못했습니다." }, { status: 502 });
  }
}
