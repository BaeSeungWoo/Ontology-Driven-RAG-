import { readFileSync } from "node:fs";
import { resolve } from "node:path";
import { runInNewContext } from "node:vm";
import { expect, it } from "vitest";

type Output = { type: string; buffer: ArrayBuffer; rms: number };
type Processor = { process: (inputs: Float32Array[][]) => boolean; port: { onmessage: (e: { data: string }) => void } };
function worklet(rate = 16000) {
  const messages: Output[] = [];
  let ProcessorClass!: new () => Processor;
  runInNewContext(readFileSync(resolve("public/voice/pcm-worklet.js"), "utf8"), {
    AudioWorkletProcessor: class { port = { postMessage: (m: Output) => messages.push(m) }; },
    sampleRate: rate,
    registerProcessor: (_: string, value: new () => Processor) => { ProcessorClass = value; },
  });
  return { processor: new ProcessorClass(), messages };
}
it("clips PCM, preserves little-endian byte order and flushes the short final frame before acknowledgement", () => {
  const { processor, messages } = worklet();
  processor.process([[Float32Array.from([-2, -1, 0, 1, 2])]]);
  expect(messages).toHaveLength(0);
  processor.port.onmessage({ data: "flush" });
  const view = new DataView(messages[0].buffer);
  expect(Array.from({ length: 5 }, (_, i) => view.getInt16(i * 2, true))).toEqual([-32768, -32768, 0, 32767, 32767]);
  expect(new Uint8Array(messages[0].buffer)[1]).toBe(128);
  expect(messages.at(-1)?.type).toBe("flushed");
  expect(processor.process([[new Float32Array(128)]])).toBe(false);
});
it("sends exactly 32000 bytes per second across arbitrary render boundaries", () => {
  const { processor, messages } = worklet();
  for (let i = 0; i < 125; i++) processor.process([[new Float32Array(128).fill(.2)]]);
  processor.port.onmessage({ data: "flush" });
  const pcm = messages.filter(m => m.type === "pcm");
  expect(pcm).toHaveLength(10); expect(pcm.reduce((n, m) => n + m.buffer.byteLength, 0)).toBe(32000);
});
it("mixes stereo to mono and rejects an unsupported sample rate", () => {
  const { processor, messages } = worklet();
  processor.process([[Float32Array.from([1, .5]), Float32Array.from([-1, .5])]]);
  processor.port.onmessage({ data: "flush" });
  expect(new DataView(messages[0].buffer).getInt16(0, true)).toBe(0);
  expect(new DataView(messages[0].buffer).getInt16(2, true)).toBe(16384);
  expect(() => worklet(48000)).toThrow(/16kHz/);
});
