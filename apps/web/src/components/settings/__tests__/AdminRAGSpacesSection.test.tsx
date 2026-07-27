/**
 * AdminRAGSpacesSection — the RAG index console: the system-space list with its
 * staleness badges, per-space reindexing (success refreshes the list; failure is
 * reported), and the **global reindex behind a mandatory confirmation** — an
 * expensive, disruptive operation that must never fire from a single click.
 *
 * Transport note: this component reaches the API through a *dynamic*
 * `await import('@/lib/api-client')` inside its handlers, which `vi.mock` does
 * not intercept — the real `ApiClient` runs and its failures disappear into the
 * component's own `catch {}`. So instead of mocking the client, the test drives
 * the **real** client over a stubbed `fetch`, which is both hermetic and closer
 * to production (URL building and response handling stay real).
 *
 * The status poll only arms itself when the backend reports `in_progress`, so
 * the default fixture keeps it idle and no interval is left running.
 */

import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest';

import { renderWithProviders, screen, waitFor } from '@/__tests__/test-utils';
import { mutationResult, mutateSpy } from '@/__tests__/api-mocks';
import type { ReindexStatus, SystemSpace, SystemStaleness } from '../AdminRAGSpacesSection';

const { useApiMutation } = vi.hoisted(() => ({ useApiMutation: vi.fn() }));
vi.mock('@/hooks/useApiMutation', () => ({ useApiMutation }));
const { useAppConfig } = vi.hoisted(() => ({ useAppConfig: vi.fn() }));
vi.mock('@/hooks/useAppConfig', () => ({ useAppConfig }));
const { toast } = vi.hoisted(() => ({
  toast: { success: vi.fn(), error: vi.fn(), info: vi.fn() },
}));
vi.mock('sonner', () => ({ toast }));

import AdminRAGSpacesSection from '../AdminRAGSpacesSection';

const I18N = 'settings.admin.ragSpaces';
const SYS = `${I18N}.systemSpaces`;
const REINDEX_ENDPOINT = '/rag-spaces/admin/reindex';

function space(over: Partial<SystemSpace> = {}): SystemSpace {
  return {
    id: 's1',
    name: 'handbook',
    description: 'Internal handbook',
    is_active: true,
    content_hash: 'abc',
    document_count: 12,
    chunk_count: 340,
    created_at: '2026-01-01T00:00:00Z',
    updated_at: '2026-02-01T00:00:00Z',
    ...over,
  };
}

function staleness(over: Partial<SystemStaleness> = {}): SystemStaleness {
  return {
    space_name: 'handbook',
    is_stale: false,
    stored_hash: 'abc',
    current_hash: 'abc',
    ...over,
  };
}

function idleStatus(over: Partial<ReindexStatus> = {}): ReindexStatus {
  return {
    in_progress: false,
    started_at: null,
    model_from: null,
    model_to: null,
    total_documents: 0,
    processed_documents: 0,
    failed_documents: 0,
    ...over,
  };
}

/** A real `Response`, so the client's own parsing stays in the loop. */
function json(data: unknown, status = 200): Response {
  return new Response(JSON.stringify(data), {
    status,
    headers: { 'content-type': 'application/json' },
  });
}

let fetchMock: ReturnType<typeof vi.fn>;
let triggerReindex: ReturnType<typeof mutateSpy>;

/** Routes the endpoints the section reads, by URL fragment. */
function stubTransport(
  spaces: SystemSpace[],
  stale: Record<string, SystemStaleness> = {},
  opts: { reindexStatus?: number; reindexBody?: Record<string, unknown> } = {}
) {
  fetchMock = vi.fn((url: string, init?: RequestInit) => {
    if (url.includes('/reindex/status')) return Promise.resolve(json(idleStatus()));
    if (init?.method === 'POST' && /system-spaces\/[^/]+\/reindex$/.test(url)) {
      return Promise.resolve(
        json(
          opts.reindexBody ?? { chunks_created: 128, status: 'success' },
          opts.reindexStatus ?? 200
        )
      );
    }
    const stalenessMatch = url.match(/system-spaces\/([^/]+)\/staleness/);
    if (stalenessMatch) {
      const name = stalenessMatch[1];
      return Promise.resolve(json(stale[name] ?? staleness({ space_name: name })));
    }
    if (url.includes('/system-spaces')) return Promise.resolve(json({ spaces }));
    return Promise.reject(new Error(`unexpected request ${url}`));
  });
  vi.stubGlobal('fetch', fetchMock);
}

function render() {
  return renderWithProviders(<AdminRAGSpacesSection lng="en" collapsible={false} />);
}

