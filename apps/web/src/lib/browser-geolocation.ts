/** Read an already granted position without ever opening a permission prompt. */
export interface BrowserPosition {
  lat: number;
  lon: number;
  accuracy: number | null;
  timestamp: number;
}

const POSITION_TIMEOUT_MS = 3000;

export async function readGrantedPosition(signal?: AbortSignal): Promise<BrowserPosition | null> {
  if (typeof navigator === 'undefined' || !navigator.geolocation || signal?.aborted) return null;
  try {
    if (!navigator.permissions?.query) return null;
    const permission = await navigator.permissions.query({ name: 'geolocation' });
    if (permission.state !== 'granted' || signal?.aborted) return null;
  } catch {
    return null;
  }
  return new Promise(resolve => {
    let settled = false;
    const finish = (value: BrowserPosition | null) => {
      if (settled) return;
      settled = true;
      clearTimeout(timer);
      signal?.removeEventListener('abort', abort);
      resolve(value);
    };
    const abort = () => finish(null);
    const timer = setTimeout(abort, POSITION_TIMEOUT_MS);
    signal?.addEventListener('abort', abort, { once: true });
    if (signal?.aborted) return abort();
    try {
      navigator.geolocation.getCurrentPosition(
        position => {
          const { latitude: lat, longitude: lon, accuracy } = position.coords;
          if (
            !Number.isFinite(lat) ||
            !Number.isFinite(lon) ||
            Math.abs(lat) > 90 ||
            Math.abs(lon) > 180
          )
            return finish(null);
          finish({
            lat,
            lon,
            accuracy: Number.isFinite(accuracy) && accuracy >= 0 ? accuracy : null,
            timestamp: Number.isFinite(position.timestamp) ? position.timestamp : Date.now(),
          });
        },
        abort,
        { maximumAge: 60_000, timeout: POSITION_TIMEOUT_MS, enableHighAccuracy: false }
      );
    } catch {
      finish(null);
    }
  });
}
