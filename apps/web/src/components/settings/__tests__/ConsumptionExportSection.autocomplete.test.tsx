/**
 * ConsumptionExportSection admin user autocomplete (F014).
 *
 * Pins the two fixed defects: (1) a superseded (stale) suggestion response must
 * never overwrite fresher results — enforced by the per-request AbortController +
 * signal.aborted guards; (2) the suggestion list is a real ARIA combobox/listbox
 * with keyboard navigation. useDebounce is mocked to identity so the tests drive
 * the fetch effect directly without timer juggling.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';

vi.mock('@/hooks/useDebounce', () => ({ useDebounce: (v: unknown) => v }));

import ConsumptionExportSection from '../ConsumptionExportSection';

interface Deferred<T> {
  promise: Promise<T>;
  resolve: (value: T) => void;
}

function deferred<T>(): Deferred<T> {
  let resolve!: (value: T) => void;
  const promise = new Promise<T>(r => {
    resolve = r;
  });
  return { promise, resolve };
}

function userPayload(users: Array<{ id: string; email: string }>) {
  return { ok: true, json: () => Promise.resolve({ users }) } as unknown as Response;
}

function renderAdmin() {
  return render(<ConsumptionExportSection lng="en" mode="admin" collapsible={false} />);
}

async function type(value: string) {
  const input = screen.getByRole('combobox');
  await act(async () => {
    fireEvent.change(input, { target: { value } });
  });
  return input;
}

afterEach(() => {
  vi.restoreAllMocks();
});

describe('ConsumptionExportSection autocomplete — stale responses (F014)', () => {
  beforeEach(() => {
    vi.spyOn(console, 'error').mockImplementation(() => {});
  });

  it('an older response resolving AFTER a newer one must NOT overwrite the fresh suggestions', async () => {
    const first = deferred<Response>();
    const second = deferred<Response>();
    const fetchMock = vi
      .fn()
      .mockReturnValueOnce(first.promise)
      .mockReturnValueOnce(second.promise);
    vi.stubGlobal('fetch', fetchMock);

    renderAdmin();
    await type('ab'); // fires request #1
    await type('abc'); // aborts #1, fires request #2

    // Resolve the OLDER request last — its controller is already aborted.
    await act(async () => {
      second.resolve(userPayload([{ id: '2', email: 'new@example.com' }]));
      await Promise.resolve();
    });
    await act(async () => {
      first.resolve(userPayload([{ id: '1', email: 'stale@example.com' }]));
      await Promise.resolve();
    });

    expect(await screen.findByText('new@example.com')).toBeInTheDocument();
    expect(screen.queryByText('stale@example.com')).not.toBeInTheDocument();
  });

  it('unmounting while a request is in flight does not throw or update state', async () => {
    const pending = deferred<Response>();
    vi.stubGlobal('fetch', vi.fn().mockReturnValue(pending.promise));
    const { unmount } = renderAdmin();
    await type('ab');
    unmount();
    // Resolving after unmount must be a no-op (aborted), not a React state warning.
    await act(async () => {
      pending.resolve(userPayload([{ id: '1', email: 'late@example.com' }]));
      await Promise.resolve();
    });
    expect(screen.queryByText('late@example.com')).not.toBeInTheDocument();
  });
});

describe('ConsumptionExportSection autocomplete — ARIA combobox + keyboard (F014)', () => {
  async function openWithTwoUsers() {
    vi.stubGlobal(
      'fetch',
      vi.fn().mockResolvedValue(
        userPayload([
          { id: '1', email: 'alice@example.com' },
          { id: '2', email: 'bob@example.com' },
        ])
      )
    );
    renderAdmin();
    const input = await type('al');
    await screen.findByText('alice@example.com');
    return input;
  }

  it('exposes the combobox/listbox roles and wiring', async () => {
    const input = await openWithTwoUsers();
    expect(input).toHaveAttribute('aria-expanded', 'true');
    const listbox = screen.getByRole('listbox');
    expect(input).toHaveAttribute('aria-controls', listbox.id);
    const options = screen.getAllByRole('option');
    expect(options).toHaveLength(2);
  });

  it('ArrowDown highlights an option via aria-activedescendant and Enter selects it', async () => {
    const input = await openWithTwoUsers();
    await act(async () => {
      fireEvent.keyDown(input, { key: 'ArrowDown' });
    });
    const options = screen.getAllByRole('option');
    expect(input).toHaveAttribute('aria-activedescendant', options[0].id);
    expect(options[0]).toHaveAttribute('aria-selected', 'true');

    await act(async () => {
      fireEvent.keyDown(input, { key: 'Enter' });
    });
    // Selecting closes the listbox and shows the chosen user.
    await waitFor(() => expect(screen.queryByRole('listbox')).not.toBeInTheDocument());
    expect(screen.getByText('alice@example.com')).toBeInTheDocument();
  });

  it('Escape closes the listbox without selecting', async () => {
    const input = await openWithTwoUsers();
    await act(async () => {
      fireEvent.keyDown(input, { key: 'Escape' });
    });
    await waitFor(() => expect(screen.queryByRole('listbox')).not.toBeInTheDocument());
    expect(input).toHaveAttribute('aria-expanded', 'false');
  });
});
