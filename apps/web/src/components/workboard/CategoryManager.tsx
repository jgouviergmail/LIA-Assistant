'use client';
/**
 * Administering the categories of a board (ADR-276).
 *
 * A category is a lane: creating one splits the board, renaming one renames
 * its lane, the order here is the order of the lanes, and deleting one sends
 * its tickets back to the unfiled lane — never a ticket with it. This dialog
 * is the ONLY place a category is created, renamed, reordered or deleted: the
 * assistant reads them and files tickets under them, and administers nothing
 * (owner arbitration, 2026-11-11).
 *
 * Four things here are decisions, not styling:
 *
 * - **A name is written when its field is left, or on Enter** — never on each
 *   key, and never twice for one edit. A name the server refuses gives the
 *   stored one back: a field showing a name that was not saved would be a lie
 *   the next refresh corrects under the reader's eyes.
 * - **The writes go one at a time, in the order they were asked.** Leaving a
 *   field writes its name, and the click that left it may be a move: both must
 *   happen, and two moves computed from the same list must not race.
 * - **The cap is stated, and explains itself.** « Add » at the cap is
 *   `aria-disabled` with a guard, never `disabled`: it stays in the tab order
 *   and says why (ADR-184 — the bound the server enforces is published).
 * - **The cursor follows the category that moved.** Reordering re-inserts the
 *   row's node, and a re-inserted node loses the focus; it is given back to the
 *   same control of the same category, so three presses move it three places.
 */
