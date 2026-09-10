'use client';
/**
 * The workboard screen (ADR-276).
 *
 * The board is reached from a settings section and from every ticket
 * notification — never from the header, which is at its measured maximum of
 * seven destinations (D15). Two routes land here: `/dashboard/workboard`, which
 * reads `?ticket=`, and `/dashboard/workboard/<id>`, which the backend builds
 * in every notification. Both mount THIS component, so a ticket link and a
 * board link cannot drift apart.
 *
 * The URL carries the open ticket, so a panel is a link somebody can send.
 */
import { useCallback, useEffect, useState } from 'react';
import { useRouter, useSearchParams } from 'next/navigation';
import { LayoutGrid, Plus } from 'lucide-react';
import { toast } from 'sonner';

import { SectionToolbar } from '@/components/settings/SectionToolbar';
import { EmptyState } from '@/components/ui/empty-state';
import { LoadingAnnouncement } from '@/components/ui/loading-announcement';
import { Skeleton } from '@/components/ui/skeleton';
import { useConfirm } from '@/components/ui/use-confirm';
import { Board } from '@/components/workboard/Board';
import { BoardFilters } from '@/components/workboard/BoardFilters';
import { TicketDetailPanel } from '@/components/workboard/TicketDetailPanel';
import { TicketForm } from '@/components/workboard/TicketForm';
import { useAuth } from '@/hooks/useAuth';
import { usePeerRecipients } from '@/hooks/usePeerRecipients';
import { useWorkboard } from '@/hooks/useWorkboard';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { toastWorkboardError } from '@/lib/workboard/errors';
import { filtersFromParams, writeFilters } from '@/lib/workboard/filters-url';
import type { BoardFilters as Filters, TicketRow } from '@/types/workboard';

export interface WorkboardPageProps {
  lng: Language;
  /** The ticket the route named, when the URL carried one in its path. */
  initialTicketId?: string;
}

