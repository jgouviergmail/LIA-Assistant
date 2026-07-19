/**
 * useBulkConnect — "connect everything" for Google and Microsoft. The flow
 * spans page loads: the remaining connector types are parked in localStorage,
 * the browser is handed to the first consent screen, and on the way back the
 * mount effect resumes the queue.
 *
 * What is pinned here: the queue that survives the redirect, the entries that
 * get skipped (already-active connector, legacy `gmail` type, unknown type),
 * the completion notice when the queue drains, and the cleanup that must
 * happen when a request fails — a stale queue would restart an OAuth dance on
 * the next page load.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderHook, act, waitFor } from '@/__tests__/test-utils';
import { makeConnector } from '@/__tests__/factories';
import type { Connector } from '@/components/settings/connectors/types';

const { get } = vi.hoisted(() => ({ get: vi.fn() }));
vi.mock('@/lib/api-client', () => ({ default: { get } }));
const { toast } = vi.hoisted(() => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));

import { useBulkConnect } from '../useBulkConnect';
import {
  BULK_CONNECT_QUEUE_KEY,
  MICROSOFT_BULK_CONNECT_QUEUE_KEY,
} from '@/components/settings/connectors/constants';

const t = (key: string) => key;

const GOOGLE_ORDER = [
  'google_contacts',
  'google_gmail',
  'google_calendar',
  'google_drive',
  'google_tasks',
];

let originalLocation: Location;

function setup(connectors: Connector[] = [], loading = false) {
  return renderHook(() => useBulkConnect({ connectors, loading, t }));
}

/**
 * Lets the mount effect release the queue before the test acts. The hook
 * serializes the resume pass and a user-initiated run (see `runExclusively`),
 * so a click fired inside the resume window is deliberately a no-op — pinned
 * by "ignores a run started while the resume pass still owns the queue".
 */
async function settled(hook: ReturnType<typeof setup>) {
  await act(async () => {});
  return hook;
}

function queue(key: string): string[] | null {
  const raw = localStorage.getItem(key);
  return raw ? (JSON.parse(raw) as string[]) : null;
}

beforeEach(() => {
  vi.clearAllMocks();
  localStorage.clear();
  get.mockResolvedValue({ authorization_url: 'https://accounts.example/oauth' });
  originalLocation = window.location;
  Object.defineProperty(window, 'location', {
    value: { href: '' },
    writable: true,
    configurable: true,
  });
});

afterEach(() => {
  Object.defineProperty(window, 'location', { value: originalLocation, configurable: true });
});

describe('useBulkConnect — starting a Google run', () => {
  it('parks the rest of the queue and starts the first consent screen', async () => {
    const { result } = await settled(setup());

    await act(async () => {
      await result.current.connectAllGoogle();
    });

    expect(get).toHaveBeenCalledWith('/connectors/google-contacts/authorize');
    expect(window.location.href).toBe('https://accounts.example/oauth');
    // The legacy `gmail` type is never queued.
    expect(queue(BULK_CONNECT_QUEUE_KEY)).toEqual(GOOGLE_ORDER.slice(1));
  });

  it('skips the connectors that are already active', async () => {
    const { result } = await settled(
      setup([makeConnector({ id: '1', connector_type: 'google_contacts', status: 'active' })])
    );

    await act(async () => {
      await result.current.connectAllGoogle();
    });

    expect(get).toHaveBeenCalledWith('/connectors/gmail/authorize');
    expect(queue(BULK_CONNECT_QUEUE_KEY)).toEqual(GOOGLE_ORDER.slice(2));
  });

  it('counts a legacy Gmail row as a connected mailbox', async () => {
    const { result } = await settled(
      setup([makeConnector({ id: '1', connector_type: 'gmail', status: 'active' })])
    );

    await act(async () => {
      await result.current.connectAllGoogle();
    });

    expect(queue(BULK_CONNECT_QUEUE_KEY)).not.toContain('google_gmail');
  });

  it('ignores a connector that exists but is not active', async () => {
    const { result } = await settled(
      setup([makeConnector({ id: '1', connector_type: 'google_contacts', status: 'error' })])
    );

    await act(async () => {
      await result.current.connectAllGoogle();
    });

    expect(get).toHaveBeenCalledWith('/connectors/google-contacts/authorize');
  });

  it('says so when everything is already connected, and starts nothing', async () => {
    const { result } = await settled(
      setup(
        GOOGLE_ORDER.map((type, i) =>
          makeConnector({ id: `c${i}`, connector_type: type, status: 'active' })
        )
      )
    );

    await act(async () => {
      await result.current.connectAllGoogle();
    });

    expect(toast.info).toHaveBeenCalledWith('settings.connectors.google.all_already_connected');
    expect(get).not.toHaveBeenCalled();
    expect(queue(BULK_CONNECT_QUEUE_KEY)).toBeNull();
  });

  it('drops the queue when the authorization request fails', async () => {
    get.mockRejectedValue(new Error('502'));
    const { result } = await settled(setup());

    await act(async () => {
      await result.current.connectAllGoogle();
    });

    expect(toast.error).toHaveBeenCalledWith('settings.connectors.google.connect_all_error');
    expect(queue(BULK_CONNECT_QUEUE_KEY)).toBeNull();
    expect(result.current.bulkConnecting).toBe(false);
    expect(window.location.href).toBe('');
  });
});

