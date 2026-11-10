/** Own both startup waits and late microphone grants, including cancellation and timeout. */
export async function openRecordingInputs(
  getMedia: () => Promise<MediaStream>,
  connect: () => Promise<void>,
  signal: AbortSignal,
  timeoutMs: number
): Promise<MediaStream> {
  signal.throwIfAborted();
  let abandoned = false;
  let held: MediaStream | null = null;
  let timer: ReturnType<typeof setTimeout> | undefined;
  let abort = () => {};
  const stop = (stream: MediaStream) => stream.getTracks().forEach(track => track.stop());
  const media = getMedia().then(stream => {
    if (abandoned || signal.aborted) stop(stream);
    else held = stream;
    return stream;
  });
  const cancelled = new Promise<never>((_, reject) => {
    abort = () => reject(new DOMException('Recording cancelled', 'AbortError'));
    signal.addEventListener('abort', abort, { once: true });
    if (signal.aborted) abort();
    timer = setTimeout(
      () => reject(new DOMException('Recording setup timed out', 'TimeoutError')),
      timeoutMs
    );
  });
  try {
    const [stream] = await Promise.race([Promise.all([media, connect()]), cancelled]);
    signal.throwIfAborted();
    return stream;
  } catch (error) {
    abandoned = true;
    if (held) stop(held);
    throw error;
  } finally {
    clearTimeout(timer);
    signal.removeEventListener('abort', abort);
  }
}
