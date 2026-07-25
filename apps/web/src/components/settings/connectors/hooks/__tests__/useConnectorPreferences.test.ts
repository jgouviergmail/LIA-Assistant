/**
 * useConnectorPreferences — the per-connector default calendar / task list.
 *
 * Two contracts matter here: preferences are loaded **once** per connector (a
 * missing preference is a silent, non-retried outcome, not an error), and a
 * change is applied optimistically then **rolled back** if the API refuses it —
 * with the server's own field errors surfaced when it provides them.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';

import { renderHook, act, waitFor } from '@/__tests__/test-utils';
import { makeConnector } from '@/__tests__/factories';
import type { ConnectorPreferences } from '@/components/settings/connectors/types';

const { get, patch } = vi.hoisted(() => ({ get: vi.fn(), patch: vi.fn() }));
// The default export is stubbed, but `ApiError` stays the REAL class: the
// rejection shape is the contract under test here, and a hand-rolled stand-in
// would let the production read drift away from what the client actually throws.
vi.mock('@/lib/api-client', async importOriginal => ({
  ...(await importOriginal<typeof import('@/lib/api-client')>()),
  default: { get, patch },
}));
const { toast } = vi.hoisted(() => ({ toast: { success: vi.fn(), error: vi.fn() } }));
vi.mock('sonner', () => ({ toast }));
vi.mock('@/lib/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), warn: vi.fn(), info: vi.fn() },
}));

import { ApiError } from '@/lib/api-client';

import { useConnectorPreferences } from '../useConnectorPreferences';

const t = (key: string) => key;

/**
 * The 422 the connectors router actually puts on the wire for a refused
 * preference: `ConnectorValidationError` serialises
 * `{"detail": {"errors": [{"field": ..., "message": ...}]}}`, and `apiClient`
 * wraps it in `ApiError(message, status, body)`.
 */
function connectorValidationError(...messages: string[]): ApiError {
  const detail = { errors: messages.map(message => ({ field: 'preferences', message })) };
  return new ApiError(String(detail), 422, { detail });
}

/** A calendar connector — one of the types that carries preferences. */
const calendar = makeConnector({ id: 'c1', connector_type: 'google_calendar', status: 'active' });

function setup(connectors = [calendar]) {
  return renderHook(() => useConnectorPreferences({ connectors, t }));
}

/** A GET the test resolves by hand, to hold a load in flight. */
function deferredGet() {
  let resolve!: (value: { preferences: ConnectorPreferences }) => void;
  get.mockReturnValue(
    new Promise<{ preferences: ConnectorPreferences }>(r => {
      resolve = r;
    })
  );
  return (preferences: ConnectorPreferences) => resolve({ preferences });
}

beforeEach(() => {
  vi.clearAllMocks();
  get.mockResolvedValue({ preferences: {} });
  patch.mockResolvedValue({});
});

describe('useConnectorPreferences — loading', () => {
  it('loads the saved preference of a connector that supports one', async () => {
    get.mockResolvedValue({ preferences: { default_calendar_name: 'Work' } });
    const { result } = setup();

    await waitFor(() =>
      expect(result.current.savedPrefs.c1).toEqual({ default_calendar_name: 'Work' })
    );
    expect(get).toHaveBeenCalledWith('/connectors/c1/preferences');
  });

  it('ignores connectors that have no preferences to load', async () => {
    setup([makeConnector({ id: 'd1', connector_type: 'google_drive', status: 'active' })]);
    await waitFor(() => expect(get).not.toHaveBeenCalled());
  });

  it('treats a missing preference as a silent, non-repeated outcome', async () => {
    get.mockRejectedValue(new Error('404'));
    const { result, rerender } = setup();

    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    rerender();
    // The "already looked" flag survives the re-render: no retry storm.
    await waitFor(() => expect(get).toHaveBeenCalledTimes(1));
    expect(result.current.savedPrefs.c1).toBeUndefined();
  });
});

describe('useConnectorPreferences — saving', () => {
  it('patches the field mapped to the connector type and confirms', async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.selectPreference('c1', 'google_calendar', 'Work');
    });

    expect(patch).toHaveBeenCalledWith('/connectors/c1/preferences', {
      default_calendar_name: 'Work',
    });
    expect(result.current.savedPrefs.c1).toEqual({ default_calendar_name: 'Work' });
    expect(toast.success).toHaveBeenCalledWith('settings.connectors.preferences.saved');
  });

  it('maps a task connector onto its own field', async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.selectPreference('c1', 'google_tasks', 'Inbox');
    });
    expect(patch).toHaveBeenCalledWith('/connectors/c1/preferences', {
      default_task_list_name: 'Inbox',
    });
  });

  it('uses the cleared wording when the preference is emptied', async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.selectPreference('c1', 'google_calendar', '');
    });
    expect(toast.success).toHaveBeenCalledWith('settings.connectors.preferences.cleared');
  });

  it('does nothing for a connector type without a mapped field', async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.selectPreference('c1', 'google_drive', 'whatever');
    });
    expect(patch).not.toHaveBeenCalled();
    expect(result.current.savingPreference).toBeNull();
  });

  it('leaves no connector marked as saving once the call settles', async () => {
    const { result } = setup();
    await act(async () => {
      await result.current.selectPreference('c1', 'google_calendar', 'Work');
    });
    expect(result.current.savingPreference).toBeNull();
  });
});

