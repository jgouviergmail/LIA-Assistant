/** Owner-local audio preferences. No audio or private message content is persisted. */
function localPreference<T>(
  key: string,
  initial: T,
  decode: (raw: string | null) => T,
  encode: (value: T) => string
) {
  const read = () => {
    try {
      return typeof window === 'undefined' ? initial : decode(localStorage.getItem(key));
    } catch {
      return initial;
    }
  };
  let current = read();
  const listeners = new Set<() => void>();
  const emit = () => {
    for (const listener of listeners) listener();
  };
  const storage = (event: StorageEvent) => {
    if (event.key !== key && event.key !== null) return;
    current = read();
    emit();
  };
  return {
    snapshot: () => current,
    serverSnapshot: () => initial,
    subscribe: (listener: () => void) => {
      listeners.add(listener);
      if (listeners.size === 1) window.addEventListener('storage', storage);
      return () => {
        listeners.delete(listener);
        if (!listeners.size) window.removeEventListener('storage', storage);
      };
    },
    update: (value: T) => {
      if (Object.is(current, value)) return;
      current = value;
      try {
        localStorage.setItem(key, encode(value));
      } catch {
        /* This tab still obeys the choice. */
      }
      emit();
    },
  };
}
export function soundPreference(ownerId: string) {
  return localPreference(
    'lia-world-sound:' + ownerId,
    false,
    raw => raw === 'on',
    value => (value ? 'on' : 'off')
  );
}
export function volumePreference(ownerId: string) {
  const store = localPreference(
    'lia-world-sound-volume:' + ownerId,
    1,
    raw => {
      const value = raw?.trim() ? Number(raw) : Number.NaN;
      return Number.isFinite(value) ? Math.max(0, Math.min(1, value)) : 1;
    },
    String
  );
  return {
    ...store,
    update: (value: number) => {
      if (Number.isFinite(value)) store.update(Math.max(0, Math.min(1, value)));
    },
  };
}
