/**
 * The wake-word runtime as the app runs it (ADR-329), measured inside the
 * native WebView: ONNX Runtime Web single-threaded in a MODULE worker, a model
 * the app ships, its SHA-256 by WebCrypto, one 80 ms chunk through the
 * melspectrogram stage. No SharedArrayBuffer and no cross-origin isolation are
 * needed — that is the claim this measures.
 *
 * Posts `{ status: 'ok', frames, run_ms }` (`frames` must be 5 for the first
 * 1 280-sample chunk; `run_ms` is the median of 20 runs on this device) or
 * `{ status: 'error:<message>' }`.
 */
self.onmessage = async () => {
  try {
    const ort = await import('/wake/ort.mjs');
    ort.env.wasm.numThreads = 1;
    ort.env.wasm.proxy = false;
    ort.env.wasm.wasmPaths = '/wake/';
    const response = await fetch('/wake/melspectrogram.onnx');
    if (!response.ok) throw new Error(`model ${response.status}`);
    const bytes = await response.arrayBuffer();
    await crypto.subtle.digest('SHA-256', bytes);
    const session = await ort.InferenceSession.create(new Uint8Array(bytes), {
      executionProviders: ['wasm'],
    });
    const feeds = {
      [session.inputNames[0]]: new ort.Tensor('float32', new Float32Array(1280), [1, 1280]),
    };
    let frames = 0;
    const timings = [];
    for (let run = 0; run < 20; run += 1) {
      const started = performance.now();
      const output = await session.run(feeds);
      timings.push(performance.now() - started);
      frames = output[session.outputNames[0]].data.length / 32;
    }
    timings.sort((a, b) => a - b);
    self.postMessage({ status: 'ok', frames, run_ms: Math.round(timings[10] * 100) / 100 });
  } catch (error) {
    self.postMessage({ status: `error:${String(error && error.message)}` });
  }
};