describe('useBulkConnect — starting a Microsoft run', () => {
  it('uses its own queue and endpoints', async () => {
    const { result } = await settled(setup());

    await act(async () => {
      await result.current.connectAllMicrosoft();
    });

    expect(get).toHaveBeenCalledWith('/connectors/microsoft-outlook/authorize');
    expect(queue(MICROSOFT_BULK_CONNECT_QUEUE_KEY)).toEqual([
      'microsoft_calendar',
      'microsoft_contacts',
      'microsoft_tasks',
    ]);
    expect(queue(BULK_CONNECT_QUEUE_KEY)).toBeNull();
  });
});

describe('useBulkConnect — resuming after the redirect', () => {
  it('picks the next connector up on mount and pops it off the queue', async () => {
    localStorage.setItem(
      BULK_CONNECT_QUEUE_KEY,
      JSON.stringify(['google_calendar', 'google_drive'])
    );

    setup();

    await waitFor(() => expect(get).toHaveBeenCalledWith('/connectors/google-calendar/authorize'));
    expect(queue(BULK_CONNECT_QUEUE_KEY)).toEqual(['google_drive']);
    expect(window.location.href).toBe('https://accounts.example/oauth');
  });

  it('announces the end of the run once the last entry is already connected', async () => {
    localStorage.setItem(BULK_CONNECT_QUEUE_KEY, JSON.stringify(['google_calendar']));

    setup([makeConnector({ id: '1', connector_type: 'google_calendar', status: 'active' })]);

    await waitFor(() =>
      expect(toast.success).toHaveBeenCalledWith('settings.connectors.google.connect_all_complete')
    );
    expect(queue(BULK_CONNECT_QUEUE_KEY)).toBeNull();
    expect(get).not.toHaveBeenCalled();
  });

  it('walks past an already-connected entry to the next real one', async () => {
    localStorage.setItem(
      BULK_CONNECT_QUEUE_KEY,
      JSON.stringify(['google_calendar', 'google_drive'])
    );

    setup([makeConnector({ id: '1', connector_type: 'google_calendar', status: 'active' })]);

    await waitFor(() => expect(get).toHaveBeenCalledWith('/connectors/google-drive/authorize'));
  });

  it('walks past an entry that no longer maps to any endpoint', async () => {
    localStorage.setItem(BULK_CONNECT_QUEUE_KEY, JSON.stringify(['google_places', 'google_drive']));

    setup();

    await waitFor(() => expect(get).toHaveBeenCalledWith('/connectors/google-drive/authorize'));
  });

  it('clears an empty queue without announcing anything', async () => {
    localStorage.setItem(BULK_CONNECT_QUEUE_KEY, JSON.stringify([]));

    setup();

    await waitFor(() => expect(queue(BULK_CONNECT_QUEUE_KEY)).toBeNull());
    expect(toast.success).not.toHaveBeenCalled();
    expect(get).not.toHaveBeenCalled();
  });

  it('does nothing at all without a parked queue', async () => {
    setup();
    await waitFor(() => expect(get).not.toHaveBeenCalled());
    expect(toast.success).not.toHaveBeenCalled();
  });

  it('waits for the connector list before resuming', async () => {
    localStorage.setItem(BULK_CONNECT_QUEUE_KEY, JSON.stringify(['google_calendar']));

    setup([], true);

    await waitFor(() => expect(get).not.toHaveBeenCalled());
    expect(queue(BULK_CONNECT_QUEUE_KEY)).toEqual(['google_calendar']);
  });

  it('drops both queues when resuming blows up', async () => {
    localStorage.setItem(BULK_CONNECT_QUEUE_KEY, JSON.stringify(['google_calendar']));
    localStorage.setItem(MICROSOFT_BULK_CONNECT_QUEUE_KEY, JSON.stringify(['microsoft_tasks']));
    get.mockRejectedValue(new Error('boom'));

    setup();

    await waitFor(() => expect(queue(BULK_CONNECT_QUEUE_KEY)).toBeNull());
    expect(queue(MICROSOFT_BULK_CONNECT_QUEUE_KEY)).toBeNull();
  });

  it('survives a corrupted queue without wedging the page', async () => {
    localStorage.setItem(BULK_CONNECT_QUEUE_KEY, 'not-json');

    setup();

    await waitFor(() => expect(queue(BULK_CONNECT_QUEUE_KEY)).toBeNull());
    expect(get).not.toHaveBeenCalled();
  });
});

describe('useBulkConnect — one owner of the queue at a time', () => {
  it('ignores a run started while the resume pass still owns the queue', async () => {
    localStorage.setItem(BULK_CONNECT_QUEUE_KEY, JSON.stringify(['google_calendar']));
    let resolveGet!: (value: { authorization_url: string }) => void;
    get.mockReturnValue(
      new Promise<{ authorization_url: string }>(resolve => {
        resolveGet = resolve;
      })
    );

    const { result } = setup();
    // The resume pass is now awaiting its authorize call, holding the queue.
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));

    await act(async () => {
      await result.current.connectAllMicrosoft();
    });

    // Overlapping would have parked a second queue and fired a second
    // authorize request — the run is dropped instead.
    expect(get).toHaveBeenCalledTimes(1);
    expect(queue(MICROSOFT_BULK_CONNECT_QUEUE_KEY)).toBeNull();

    await act(async () => {
      resolveGet({ authorization_url: 'https://accounts.example/oauth' });
    });
  });

  it('accepts a run again once the resume pass has finished', async () => {
    const { result } = await settled(setup());

    await act(async () => {
      await result.current.connectAllGoogle();
    });

    expect(get).toHaveBeenCalledWith('/connectors/google-contacts/authorize');
  });
});
