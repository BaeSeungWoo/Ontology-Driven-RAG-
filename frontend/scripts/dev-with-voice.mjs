import { spawn, execFileSync } from "node:child_process";
import { createRequire } from "node:module";
import nextEnv from "@next/env";
import { createVoiceRelay } from "./voice-relay.mjs";

nextEnv.loadEnvConfig(process.cwd(), true);
const relay = createVoiceRelay({
  upstream: process.env.VOICE_PROXY_URL || "https://rag.waff.co.kr:9443",
  username: process.env.VOICE_PROXY_USERNAME || "",
  password: process.env.VOICE_PROXY_PASSWORD || "",
});
let child;
let stopping = false;
function stop(code = 0) {
  if (stopping) return;
  stopping = true;
  relay.close();
  if (child && child.exitCode === null) {
    if (process.platform === "win32") {
      try { execFileSync("taskkill", ["/pid", String(child.pid), "/T", "/F"], { stdio: "ignore", windowsHide: true }); } catch { /* Already stopped. */ }
    } else child.kill("SIGTERM");
  }
  process.exitCode = code;
}
process.on("SIGINT", () => stop());
process.on("SIGTERM", () => stop());
relay.server.on("error", error => {
  console.error(`[voice relay] 시작 실패: ${error.code || "설정 오류"} (127.0.0.1:3002)`);
  stop(1);
});
relay.server.listen(3002, "127.0.0.1", () => {
  console.log("[voice relay] http://127.0.0.1:3002 → 원격 HTTPS 음성 프록시");
  if (!process.env.VOICE_PROXY_USERNAME || !process.env.VOICE_PROXY_PASSWORD) {
    console.log("[voice relay] .env.local에 VOICE_PROXY_USERNAME / VOICE_PROXY_PASSWORD를 입력하세요. 일반 채팅은 사용할 수 있습니다.");
  }
  const require = createRequire(import.meta.url);
  child = spawn(process.execPath, [require.resolve("next/dist/bin/next"), "dev", "--port", "3000"], {
    stdio: "inherit", windowsHide: true,
    env: { ...process.env, NEXT_PUBLIC_VOICE_API_URL: "http://127.0.0.1:3002" },
  });
  child.on("error", () => stop(1));
  child.on("exit", code => stop(code ?? 1));
});
