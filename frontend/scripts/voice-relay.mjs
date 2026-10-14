import { createServer } from "node:http";
import WebSocket, { WebSocketServer } from "ws";

// Only this laptop's local UI may use the server-side proxy credentials.
export function createVoiceRelay({ upstream, username, password }) {
  const target = new URL(upstream);
  if (target.protocol !== "https:" || target.username || target.password) {
    throw new Error("VOICE_PROXY_URL must be an HTTPS URL without credentials.");
  }
  const origins = new Set(["http://localhost:3000", "http://127.0.0.1:3000"]);
  const authorization = `Basic ${Buffer.from(`${username}:${password}`).toString("base64")}`;
  const configured = Boolean(username && password);
  const headers = origin => ({ Origin: origin, Authorization: authorization });
  const error = (response, status, detail) => {
    response.writeHead(status, { "Content-Type": "application/json", "Cache-Control": "no-store" });
    response.end(JSON.stringify({ detail }));
  };
  const server = createServer(async (request, response) => {
    const origin = request.headers.origin;
    if (!origins.has(origin)) return error(response, 403, "로컬 화면에서만 음성 중계를 사용할 수 있습니다.");
    response.setHeader("Access-Control-Allow-Origin", origin);
    response.setHeader("Vary", "Origin");
    if (request.url !== "/api/voice/sessions") return error(response, 404, "음성 중계 경로가 아닙니다.");
    if (request.method === "OPTIONS") {
      response.writeHead(204, {
        "Access-Control-Allow-Methods": "POST",
        "Access-Control-Allow-Headers": "Content-Type",
      });
      return response.end();
    }
    if (request.method !== "POST") return error(response, 405, "POST 요청만 지원합니다.");
    if (!configured) return error(response, 503, "frontend/.env.local에 VOICE_PROXY_USERNAME과 VOICE_PROXY_PASSWORD를 입력하고 npm run dev를 다시 실행해 주세요.");
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), 15000);
    response.on("close", () => controller.abort());
    try {
      const result = await fetch(new URL("/api/voice/sessions", target), {
        method: "POST", headers: { ...headers(origin), "Content-Type": "application/json" },
        body: "{}", redirect: "error", signal: controller.signal,
      });
      if (result.status === 401) return error(response, 401, "음성 프록시 로그인 아이디 또는 비밀번호를 확인해 주세요.");
      const body = await result.json();
      response.writeHead(result.status, { "Content-Type": "application/json", "Cache-Control": "no-store" });
      response.end(JSON.stringify(body));
    } catch {
      if (!response.destroyed) error(response, 502, "원격 음성 프록시에 연결하지 못했습니다. 주소와 네트워크를 확인해 주세요.");
    } finally {
      clearTimeout(timeout);
    }
  });
  const sockets = new WebSocketServer({
    noServer: true, maxPayload: 32000, perMessageDeflate: false,
    handleProtocols: protocols => protocols.has("voice.v1") ? "voice.v1" : false,
  });
  server.on("upgrade", (request, socket, head) => {
    const protocols = String(request.headers["sec-websocket-protocol"] ?? "").split(",").map(value => value.trim());
    if (request.url !== "/api/voice/stream" || !origins.has(request.headers.origin) || !configured
      || !protocols.includes("voice.v1") || protocols.filter(value => /^ticket\.[\w-]+$/.test(value)).length !== 1) {
      socket.end("HTTP/1.1 403 Forbidden\r\nConnection: close\r\n\r\n");
      return;
    }
    sockets.handleUpgrade(request, socket, head, client => {
      const url = new URL("/api/voice/stream", target);
      url.protocol = "wss:";
      const remote = new WebSocket(url, protocols, {
        headers: headers(request.headers.origin), handshakeTimeout: 15000,
        maxPayload: 2 ** 20, perMessageDeflate: false,
      });
      const fail = () => {
        if (client.readyState === WebSocket.OPEN) {
          client.send(JSON.stringify({ type: "error", error: "원격 음성 연결이 종료되었습니다. 다시 시도해 주세요." }));
          client.close(1011);
        }
        remote.terminate();
      };
      client.on("error", () => remote.terminate());
      remote.on("error", fail);
      client.on("close", () => remote.terminate());
      remote.on("close", code => {
        if (client.readyState === WebSocket.OPEN) client.close(code === 1000 ? 1000 : 1011);
      });
      client.on("message", (data, binary) => {
        if (!binary || remote.readyState !== WebSocket.OPEN || remote.bufferedAmount > 160000) return fail();
        remote.send(data, { binary: true });
      });
      remote.on("message", (data, binary) => {
        if (client.readyState !== WebSocket.OPEN) return;
        if (client.bufferedAmount > 2 ** 20) return fail();
        client.send(data, { binary });
      });
    });
  });
  return {
    server,
    close() {
      for (const client of sockets.clients) client.terminate();
      sockets.close();
      server.close();
      server.closeAllConnections();
    },
  };
}