describe('useConnectorPreferences — rollback', () => {
  it('restores the previous value when the API refuses the change', async () => {
    get.mockResolvedValue({ preferences: { default_calendar_name: 'Work' } });
    const { result } = setup();
    await waitFor(() =>
      expect(result.current.savedPrefs.c1).toEqual({ default_calendar_name: 'Work' })
    );

    patch.mockRejectedValue(new Error('nope'));
    await act(async () => {
      await result.current.selectPreference('c1', 'google_calendar', 'Personal');
    });

    expect(result.current.savedPrefs.c1).toEqual({ default_calendar_name: 'Work' });
    expect(result.current.savingPreference).toBeNull();
  });

  it('surfaces the validation errors the server returned', async () => {
    patch.mockRejectedValue(connectorValidationError('unknown calendar', 'try again'));
    const { result } = setup();
    await act(async () => {
      await result.current.selectPreference('c1', 'google_calendar', 'Ghost');
    });
    expect(toast.error).toHaveBeenCalledWith('unknown calendar, try again');
  });

  it('falls back to the generic wording when the 422 carries no field error', async () => {
    patch.mockRejectedValue(new ApiError('HTTP 422', 422, { detail: { errors: [] } }));
    const { result } = setup();
    await act(async () => {
      await result.current.selectPreference('c1', 'google_calendar', 'Ghost');
    });
    expect(toast.error).toHaveBeenCalledWith('settings.connectors.preferences.error');
  });

  it('surfaces a plain string detail as-is', async () => {
    patch.mockRejectedValue(
      new ApiError('Calendar is read-only', 409, {
        detail: 'Calendar is read-only',
      })
    );
    const { result } = setup();
    await act(async () => {
      await result.current.selectPreference('c1', 'google_calendar', 'Ghost');
    });
    expect(toast.error).toHaveBeenCalledWith('Calendar is read-only');
  });

  it('falls back to the generic wording for an unstructured failure', async () => {
    patch.mockRejectedValue(new Error('500'));
    const { result } = setup();
    await act(async () => {
      await result.current.selectPreference('c1', 'google_calendar', 'Work');
    });
    expect(toast.error).toHaveBeenCalledWith('settings.connectors.preferences.error');
  });
});

describe('useConnectorPreferences — load racing a local write', () => {
  it('fetches a connector once, even if the parent re-renders mid-request', async () => {
    const settle = deferredGet();
    const { rerender } = renderHook(
      ({ connectors }) => useConnectorPreferences({ connectors, t }),
      { initialProps: { connectors: [calendar] } }
    );

    // A new array identity is what UserConnectorsSection produces on every
    // optimistic connector add/remove — it must not re-fire the request.
    rerender({ connectors: [{ ...calendar }] });
    expect(get).toHaveBeenCalledTimes(1);

    await act(async () => {
      settle({});
    });
    expect(get).toHaveBeenCalledTimes(1);
  });

  it('never lets a late load overwrite the value the user just chose', async () => {
    const settle = deferredGet();
    const { result } = setup();

    await act(async () => {
      await result.current.selectPreference('c1', 'google_calendar', 'Personal');
    });
    expect(result.current.savedPrefs.c1).toEqual({ default_calendar_name: 'Personal' });

    // The initial load answers only now, with the value the save has replaced.
    await act(async () => {
      settle({ default_calendar_name: 'Server' });
    });

    expect(result.current.savedPrefs.c1).toEqual({ default_calendar_name: 'Personal' });
  });

  it('lets the late load fill the value in when the save was refused', async () => {
    const settle = deferredGet();
    patch.mockRejectedValue(new Error('nope'));
    const { result } = setup();

    await act(async () => {
      await result.current.selectPreference('c1', 'google_calendar', 'Personal');
    });

    // The rollback puts the value back to "nothing chosen yet", so the server
    // answer is welcome — leaving a hole would be the real bug.
    await act(async () => {
      settle({ default_calendar_name: 'Server' });
    });

    expect(result.current.savedPrefs.c1).toEqual({ default_calendar_name: 'Server' });
  });
});
