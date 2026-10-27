// Local Agent requests keep the same IP-based machine scope as the remote chat API.
export async function authorizeMachine(request: Request, requestedCode: unknown): Promise<string | Response> {
  const code = typeof requestedCode === "string" ? requestedCode.trim() : "";
  if (!/^[A-Za-z0-9_-]+$/.test(code) || code === "ALL") {
    return Response.json({ detail: "조회할 장비를 선택하세요." }, { status: 422 });
  }
  const base = (process.env.NEXT_PUBLIC_API_URL || process.env.API_PROXY_TARGET || "http://127.0.0.1:8000").replace(/\/+$/, "");
  // Next sets X-Forwarded-For from the incoming socket. For a browser on the same
  // PC, omit loopback so the backend sees this frontend PC's network address.
  const clientIp = request.headers.get("x-forwarded-for")?.split(",")[0].trim().replace(/^::ffff:/, "");
  const headers: Record<string, string> = {};
  if (clientIp && clientIp !== "::1" && !clientIp.startsWith("127.")) headers["X-Forwarded-For"] = clientIp;
  try {
    const response = await fetch(`${base}/api/prompts/machines`, {
      headers, cache: "no-store", signal: AbortSignal.any([request.signal, AbortSignal.timeout(5000)]),
    });
    if (!response.ok) throw new Error();
    const machines: { machine_code: string; can_select: boolean }[] = await response.json();
    if (!machines.some(machine => machine.machine_code === code && machine.can_select === true)) {
      return Response.json({ detail: "해당 장비에 접근할 수 없습니다." }, { status: 403 });
    }
    return code;
  } catch {
    return Response.json({ detail: "백엔드에서 장비 접근 권한을 확인할 수 없습니다." }, { status: 502 });
  }
}
