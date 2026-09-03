/**
 * The Gmail label section of a space (ADR-262).
 *
 * The oracles are what a reader must be able to do and to know: see what is
 * followed and in which state, follow a new label without being offered one
 * already followed, and stop following one — with the choice of deleting the
 * indexed documents, carried faithfully to the caller. The privacy sentence
 * is part of the picker, not a tooltip: linking a label copies personal mail.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

import type { RAGMailSource } from '@/types/rag-spaces';

const labels = vi.hoisted(() => ({ current: [] as { id: string; name: string }[] }));
const state = vi.hoisted(() => ({ loading: false, error: null as string | null }));

vi.mock('@/hooks/useMailSources', () => ({
  useGmailLabels: () => ({
    labels: labels.current,
    loading: state.loading,
    error: state.error,
    refetch: vi.fn(),
  }),
}));

import { MailSourcesList } from '../MailSourcesList';

function source(over: Partial<RAGMailSource> = {}): RAGMailSource {
  return {
    id: 'src-1',
    label_id: 'Label_1',
    label_name: 'Projects',
    sync_status: 'completed',
    last_sync_at: '2026-09-03T08:00:00Z',
    thread_count: 12,
    synced_thread_count: 11,
    error_message: null,
    created_at: '2026-09-01T08:00:00Z',
    ...over,
  };
}

const onLink = vi.fn().mockResolvedValue(undefined);
const onUnlink = vi.fn();
const onSync = vi.fn();

function renderList(sources: RAGMailSource[] = [source()]) {
  return render(
    <MailSourcesList
      spaceId="space-1"
      sources={sources}
      onLink={onLink}
      onUnlink={onUnlink}
      onSync={onSync}
    />
  );
}

beforeEach(() => {
  onLink.mockClear();
  onUnlink.mockReset();
  onSync.mockReset();
  labels.current = [
    { id: 'Label_1', name: 'Projects' },
    { id: 'Label_2', name: 'Invoices' },
  ];
  state.loading = false;
  state.error = null;
});

describe('MailSourcesList', () => {
  it('explains an empty section instead of showing nothing', () => {
    renderList([]);
    expect(screen.getByText('spaces.mail.empty')).toBeInTheDocument();
  });

  it('shows the label, its state and its exact counts', () => {
    renderList();
    expect(screen.getByText('Projects')).toBeInTheDocument();
    expect(screen.getByText('spaces.mail.status_completed')).toBeInTheDocument();
    expect(screen.getByText(/spaces\.mail\.synced_count/)).toBeInTheDocument();
    expect(screen.getByText(/spaces\.mail\.threads_count/)).toBeInTheDocument();
  });

  it('says what failed when a sync errored', () => {
    renderList([source({ sync_status: 'error', error_message: 'Gmail refused the label' })]);
    expect(screen.getByText('Gmail refused the label')).toBeInTheDocument();
  });

  it('refuses a second sync while one is running', () => {
    renderList([source({ sync_status: 'syncing' })]);
    const button = screen.getByRole('button', { name: 'spaces.mail.sync_now' });
    expect(button).toBeDisabled();
    fireEvent.click(button);
    expect(onSync).not.toHaveBeenCalled();
  });

  it('syncs the source the button belongs to', () => {
    renderList();
    fireEvent.click(screen.getByRole('button', { name: 'spaces.mail.sync_now' }));
    expect(onSync).toHaveBeenCalledWith('src-1');
  });

  it('offers only the labels not already followed, and states the privacy rule', async () => {
    renderList();
    fireEvent.click(screen.getByRole('button', { name: /spaces\.mail\.link_label/ }));
    await waitFor(() => expect(screen.getByText('spaces.mail.picker_title')).toBeInTheDocument());
    expect(screen.getByText('spaces.mail.privacy_note')).toBeInTheDocument();
    expect(screen.getByRole('radio', { name: /Invoices/ })).toBeInTheDocument();
    // "Projects" is already followed: it is the card's title, never a choice.
    expect(screen.queryByRole('radio', { name: /Projects/ })).not.toBeInTheDocument();
  });

  it('links the chosen label, and nothing before a choice is made', async () => {
    renderList();
    fireEvent.click(screen.getByRole('button', { name: /spaces\.mail\.link_label/ }));
    await waitFor(() => expect(screen.getByText('spaces.mail.picker_title')).toBeInTheDocument());

    const confirm = screen.getByRole('button', { name: 'spaces.mail.picker_select' });
    expect(confirm).toBeDisabled();

    fireEvent.click(screen.getByRole('radio', { name: /Invoices/ }));
    fireEvent.click(confirm);
    expect(onLink).toHaveBeenCalledWith('Label_2', 'Invoices');
  });

  it('carries the delete-documents choice to the caller when unfollowing', async () => {
    renderList();
    fireEvent.click(screen.getByRole('button', { name: 'spaces.mail.unlink' }));
    await waitFor(() =>
      expect(screen.getByText('spaces.mail.unlink_confirm_title')).toBeInTheDocument()
    );
    fireEvent.click(screen.getByRole('checkbox', { name: 'spaces.mail.unlink_delete_docs' }));
    fireEvent.click(screen.getByText('spaces.mail.unlink'));
    expect(onUnlink).toHaveBeenCalledWith('src-1', true);
  });

  it('reports a label listing that failed rather than an empty picker', async () => {
    state.error = 'failed';
    labels.current = [];
    renderList([]);
    fireEvent.click(screen.getByRole('button', { name: /spaces\.mail\.link_label/ }));
    await waitFor(() => expect(screen.getByText('spaces.mail.picker_error')).toBeInTheDocument());
  });

  it('says it is loading the labels', async () => {
    state.loading = true;
    renderList([]);
    fireEvent.click(screen.getByRole('button', { name: /spaces\.mail\.link_label/ }));
    await waitFor(() => expect(screen.getByText('spaces.mail.picker_loading')).toBeInTheDocument());
  });
});
