'use client';

import { useState, type Ref } from 'react';
import { useTranslation } from 'react-i18next';
import {
  ChevronDown,
  Check,
  Download,
  MessageSquare,
  Pencil,
  Pin,
  Plus,
  Trash2,
} from '@/lib/icons';
import { Button } from '@/components/ui/button';
import { LoadingSpinner } from '@/components/ui/loading-spinner';
import { RowActions, type RowAction } from '@/components/ui/row-actions';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from '@/components/ui/dialog';
import type {
  ConversationCatalogueConfig,
  ConversationCataloguePage,
  ConversationCreateRequest,
  ConversationSummary,
} from '@/types/conversation';
import { discussionExportUrl } from '@/lib/discussion-export';
import { ConversationCreateDialog, ConversationTitleDialog } from './ConversationCreateDialog';
import { ConversationRetirementConfirm } from './ConversationRetirementConfirm';

export interface ConversationSwitcherProps {
  current: ConversationSummary | null;
  page?: ConversationCataloguePage;
  visibleItems?: ConversationSummary[];
  needsRecount?: boolean;
  loading: boolean;
  error: boolean;
  rules: ConversationCatalogueConfig;
  /** A translated reason while leaving this view would cancel local work. */
  blockedReason?: string;
  triggerRef?: Ref<HTMLButtonElement>;
  onOpen: () => void;
  onSelect: (target: ConversationSummary | null) => void;
  onCreate: (request: ConversationCreateRequest) => Promise<void>;
  onRename: (target: ConversationSummary, title: string) => Promise<void>;
  onDelete: (target: ConversationSummary, operationId: string) => Promise<void>;
  onPage: (offset: number) => void;
}

interface DiscussionRowProps {
  target: ConversationSummary | null;
  current: boolean;
  blocked: boolean;
  /**
   * Whether the discussion holds something to download. Always true for a
   * listed annex; Main's row is drawn before the account has one.
   */
  exportable: boolean;
  onSelect: (target: ConversationSummary | null) => void;
  onDelete: (target: ConversationSummary) => void;
  onRename: (target: ConversationSummary) => void;
}

function DiscussionRow({
  target,
  current,
  blocked,
  exportable,
  onSelect,
  onDelete,
  onRename,
}: DiscussionRowProps) {
  const { t } = useTranslation();
  const annex = target?.kind === 'secondary' ? target : null;
  const title = annex?.title ?? t('chat.discussions.main');
  // A download, so a real link the browser handles — and never blocked: it
  // leaves the discussion, its draft and the running turn as they are.
  const actions: RowAction[] = exportable
    ? [
        {
          key: 'export',
          label: t('chat.discussions.export_action', { title }),
          menuText: t('chat.discussions.export'),
          icon: Download,
          href: discussionExportUrl(target),
          onSelect: () => undefined,
        },
      ]
    : [];
  if (annex)
    actions.push(
      {
        key: 'rename',
        label: t('chat.discussions.rename_action', { title }),
        menuText: t('chat.discussions.rename'),
        icon: Pencil,
        onSelect: () => onRename(annex),
      },
      {
        key: 'delete',
        label: t('chat.discussions.delete_action', { title }),
        menuText: t('chat.discussions.delete'),
        icon: Trash2,
        tone: 'destructive',
        onSelect: () => onDelete(annex),
      }
    );
  return (
    <li className="flex min-w-0 items-center gap-1 border-b last:border-b-0">
      <Button
        type="button"
        variant="ghost"
        className="min-h-11 h-auto min-w-0 flex-1 justify-start gap-2 px-2 text-left"
        aria-current={current ? 'true' : undefined}
        aria-disabled={blocked && !current ? true : undefined}
        onClick={() => {
          if (!blocked || current) onSelect(target);
        }}
      >
        {annex ? <MessageSquare aria-hidden="true" /> : <Pin aria-hidden="true" />}
        <bdi className="min-w-0 truncate" title={title}>
          {title}
        </bdi>
        {current && <Check className="ms-auto text-primary" aria-hidden="true" />}
      </Button>
      {actions.length > 0 && (
        <RowActions menuLabel={t('chat.discussions.row_actions', { title })} actions={actions} />
      )}
    </li>
  );
}

