// AudioContext performs the microphone's native-rate -> 16kHz resampling.
// Send PCM s16le in 100ms frames; retain the final short frame on stop.
class PCMProcessor extends AudioWorkletProcessor {
  constructor() {
    super();
    if (sampleRate !== 16000) throw new Error("16kHz AudioContext required");
    this.samples = new Float32Array(1600);
    this.used = 0;
    this.stopped = false;
    this.port.onmessage = ({data}) => {
      if (data === "flush") {
        this.stopped = true;
        this.emit();
        this.port.postMessage({type: "flushed"});
      }
    };
  }
  emit() {
    if (!this.used) return;
    const buffer = new ArrayBuffer(this.used * 2);
    const view = new DataView(buffer);
    let squares = 0;
    for (let i = 0; i < this.used; i++) {
      const value = Math.max(-1, Math.min(1, this.samples[i]));
      squares += value * value;
      view.setInt16(i * 2, Math.round(value * (value < 0 ? 32768 : 32767)), true);
    }
    this.port.postMessage({type: "pcm", buffer, rms: Math.sqrt(squares / this.used)}, [buffer]);
    this.used = 0;
  }
  process(inputs) {
    if (this.stopped) return false;
    const channels = inputs[0];
    if (!channels?.length) return true;
    for (let i = 0; i < channels[0].length; i++) {
      let mono = 0;
      for (const channel of channels) mono += channel[i];
      this.samples[this.used++] = mono / channels.length;
      if (this.used === this.samples.length) this.emit();
    }
    return true;
  }
}
registerProcessor("pcm-capture", PCMProcessor);
