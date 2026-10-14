export const runtime = "nodejs";

const ADDRESS = /^([GFYXRAKTCD])(\d{1,5})\.([0-7])$/;
const READ_ERROR = "신호 조회 실패 · 장비 연결 또는 주소 범위를 확인하세요.";

export async function POST(request: Request) {
  let addresses: string[];
  try {
    const body = await request.json();
    if (!Array.isArray(body.addresses) || !body.addresses.length || body.addresses.length > 128) throw new Error();
    addresses = [...new Set<string>(body.addresses.map((raw: unknown) => {
      const match = typeof raw === "string" ? ADDRESS.exec(raw.toUpperCase()) : null;
      if (!match || Number(match[2]) > 32767) throw new Error();
      return `${match[1]}${Number(match[2])}.${match[3]}`;
    }))];
  } catch {
    return Response.json({ detail: "PMC 주소를 1~128개 입력하세요. 예: X8.4" }, { status: 422 });
  }

  const code = process.env.MCODE?.trim() || "";
  if (!/^[A-Za-z0-9_-]+$/.test(code)) {
    return Response.json({ detail: "테스트 장비 코드 설정이 올바르지 않습니다." }, { status: 503 });
  }
  const base = (process.env.LADDER_AGENT_URL || "http://127.0.0.1:5001").replace(/\/+$/, "");
  const path = `${base}/api/agent/fanuc/machines/${code}`;
  async function read(url: string) {
    const response = await fetch(url, {
      cache: "no-store",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(5000)]),
    });
    if (!response.ok) throw new Error("Agent request failed");
    return response.json();
  }

  let machine;
  try {
    machine = await read(path);
    if (machine.MachineCode !== code) throw new Error();
  } catch {
    return Response.json({ detail: "로컬 Agent 또는 장비 목록에 연결할 수 없습니다." }, { status: 502 });
  }

  const areas = new Map<string, Set<number>>();
  for (const address of addresses) {
    const [, area, number] = ADDRESS.exec(address)!;
    if (!areas.has(area)) areas.set(area, new Set());
    areas.get(area)!.add(Number(number));
  }
  const values = new Map<string, number>();
  for (const [area, numbers] of areas) {
    const sorted = [...numbers].sort((a, b) => a - b);
    for (let i = 0; i < sorted.length; i++) {
      if (request.signal.aborted) return new Response(null, { status: 499 });
      const start = sorted[i];
      let end = start;
      while (i + 1 < sorted.length && sorted[i + 1] === end + 1 && end - start < 199) end = sorted[++i];
      try {
        const payload = await read(`${path}/pmc/range?pmcType=${area}&start=${start}&end=${end}`);
        if (payload.pmcType !== area || payload.start !== start || payload.end !== end) throw new Error();
        const raw = payload.data;
        let data: Uint8Array;
        if (typeof raw === "string" && /^(?:[A-Za-z0-9+/]{4})*(?:[A-Za-z0-9+/]{2}==|[A-Za-z0-9+/]{3}=)?$/.test(raw)) {
          data = Buffer.from(raw, "base64");
        } else if (Array.isArray(raw) && raw.every(value => Number.isInteger(value) && value >= 0 && value <= 255)) {
          data = Uint8Array.from(raw);
        } else throw new Error();
        if (data.length !== end - start + 1) throw new Error();
        data.forEach((value, offset) => values.set(`${area}${start + offset}`, value));
      } catch {
        // 미수신을 OFF로 바꾸지 않는다. 성공한 범위만 값에 포함한다.
      }
    }
  }

  return Response.json({
    test_mode: true,
    machine: { code, name: machine.MachineName ?? code, ip: machine.MachineIP ?? "" },
    read_completed: new Date().toISOString(),
    signals: addresses.map(address => {
      const [byte, bit] = address.split(".");
      const value = values.get(byte);
      return { address, value: value === undefined ? null : (value >> Number(bit)) & 1, error: value === undefined ? READ_ERROR : null };
    }),
  });
}
