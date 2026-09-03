/**
 * The mail-source hooks (ADR-262): the URLs they call and when.
 *
 * A closed picker must ask Gmail nothing (the label listing is a real API
 * call on the user's mailbox), a failed listing must not look like an empty
 * one, and the unlink call must carry the delete-documents flag — the two
 * defects a hook like this ships with.
 */

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { renderHook, act, waitFor } from '@testing-library/react';

const mutate = vi.hoisted(() => vi.fn().mockResolvedValue(undefined));
const get = vi.hoisted(() => vi.fn());

vi.mock('@/hooks/useApiMutation', () => ({
  useApiMutation: () => ({ mutate, loading: false }),
}));
vi.mock('@/lib/api-client', () => ({ default: { get } }));

import { useGmailLabels, useMailSources } from '../useMailSources';

beforeEach(() => {
  mutate.mockClear();
  get.mockReset();
});

describe('useMailSources', () => {
  it('links, unlinks with its flag, and syncs on the space-scoped routes', async () => {
    const { result } = renderHook(() => useMailSources('space-1'));

    await act(async () => {
      await result.current.linkLabel('Label_3', 'Invoices');
    });
    expect(mutate).toHaveBeenCalledWith('/rag-spaces/space-1/mail-sources', {
      label_id: 'Label_3',
      label_name: 'Invoices',
    });

    await act(async () => {
      await result.current.unlinkLabel('src-9', true);
    });
    expect(mutate).toHaveBeenLastCalledWith(
      '/rag-spaces/space-1/mail-sources/src-9?delete_documents=true'
    );

    await act(async () => {
      await result.current.unlinkLabel('src-9');
    });
    expect(mutate).toHaveBeenLastCalledWith(
      '/rag-spaces/space-1/mail-sources/src-9?delete_documents=false'
    );

    await act(async () => {
      await result.current.syncLabel('src-9');
    });
    expect(mutate).toHaveBeenLastCalledWith('/rag-spaces/space-1/mail-sources/src-9/sync');
  });
});

describe('useGmailLabels', () => {
  it('asks Gmail nothing while the picker is closed', () => {
    renderHook(() => useGmailLabels('space-1', false));
    expect(get).not.toHaveBeenCalled();
  });

  it('fetches the labels when the picker opens', async () => {
    get.mockResolvedValue([{ id: 'Label_1', name: 'Projects' }]);
    const { result } = renderHook(() => useGmailLabels('space-1', true));
    await waitFor(() => expect(result.current.labels).toHaveLength(1));
    expect(get).toHaveBeenCalledWith('/rag-spaces/space-1/mail-labels');
    expect(result.current.error).toBeNull();
  });

  it('reports a failure instead of an empty list', async () => {
    get.mockRejectedValue(new Error('403'));
    const { result } = renderHook(() => useGmailLabels('space-1', true));
    await waitFor(() => expect(result.current.error).toBe('failed'));
    expect(result.current.labels).toEqual([]);
    expect(result.current.loading).toBe(false);
  });
});