import { useCallback, useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import { Input } from '@/components/ui/input';
import { RowActions } from '@/components/ui/row-actions';
import { Skeleton } from '@/components/ui/skeleton';
import { useConfirm } from '@/components/ui/use-confirm';
import type { UseWorkboardCategoriesResult } from '@/hooks/useWorkboardCategories';
import { ArrowDown, ArrowUp, Plus, Tags, Trash2 } from '@/lib/icons';
import { TOO_MANY_CATEGORIES, toastWorkboardError } from '@/lib/workboard/errors';
import type { CategoryRow } from '@/types/workboard';

/** What the dialog reads and writes: the reader's categories and their three verbs. */
export type CategorySource = Pick<
  UseWorkboardCategoriesResult,
  'own' | 'maxCategories' | 'nameMaxChars' | 'firstLoad' | 'error' | 'create' | 'update' | 'remove'
>;

export interface CategoryManagerProps {
  open: boolean;
  onClose: () => void;
  source: CategorySource;
  /** A category was created, renamed, moved or deleted: the board's lanes changed. */
  onChanged: () => void;
}

/** Whether the focus is nowhere a person left it: on the page, or on the dialog's own box. */
function focusIsLost(): boolean {
  const active = document.activeElement;
  return !active || active === document.body || active.getAttribute('role') === 'dialog';
}

interface CategoryLineProps {
  category: CategoryRow;
  first: boolean;
  last: boolean;
  nameMaxChars: number | undefined;
  onRename: (category: CategoryRow, name: string) => Promise<void>;
  onMove: (category: CategoryRow, delta: -1 | 1, label: string) => void;
  onDelete: (category: CategoryRow) => void;
}

function CategoryLine({
  category,
  first,
  last,
  nameMaxChars,
  onRename,
  onMove,
  onDelete,
}: CategoryLineProps) {
  const { t } = useTranslation();
  // What is being typed; null while the field shows the stored name.
  const [draft, setDraft] = useState<string | null>(null);
  const committing = useRef(false);
  const { name } = category;
  const upLabel = t('workboard.categories.move_up', { name });
  const downLabel = t('workboard.categories.move_down', { name });

  const commit = async () => {
    // Enter then Tab is ONE edit: the second ask finds the first under way.
    if (draft === null || committing.current) return;
    const wanted = draft.trim();
    // Blanked, or left as it was: not a rename.
    if (wanted && wanted !== name) {
      committing.current = true;
      await onRename(category, wanted);
      committing.current = false;
    }
    // Written or refused, the field shows what is STORED from here on.
    setDraft(null);
  };

  return (
    <li data-category-id={category.id} className="flex flex-col gap-2 sm:flex-row sm:items-center">
      {/* The wrapper is what the row measures: the field's own frame is
          full-width and would push the actions off the line. */}
      <div className="min-w-0 flex-1">
        <Input
          aria-label={t('workboard.categories.name_label', { name })}
          value={draft ?? name}
          maxLength={nameMaxChars}
          onChange={event => setDraft(event.target.value)}
          onBlur={() => void commit()}
          onKeyDown={event => {
            if (event.key === 'Enter') void commit();
          }}
        />
      </div>
      <div className="flex items-center justify-between gap-2 sm:justify-end">
        <span className="shrink-0 text-xs text-muted-foreground">
          {t('workboard.board.column_count', { count: category.ticket_count })}
        </span>
        <RowActions
          menuLabel={t('workboard.categories.actions', { name })}
          actions={[
            {
              key: 'up',
              label: upLabel,
              menuText: t('workboard.categories.move_up_short'),
              icon: ArrowUp,
              // Stated, never removed: after a move to the top the control
              // still holds the focus, and `disabled` would drop it.
              blocked: first,
              onSelect: () => onMove(category, -1, upLabel),
            },
            {
              key: 'down',
              label: downLabel,
              menuText: t('workboard.categories.move_down_short'),
              icon: ArrowDown,
              blocked: last,
              onSelect: () => onMove(category, 1, downLabel),
            },
            {
              key: 'delete',
              label: t('workboard.categories.delete', { name }),
              menuText: t('workboard.card.delete'),
              icon: Trash2,
              tone: 'destructive',
              onSelect: () => onDelete(category),
            },
          ]}
        />
      </div>
    </li>
  );
}

export function CategoryManager({ open, onClose, source, onChanged }: CategoryManagerProps) {
  const { t } = useTranslation();
  const { confirm, confirmDialog } = useConfirm();
  const { own, maxCategories, nameMaxChars } = source;
  const [name, setName] = useState('');
  // How many writes are queued or under way: the list says it is busy.
  const [pending, setPending] = useState(0);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const adding = useRef(false);
  const list = useRef<HTMLUListElement>(null);
  const newField = useRef<HTMLInputElement>(null);
  // Where the cursor goes once the list has been re-read, if the re-read left
  // it nowhere. Armed by the write that will move or remove the focused row.
  const landing = useRef<(() => void) | null>(null);

  const full = maxCategories !== undefined && own.length >= maxCategories;

  useEffect(() => {
    const land = landing.current;
    landing.current = null;
    if (land && focusIsLost()) land();
  }, [own]);

  /** One write at a time, in the order they were asked. */
  const run = useCallback(async <T,>(task: () => Promise<T>): Promise<T> => {
    const turn = queue.current.then(task);
    queue.current = turn.then(
      () => undefined,
      () => undefined
    );
    setPending(count => count + 1);
    try {
      return await turn;
    } finally {
      setPending(count => count - 1);
    }
  }, []);

  const add = async () => {
    const wanted = name.trim();
    if (!wanted || adding.current) return;
    if (full) {
      // The server would refuse it: say why here, and send nothing.
      toastWorkboardError(t, TOO_MANY_CATEGORIES);
      return;
    }
    adding.current = true;
    const outcome = await run(() => source.create({ name: wanted }));
    adding.current = false;
    if (!outcome.ok) {
      toastWorkboardError(t, outcome.errorCode);
      return;
    }
    toast.success(t('workboard.categories.created'));
    setName('');
    onChanged();
  };

  const rename = async (category: CategoryRow, wanted: string) => {
    const outcome = await run(() => source.update(category.id, { name: wanted }));
    if (!outcome.ok) {
      toastWorkboardError(t, outcome.errorCode);
      return;
    }
    toast.success(t('workboard.categories.renamed'));
    onChanged();
  };

  /** Give the focus back to one control of one category's line. */
  const focusControl = (categoryId: string, label: string) => {
    const line = Array.from(list.current?.children ?? []).find(
      item => item.getAttribute('data-category-id') === categoryId
    );
    const buttons = Array.from(line?.querySelectorAll('button') ?? []);
    const control = buttons.find(button => button.getAttribute('aria-label') === label);
    control?.focus();
    // On a phone the three controls are folded into the line's menu and the
    // icon cannot take the focus: the menu's own trigger takes it.
    if (control && document.activeElement !== control) {
      buttons.find(button => button.getAttribute('aria-haspopup') === 'menu')?.focus();
    }
  };

  const move = (category: CategoryRow, delta: -1 | 1, label: string) => {
    const index = own.findIndex(row => row.id === category.id);
    const position = index + delta;
    // The first cannot go up nor the last down: the control says so, and this
    // is what makes it true.
    if (index < 0 || position < 0 || position >= own.length) return;
    void run(async () => {
      landing.current = () => focusControl(category.id, label);
      const outcome = await source.update(category.id, { position });
      if (outcome.ok) onChanged();
      else {
        landing.current = null;
        toastWorkboardError(t, outcome.errorCode);
      }
    });
  };

  const remove = async (category: CategoryRow) => {
    const accepted = await confirm({
      title: t('workboard.categories.delete_confirm_title'),
      // The EXACT number of tickets that go back to the unfiled lane — the
      // list's own count, which the server computed (ADR-185).
      description:
        category.ticket_count > 0
          ? t('workboard.categories.delete_confirm_body', {
              name: category.name,
              count: category.ticket_count,
            })
          : t('workboard.categories.delete_confirm_body_empty', { name: category.name }),
      confirmLabel: t('workboard.card.delete'),
    });
    if (!accepted) return;
    const outcome = await run(() => {
      // The line is about to go, and the focus with it.
      landing.current = () => newField.current?.focus();
      return source.remove(category.id);
    });
    if (!outcome.ok) {
      landing.current = null;
      toastWorkboardError(t, outcome.errorCode);
      return;
    }
    toast.success(t('workboard.categories.deleted'));
    onChanged();
  };

  return (
    <Dialog
      open={open}
      onOpenChange={next => {
        if (!next) onClose();
      }}
    >
      <DialogContent className="max-w-lg">
        <DialogHeader>
          <DialogTitle className="flex items-center gap-2">
            <Tags className="h-5 w-5 shrink-0 text-primary" aria-hidden="true" />
            {t('workboard.categories.title')}
          </DialogTitle>
          <DialogDescription>{t('workboard.categories.description')}</DialogDescription>
        </DialogHeader>

        <div className="space-y-4">
          {source.firstLoad ? (
            <div className="space-y-2">
              <Skeleton className="h-10 w-full" />
              <Skeleton className="h-10 w-full" />
            </div>
          ) : source.error ? (
            // « None yet » would be a claim: the list was not read.
            <p className="text-sm text-muted-foreground">{t('workboard.load_error')}</p>
          ) : own.length === 0 ? (
            <p className="text-sm text-muted-foreground">{t('workboard.categories.empty')}</p>
          ) : (
            <ul ref={list} className="space-y-3 sm:space-y-2" aria-busy={pending > 0}>
              {own.map((category, index) => (
                <CategoryLine
                  key={category.id}
                  category={category}
                  first={index === 0}
                  last={index === own.length - 1}
                  nameMaxChars={nameMaxChars}
                  onRename={rename}
                  onMove={move}
                  onDelete={target => void remove(target)}
                />
              ))}
            </ul>
          )}

          <form
            className="flex items-end gap-2 border-t border-border pt-4"
            onSubmit={event => {
              event.preventDefault();
              void add();
            }}
          >
            <div className="min-w-0 flex-1">
              <Input
                ref={newField}
                label={t('workboard.categories.new_label')}
                labelEnd={
                  maxCategories !== undefined && (
                    <span className="text-xs text-muted-foreground">
                      {t('workboard.categories.capacity', {
                        used: own.length,
                        max: maxCategories,
                      })}
                    </span>
                  )
                }
                placeholder={t('workboard.categories.new_placeholder')}
                value={name}
                maxLength={nameMaxChars}
                onChange={event => setName(event.target.value)}
              />
            </div>
            {/* `aria-disabled` plus the guard in `add`: at the cap the button
                stays reachable and says why it does nothing. */}
            <Button type="submit" aria-disabled={full || !name.trim()}>
              <Plus className="h-4 w-4" aria-hidden="true" />
              {t('workboard.categories.add')}
            </Button>
          </form>

          <div className="flex justify-end">
            <Button variant="outline" onClick={onClose}>
              {t('workboard.actions.close')}
            </Button>
          </div>
        </div>

        {confirmDialog}
      </DialogContent>
    </Dialog>
  );
}