interface CatalogueListProps extends Pick<
  ConversationSwitcherProps,
  'current' | 'page' | 'visibleItems'
> {
  busy: boolean;
  blocked: boolean;
  onSelect: (target: ConversationSummary | null) => void;
  onDelete: (target: ConversationSummary) => void;
  onRename: (target: ConversationSummary) => void;
}

/** The discussions on screen: Main first, then the annexes of the page. */
function CatalogueList({
  current,
  page,
  visibleItems,
  busy,
  blocked,
  onSelect,
  onDelete,
  onRename,
}: CatalogueListProps) {
  const rows = visibleItems ?? page?.items ?? [];
  return (
    <ul
      aria-busy={busy}
      className="max-h-[45dvh] min-w-0 overflow-y-auto rounded-lg border bg-card px-1"
    >
      <DiscussionRow
        target={rows.find(row => row.kind === 'main') ?? null}
        current={current?.kind !== 'secondary'}
        blocked={blocked}
        // Main exists as soon as the account has one discussion; a page
        // further down the list does not hold its row.
        exportable={(page?.total_count ?? 0) > 0}
        onSelect={onSelect}
        onDelete={onDelete}
        onRename={onRename}
      />
      {rows
        .filter(row => row.kind === 'secondary')
        .map(row => (
          <DiscussionRow
            key={row.id}
            target={row}
            current={row.id === current?.id}
            blocked={blocked}
            exportable
            onSelect={onSelect}
            onDelete={onDelete}
            onRename={onRename}
          />
        ))}
    </ul>
  );
}

const PAGING_INERT = 'aria-disabled:cursor-not-allowed aria-disabled:opacity-60';

function CataloguePaging({
  page,
  offsetMax,
  busy,
  onPage,
}: {
  page: ConversationCataloguePage;
  offsetMax: number;
  busy: boolean;
  onPage: (offset: number) => void;
}) {
  const { t, i18n } = useTranslation();
  const next = page.offset + page.limit;
  const hasNext = next < page.total_count && next <= offsetMax;
  const count = new Intl.NumberFormat(i18n.language).format(page.total_count);
  // The press that asks for a page is what makes the list busy: `disabled`
  // would blur the very button it landed on. The guard prevents the second
  // request; the attribute only says so.
  const turnTo = (offset: number) => {
    if (!busy) onPage(offset);
  };
  return (
    <div className="flex flex-wrap items-center gap-2 text-sm">
      <p className="me-auto text-muted-foreground">
        {t('chat.discussions.total', { count: page.total_count, formatted: count })}
      </p>
      {page.offset > 0 && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className={PAGING_INERT}
          aria-disabled={busy || undefined}
          onClick={() => turnTo(Math.max(0, page.offset - page.limit))}
        >
          {t('chat.discussions.previous')}
        </Button>
      )}
      {hasNext && (
        <Button
          type="button"
          size="sm"
          variant="outline"
          className={PAGING_INERT}
          aria-disabled={busy || undefined}
          onClick={() => turnTo(next)}
        >
          {t('chat.discussions.next')}
        </Button>
      )}
    </div>
  );
}

type Dialogue = { kind: 'create' } | { kind: 'rename' | 'delete'; row: ConversationSummary };

function CatalogueDialogue({
  dialogue,
  rules,
  onCreate,
  onRename,
  onDelete,
  onClose,
}: Pick<ConversationSwitcherProps, 'rules' | 'onCreate' | 'onRename' | 'onDelete'> & {
  dialogue: Dialogue | null;
  onClose: () => void;
}) {
  if (dialogue === null) return null;
  switch (dialogue.kind) {
    case 'create':
      return <ConversationCreateDialog rules={rules} onCreate={onCreate} onClose={onClose} />;
    case 'rename':
      return (
        <ConversationTitleDialog
          rules={rules}
          initialTitle={dialogue.row.title ?? ''}
          heading="chat.discussions.rename"
          description="chat.discussions.rename_description"
          actionLabel="common.save"
          onSubmitTitle={title => onRename(dialogue.row, title)}
          onClose={onClose}
          refusalKey={status =>
            status === 409 ? 'chat.discussions.rename_changed' : 'chat.discussions.rename_error'
          }
        />
      );
    case 'delete':
      return (
        <ConversationRetirementConfirm
          action="delete"
          target={dialogue.row}
          onConfirm={onDelete}
          onClose={onClose}
        />
      );
  }
}

