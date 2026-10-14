export const runtime = "nodejs";

export async function GET(request: Request) {
  const code = process.env.MCODE?.trim() || "";
  if (!/^[A-Za-z0-9_-]+$/.test(code)) {
    return Response.json({ detail: "테스트 장비 코드 설정이 올바르지 않습니다." }, { status: 503 });
  }
  const base = (process.env.NEXT_PUBLIC_API_URL || process.env.API_PROXY_TARGET || "http://127.0.0.1:8000").replace(/\/+$/, "");
  try {
    const response = await fetch(`${base}/api/ladder/test-document?machine_code=${encodeURIComponent(code)}`, {
      cache: "no-store",
      signal: AbortSignal.any([request.signal, AbortSignal.timeout(12000)]),
    });
    if (!response.ok) {
      return Response.json({ detail: response.status === 404
        ? `${code}.LAD 파일을 백엔드에서 찾을 수 없습니다.`
        : "백엔드에서 래더 파일을 불러오지 못했습니다." }, { status: response.status });
    }
    const document = await response.json();
    // 구버전 백엔드가 장비 코드를 무시해 다른 회로를 반환하는 경우도 차단한다.
    if (document.meta?.machine_code !== code) {
      return Response.json({ detail: "래더 파일의 장비 코드가 다릅니다. 백엔드 업데이트를 확인하세요." }, { status: 502 });
    }
    return Response.json(document);
  } catch {
    return Response.json({ detail: "래더 파일을 제공하는 백엔드에 연결할 수 없습니다." }, { status: 502 });
  }
}
