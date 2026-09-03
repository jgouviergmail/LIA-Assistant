/**
 * SourceSyncCard — the ONE card behind a Drive folder and a Gmail label.
 *
 * The oracles are the two rules a shared row card exists to enforce: the
 * actions are never revealed by hover (ADR-208 — a keyboard focus would land
 * on an invisible control), and the "⋮" trigger NAMES ITS ROW. Plus the
 * behaviour a reader depends on: the state, the counts, and a sync button
 * that refuses while a sync is already running.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { FolderSync } from 'lucide-react';

import type { RAGSourceSyncStatus } from '@/types/rag-spaces';

import { SourceSyncCard, formatRelativeTime } from '../SourceSyncCard';

const onSync = vi.fn();
const onUnlink = vi.fn();

const STATUS_KEYS: Record<RAGSourceSyncStatus, string> = {
  idle: 'ns.status_idle',
  syncing: 'ns.status_syncing',
  completed: 'ns.status_completed',
  error: 'ns.status_error',
};

function renderCard(over: Partial<React.ComponentProps<typeof SourceSyncCard>> = {}) {
  return render(
    <SourceSyncCard
      icon={<FolderSync className="h-4 w-4" />}
      title="Reports"
      status="completed"
      statusKeys={STATUS_KEYS}
      syncedLabel="3 synced"
      totalLabel="12 files"
      lastSyncAt={null}
      lastSyncedLabel={time => `last ${time}`}
      errorMessage={null}
      onSync={onSync}
      onUnlink={onUnlink}
      syncTitle="ns.sync_now"
      unlinkTitle="ns.unlink"
      {...over}
    />
  );
}

beforeEach(() => {
  onSync.mockReset();
  onUnlink.mockReset();
});

describe('SourceSyncCard', () => {
  it('exposes both actions as named buttons, never hidden behind a hover', () => {
    const { container } = renderCard();
    const sync = screen.getByRole('button', { name: 'ns.sync_now' });
    const unlink = screen.getByRole('button', { name: 'ns.unlink' });

    expect(sync).toBeInTheDocument();
    expect(unlink).toBeInTheDocument();
    // ADR-208: an affordance the pointer must reveal is not an affordance.
    expect(container.querySelector('[class*="opacity-0"]')).toBeNull();

    sync.focus();
    expect(document.activeElement).toBe(sync);
  });

  it('names the phone menu after the row it belongs to', () => {
    renderCard({ title: 'Invoices' });
    // The stub `t` echoes the key; the interpolated name is what matters here.
    expect(screen.getByRole('button', { name: /common\.actions_for/ })).toBeInTheDocument();
  });

  it('says the state, the counts and the last sync', () => {
    renderCard({ lastSyncAt: new Date(Date.now() - 3 * 60_000).toISOString() });
    expect(screen.getByText('ns.status_completed')).toBeInTheDocument();
    expect(screen.getByText(/3 synced/)).toBeInTheDocument();
    expect(screen.getByText(/12 files/)).toBeInTheDocument();
    expect(screen.getByText('last 3 min')).toBeInTheDocument();
  });

  it('refuses a second sync while one runs, and says so', () => {
    renderCard({ status: 'syncing' });
    const sync = screen.getByRole('button', { name: 'ns.sync_now' });
    expect(sync).toBeDisabled();
    fireEvent.click(sync);
    expect(onSync).not.toHaveBeenCalled();
    expect(screen.getByText('ns.status_syncing')).toBeInTheDocument();
  });

  it('shows the error message only in the error state', () => {
    renderCard({ status: 'completed', errorMessage: 'quota exceeded' });
    expect(screen.queryByText('quota exceeded')).not.toBeInTheDocument();
    renderCard({ status: 'error', errorMessage: 'quota exceeded' });
    expect(screen.getByText('quota exceeded')).toBeInTheDocument();
  });

  it('falls back to the idle wording for a state this build does not know', () => {
    renderCard({ status: 'archived' as RAGSourceSyncStatus });
    expect(screen.getByText('ns.status_idle')).toBeInTheDocument();
  });

  it('unlinks through its own handler', () => {
    renderCard();
    fireEvent.click(screen.getByRole('button', { name: 'ns.unlink' }));
    expect(onUnlink).toHaveBeenCalledTimes(1);
  });
});

describe('formatRelativeTime', () => {
  it('reads in minutes, then hours, then days', () => {
    const ago = (ms: number) => new Date(Date.now() - ms).toISOString();
    expect(formatRelativeTime(ago(10_000))).toBe('< 1 min');
    expect(formatRelativeTime(ago(5 * 60_000))).toBe('5 min');
    expect(formatRelativeTime(ago(3 * 3_600_000))).toBe('3h');
    expect(formatRelativeTime(ago(2 * 86_400_000))).toBe('2d');
  });
});
