import { defineConfig } from "vitest/config";
import { fileURLToPath } from "node:url";

export default defineConfig({
  resolve: { alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) } },
  esbuild: { jsx: "automatic" },
  test: { environment: "jsdom", include: ["tests/voice*.test.{ts,tsx}", "tests/graphEvidence.test.tsx"], restoreMocks: true },
});