function CatalogueFeedback({
  loading,
  error,
  retry,
}: {
  loading: boolean;
  error: boolean;
  retry: () => void;
}) {
  const { t } = useTranslation();
  return (
    <>
      {loading && (
        <p role="status" className="flex items-center gap-2 text-sm">
          <LoadingSpinner aria-hidden="true" />
          {t('chat.discussions.loading')}
        </p>
      )}
      {error && (
        <div role="alert" className="flex flex-wrap items-center gap-2 text-sm">
          <span className="text-destructive">{t('chat.discussions.list_error')}</span>
          <Button type="button" variant="outline" size="sm" onClick={retry}>
            {t('common.retry')}
          </Button>
        </div>
      )}
    </>
  );
}

export function ConversationSwitcher({
  current,
  page,
  visibleItems,
  needsRecount,
  loading,
  error,
  rules,
  blockedReason,
  triggerRef,
  onOpen,
  onSelect,
  onCreate,
  onRename,
  onDelete,
  onPage,
}: ConversationSwitcherProps) {
  const { t } = useTranslation();
  const [open, setOpen] = useState(false);
  const [dialogue, setDialogue] = useState<Dialogue | null>(null);
  const title =
    (current?.kind === 'secondary' ? current.title : null) ?? t('chat.discussions.main');

  function select(target: ConversationSummary | null) {
    setOpen(false);
    onSelect(target);
  }

  return (
    <Dialog
      open={open}
      onOpenChange={value => {
        setOpen(value);
        if (value) onOpen();
      }}
    >
      <DialogTrigger asChild>
        <Button
          ref={triggerRef}
          type="button"
          variant="softPrimary"
          size="sm"
          className="min-h-10 max-w-full min-w-0 gap-1.5 rounded-full px-2.5"
          aria-label={t('chat.discussions.open', { title })}
        >
          <MessageSquare aria-hidden="true" />
          {/* Under 19rem of header the centre group wraps as a net
              (`ChatWorkspaceToolbar`): a short title keeps it on one line. */}
          <bdi title={title} className="max-w-24 truncate @max-[19rem]:max-w-6 lg:max-w-40">
            {title}
          </bdi>
          {/* The title needs the room more than the pill needs its arrow
              (`lib/mobile-visibility.ts`). */}
          <ChevronDown className="hidden !size-3.5 @min-[640px]:block" aria-hidden="true" />
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-md">
        <DialogHeader className="pe-10">
          <DialogTitle>{t('chat.discussions.heading')}</DialogTitle>
          <DialogDescription>{t('chat.discussions.description')}</DialogDescription>
        </DialogHeader>
        {blockedReason && (
          <p role="status" className="text-sm">
            {blockedReason}
          </p>
        )}
        <CatalogueList
          current={current}
          page={page}
          visibleItems={visibleItems}
          busy={loading}
          blocked={Boolean(blockedReason)}
          onSelect={select}
          onDelete={row => setDialogue({ kind: 'delete', row })}
          onRename={row => setDialogue({ kind: 'rename', row })}
        />
        <CatalogueFeedback loading={loading} error={error} retry={onOpen} />
        {page && !needsRecount && (
          <CataloguePaging
            page={page}
            busy={loading}
            offsetMax={rules.offset_max}
            onPage={onPage}
          />
        )}
        <DialogFooter>
          <Button
            type="button"
            disabled={!rules.creation_enabled || Boolean(blockedReason)}
            onClick={() => setDialogue({ kind: 'create' })}
          >
            <Plus aria-hidden="true" />
            {t('chat.discussions.new')}
          </Button>
        </DialogFooter>
        {!rules.creation_enabled && (
          <p className="text-sm text-muted-foreground">{t('chat.discussions.creation_disabled')}</p>
        )}
        <CatalogueDialogue
          dialogue={dialogue}
          rules={rules}
          onCreate={onCreate}
          onRename={onRename}
          onDelete={onDelete}
          onClose={() => setDialogue(null)}
        />
      </DialogContent>
    </Dialog>
  );
}
