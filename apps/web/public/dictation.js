class DictationProcessor extends AudioWorkletProcessor {
  process(inputs) {
    const samples = inputs[0]?.[0];
    if (samples?.length) {
      const pcm = Int16Array.from(samples, (value) =>
        Math.round(Math.max(-1, Math.min(1, value)) * 32767),
      );
      this.port.postMessage(pcm, [pcm.buffer]);
    }
    return true;
  }
}
registerProcessor("certvault-dictation", DictationProcessor);
