/** Bound asset readiness without advancing any live face or simulation clock. */
export async function preparePhotoAsset(
  preparation: Promise<void> | undefined,
  signal: AbortSignal
): Promise<void> {
  signal.throwIfAborted();
  await new Promise<void>((resolve, reject) => {
    const done = () => {
      clearTimeout(timer);
      signal.removeEventListener('abort', abort);
      resolve();
    };
    const abort = () => {
      clearTimeout(timer);
      signal.removeEventListener('abort', abort);
      reject(new DOMException('Aborted', 'AbortError'));
    };
    const timer = setTimeout(done, 1500);
    signal.addEventListener('abort', abort, { once: true });
    void Promise.resolve(preparation).then(done, done);
  });
  signal.throwIfAborted();
}