export function WorkboardPage({ lng, initialTicketId }: WorkboardPageProps) {
  const { t } = useTranslation(lng);
  const router = useRouter();
  const params = useSearchParams();
  const { user } = useAuth();
  const peers = usePeerRecipients(true);
  const { confirm, confirmDialog } = useConfirm();

  // The filters START from the URL — a settings figure links into a narrowed
  // board — and the URL then FOLLOWS them (below), never the reverse while a
  // person types: a search box whose value came back through the router
  // dropped every second keystroke.
  const [filters, setFilters] = useState<Filters>(() =>
    filtersFromParams(new URLSearchParams(Array.from(params.entries())))
  );
  const [creating, setCreating] = useState(false);
  // Bumped after every write so the open panel re-reads the ticket it shows.
  const [revision, setRevision] = useState(0);
  // A drag is the one moment a refreshed payload would be felt, so the page
  // holds the poll for its duration rather than the hook guessing at it.
  const [dragging, setDragging] = useState(false);
  const board = useWorkboard(filters, { paused: dragging });

  useEffect(() => {
    const current = window.location.search.replace(/^\?/, '');
    const next = writeFilters(new URLSearchParams(current), filters).toString();
    if (next === current) return;
    router.replace(`/${lng}/dashboard/workboard${next ? `?${next}` : ''}`, { scroll: false });
  }, [filters, lng, router]);

  // The open ticket is DERIVED from the URL, never mirrored into state: a panel
  // is then a link somebody can send, the browser's back button closes it, and
  // there is no second authority to keep in step. `initialTicketId` is the path
  // form (`/dashboard/workboard/<id>`), which the backend puts in every ticket
  // notification; `?ticket=` is what the board itself writes.
  const open = initialTicketId ?? params.get('ticket');

  const openTicket = useCallback(
    (id: string | null) => {
      const next = new URLSearchParams(Array.from(params.entries()));
      if (id) next.set('ticket', id);
      else next.delete('ticket');
      const query = next.toString();
      router.replace(`/${lng}/dashboard/workboard${query ? `?${query}` : ''}`, { scroll: false });
    },
    [lng, params, router]
  );

  /** Run one write, say what was refused, and let the panel re-read. */
  const settle = useCallback(
    async (call: Promise<{ ok: boolean; errorCode: string | null }>) => {
      const result = await call;
      if (!result.ok) toastWorkboardError(t, result.errorCode);
      else setRevision(value => value + 1);
      return result;
    },
    [t]
  );

  const onDelete = useCallback(
    async (id: string, title: string) => {
      const accepted = await confirm({
        title: t('workboard.delete_confirm.title'),
        description: t('workboard.delete_confirm.body', { title }),
        confirmLabel: t('workboard.card.delete'),
      });
      if (!accepted) return;
      const result = await board.remove(id);
      if (result.ok) {
        toast.success(t('workboard.deleted'));
        // Only when the panel showing it is open: deleting from a CARD must not
        // push a URL for a panel nobody opened.
        if (open === id) openTicket(null);
      } else {
        toastWorkboardError(t, result.errorCode);
      }
    },
    [board, confirm, open, openTicket, t]
  );

  if (board.isUnavailable) {
    return (
      <EmptyState
        icon={LayoutGrid}
        title={t('workboard.title')}
        description={t('workboard.unavailable')}
      />
    );
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="flex items-center gap-2 text-3xl font-bold tracking-tight">
          <LayoutGrid className="h-7 w-7 text-primary" aria-hidden="true" />
          {t('workboard.title')}
        </h1>
        <p className="mt-1 text-sm text-muted-foreground">{t('workboard.subtitle')}</p>
      </div>

      {/* No « refresh » button: the board re-reads itself (every 30 s, on
          focus, after every write) and a button for it said the opposite
          (owner, 2026-09-10). */}
      <SectionToolbar
        count={t('workboard.filters.total', { count: board.total })}
        primary={{
          key: 'create',
          label: t('workboard.actions.create'),
          icon: Plus,
          onSelect: () => setCreating(true),
        }}
        menuLabel={t('common.more_actions')}
      />

      <BoardFilters lng={lng} filters={filters} onChange={setFilters} />

      {board.firstLoad ? (
        <>
          <LoadingAnnouncement />
          <div className="flex gap-3 overflow-hidden">
            {[0, 1, 2, 3].map(index => (
              <Skeleton key={index} className="h-64 w-72 shrink-0" />
            ))}
          </div>
        </>
      ) : board.error ? (
        <EmptyState icon={LayoutGrid} description={t('workboard.load_error')} />
      ) : board.total === 0 ? (
        <EmptyState
          icon={LayoutGrid}
          variant="page"
          reason={hasFilters(filters) ? 'no-match' : 'no-data'}
          title={
            hasFilters(filters) ? t('workboard.empty.filtered_title') : t('workboard.empty.title')
          }
          description={
            hasFilters(filters)
              ? t('workboard.empty.filtered_description')
              : t('workboard.empty.description')
          }
          action={{ label: t('workboard.actions.create'), onClick: () => setCreating(true) }}
        />
      ) : (
        <div aria-busy={board.loading}>
          {board.tickets.length < board.total && (
            <p className="mb-2 text-xs text-muted-foreground">
              {t('workboard.board.partial', {
                shown: board.tickets.length,
                total: board.total,
              })}
            </p>
          )}
          <Board
            onDragActive={setDragging}
            column={board.column}
            countsByStatus={board.countsByStatus}
            loaded={board.tickets}
            total={board.total}
            meId={user?.id}
            peers={peers}
            lng={lng}
            onOpen={openTicket}
            onMove={(id, status, position) => void settle(board.move(id, status, position))}
            onFollowChange={(id, follow) => void settle(board.patch(id, { follow }))}
            // The card's own lists where nothing drags (a phone): the same
            // writes the panel makes, so the two cannot disagree.
            onStatusChange={(id, status) => void settle(board.patch(id, { status }))}
            onAssigneeChange={(id, patch) => void settle(board.patch(id, patch))}
            onDelete={(ticket: TicketRow) => void onDelete(ticket.id, ticket.title)}
          />
        </div>
      )}

      <TicketForm
        open={creating}
        lng={lng}
        peers={peers}
        onClose={() => setCreating(false)}
        onCreate={async body => {
          const result = await board.create(body);
          if (result.ok) {
            toast.success(t('workboard.created'));
            setCreating(false);
          } else {
            toastWorkboardError(t, result.errorCode);
          }
          return result;
        }}
      />

      <TicketDetailPanel
        ticketId={open}
        meId={user?.id}
        peers={peers}
        lng={lng}
        revision={revision}
        // Closing the panel re-reads the board: whatever the person did in it
        // — answered a confirmation, changed a column — the board behind must
        // already show it when the dialog goes (owner feedback, 2026-09-09).
        onClose={() => {
          openTicket(null);
          void board.refetch();
        }}
        onPatch={(id, body) => settle(board.patch(id, body))}
        onComment={(id, body) => settle(board.comment(id, body))}
        onRunNow={async id => {
          const result = await settle(board.runNow(id));
          if (result.ok) toast.success(t('workboard.run_requested'));
          return result;
        }}
        onDelete={onDelete}
      />

      {confirmDialog}
    </div>
  );
}

/** Whether the reader narrowed the board — « nothing yet » is not « no match ». */
function hasFilters(filters: Filters): boolean {
  return Boolean(
    filters.q?.trim() ||
    filters.overdue ||
    filters.priority?.length ||
    filters.status?.length ||
    (filters.assignee && filters.assignee !== 'all')
  );
}