beforeEach(() => {
  vi.clearAllMocks();
  triggerReindex = mutateSpy().mockResolvedValue({
    message: 'started',
    total_documents: 42,
    model_from: 'old-model',
    model_to: 'text-embedding-3-small',
  });
  useApiMutation.mockReturnValue(mutationResult({ mutate: triggerReindex }));
  useAppConfig.mockReturnValue({
    config: { features: { rag_spaces_embedding_model: 'text-embedding-3-large' } },
  });
  stubTransport([space()]);
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe('AdminRAGSpacesSection — system spaces', () => {
  it('shows the empty state when the backend returns no system space', async () => {
    stubTransport([]);
    render();
    // The empty state is also the initial state — assert the fetch really ran.
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/rag-spaces/admin/system-spaces'),
        expect.anything()
      )
    );
    expect(await screen.findByText(`${SYS}.noSpaces`)).toBeInTheDocument();
  });

  it('lists a space and flags it as up to date', async () => {
    stubTransport([space()], { handbook: staleness({ is_stale: false }) });
    render();
    expect(await screen.findByText('handbook')).toBeInTheDocument();
    expect(await screen.findByText(`${SYS}.upToDate`)).toBeInTheDocument();
  });

  it('flags a space whose source drifted from its index', async () => {
    stubTransport([space()], {
      handbook: staleness({ is_stale: true, stored_hash: 'abc', current_hash: 'def' }),
    });
    render();
    expect(await screen.findByText(`${SYS}.stale`)).toBeInTheDocument();
  });

  it('surfaces the configured embedding model', async () => {
    render();
    expect(await screen.findByText('text-embedding-3-large')).toBeInTheDocument();
  });
});

describe('AdminRAGSpacesSection — per-space reindex', () => {
  it('reindexes one space and refreshes the list afterwards', async () => {
    const { user } = render();
    await screen.findByText('handbook');
    const callsBefore = fetchMock.mock.calls.length;
    await user.click(screen.getByRole('button', { name: `${SYS}.reindexButton` }));
    await waitFor(() =>
      expect(fetchMock).toHaveBeenCalledWith(
        expect.stringContaining('/system-spaces/handbook/reindex'),
        expect.objectContaining({ method: 'POST' })
      )
    );
    expect(toast.success).toHaveBeenCalledWith(`${SYS}.reindexSuccess`);
    // The list is re-read so counts and staleness reflect the new index.
    await waitFor(() => expect(fetchMock.mock.calls.length).toBeGreaterThan(callsBefore + 1));
  });

  it('reports a failed per-space reindex', async () => {
    stubTransport([space()], {}, { reindexStatus: 500 });
    const { user } = render();
    await screen.findByText('handbook');
    await user.click(screen.getByRole('button', { name: `${SYS}.reindexButton` }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(`${SYS}.reindexError`));
  });

  // A corpus that was already current is not a rebuild. Announcing
  // "reindexed (0 chunks)" told an admin work had happened when none had —
  // the backend now says which of the two it was (ADR-162).
  it('does not claim a rebuild when the corpus was already current', async () => {
    stubTransport([space()], {}, { reindexBody: { chunks_created: 0, status: 'skipped' } });
    const { user } = render();
    await screen.findByText('handbook');
    await user.click(screen.getByRole('button', { name: `${SYS}.reindexButton` }));
    await waitFor(() => expect(toast.info).toHaveBeenCalledWith(`${SYS}.reindexUpToDate`));
    expect(toast.success).not.toHaveBeenCalled();
  });

  // 409 = another worker holds the reindex claim, so nothing ran. The generic
  // failure message would be true but useless; this one says to retry.
  it('distinguishes a concurrent reindex from a failure', async () => {
    stubTransport([space()], {}, { reindexStatus: 409 });
    const { user } = render();
    await screen.findByText('handbook');
    await user.click(screen.getByRole('button', { name: `${SYS}.reindexButton` }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(`${SYS}.reindexInProgress`));
  });
});

describe('AdminRAGSpacesSection — global reindex', () => {
  it('never triggers the global reindex without an explicit confirmation', async () => {
    const { user } = render();
    await screen.findByText('handbook');
    await user.click(screen.getByRole('button', { name: `${I18N}.reindexButton` }));
    await screen.findByText(`${I18N}.reindexConfirmTitle`);
    expect(triggerReindex).not.toHaveBeenCalled();
    await user.click(screen.getByRole('button', { name: 'common.cancel' }));
    expect(triggerReindex).not.toHaveBeenCalled();
  });

  it('starts the global reindex once confirmed', async () => {
    const { user } = render();
    await screen.findByText('handbook');
    await user.click(screen.getByRole('button', { name: `${I18N}.reindexButton` }));
    await user.click(await screen.findByRole('button', { name: `${I18N}.reindexConfirmAction` }));
    await waitFor(() => expect(triggerReindex).toHaveBeenCalledWith(REINDEX_ENDPOINT));
    expect(toast.success).toHaveBeenCalledWith(`${I18N}.reindexStarted`);
  });

  it('reports a refused global reindex', async () => {
    triggerReindex.mockRejectedValue(new Error('busy'));
    const { user } = render();
    await screen.findByText('handbook');
    await user.click(screen.getByRole('button', { name: `${I18N}.reindexButton` }));
    await user.click(await screen.findByRole('button', { name: `${I18N}.reindexConfirmAction` }));
    await waitFor(() => expect(toast.error).toHaveBeenCalledWith(`${I18N}.reindexError`));
  });
});
