'use client';

/**
 * ChatShortcutsSettings — CRUD of the user's own `/shortcuts` (SLASH admin
 * lot; server-persisted in users.chat_shortcuts, full-replace PUT).
 *
 * Validation mirrors the backend schema (lowercase slug, blank text refused,
 * duplicates refused) and adds the one rule the backend deliberately does not
 * know: ids of the STATIC commands are reserved — the registry belongs to the
 * frontend, so the collision is refused where the registry lives.
 * Errors are inline text (role=alert), never color or toast alone.
 */

import { useRef, useState } from 'react';
import { Check, Pencil, TerminalSquare, Trash2, X } from 'lucide-react';
import { toast } from 'sonner';

import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { Textarea } from '@/components/ui/textarea';
import { useChatShortcuts } from '@/hooks/useChatShortcuts';
import { validateShortcutId, type ShortcutIdError } from '@/lib/slash-commands';
import { CHAT_SHORTCUT_ID_MAX_LENGTH, CHAT_SHORTCUT_TEXT_MAX_LENGTH } from '@/lib/constants';
import { useTranslation } from '@/i18n/client';
import type { BaseSettingsProps } from '@/types/settings';

/** A shortcut in read mode: what it is, and the two ways to change it. */
function ShortcutRow({
  shortcut,
  saving,
  t,
  onEdit,
  onRemove,
}: {
  shortcut: { id: string; text: string };
  saving: boolean;
  t: (key: string, options?: Record<string, unknown>) => string;
  onEdit: () => void;
  onRemove: () => void;
}) {
  return (
    <li className="flex items-center gap-3 rounded-lg border border-border/40 bg-card/60 px-3 py-2">
      <code className="shrink-0 text-sm font-semibold text-primary">/{shortcut.id}</code>
      <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">{shortcut.text}</span>
      {/* Row actions follow the passkeys pattern (ADR-207): design-system
          ghost icon buttons, and the DELETE one carries its red at rest — the
          hand-written pills here were grey until hovered, so the two actions
          had no colour code at all before the pointer reached them. */}
      <Button
        type="button"
        variant="ghost"
        size="icon"
        onClick={onEdit}
        disabled={saving}
        aria-label={t('settings.chat_shortcuts.edit', { id: shortcut.id })}
      >
        <Pencil className="h-4 w-4" aria-hidden />
      </Button>
      <Button
        type="button"
        variant="ghost"
        size="icon"
        className="text-destructive hover:text-destructive"
        onClick={onRemove}
        disabled={saving}
        aria-label={t('settings.chat_shortcuts.remove', { id: shortcut.id })}
      >
        <Trash2 className="h-4 w-4" aria-hidden />
      </Button>
    </li>
  );
}

export function ChatShortcutsSettings({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  // Focus parks here after a row deletion: the delete button vanishes with its
  // row, so without a deliberate destination the keyboard user lands on <body>
  // (same pattern as the routines list — see ScheduledActionsSettings).
  const listRegionRef = useRef<HTMLDivElement>(null);
  const { shortcuts, maxCount, loading, save, saving } = useChatShortcuts();
  const [draftId, setDraftId] = useState('');
  const [draftText, setDraftText] = useState('');
  const [formError, setFormError] = useState<ShortcutIdError>(null);
  // Edit mode is keyed by the ORIGINAL id: it is the only stable handle while
  // the user is retyping the id itself.
  const [editingId, setEditingId] = useState<string | null>(null);
  const [editId, setEditId] = useState('');
  const [editText, setEditText] = useState('');
  const [editError, setEditError] = useState<ShortcutIdError>(null);

  const atCapacity = maxCount > 0 && shortcuts.length >= maxCount;

  const startEdit = (shortcut: { id: string; text: string }) => {
    setEditingId(shortcut.id);
    setEditId(shortcut.id);
    setEditText(shortcut.text);
    setEditError(null);
  };

  const cancelEdit = () => {
    setEditingId(null);
    setEditError(null);
  };

  const handleSaveEdit = async () => {
    if (!editingId) return;
    const id = editId.trim().toLowerCase();
    const text = editText.trim();
    if (!id || !text) return;
    // The shortcut being edited is excluded from the duplicate check —
    // otherwise renaming nothing but the text would collide with itself.
    const error = validateShortcutId(
      id,
      shortcuts.filter(s => s.id !== editingId).map(s => s.id),
      CHAT_SHORTCUT_ID_MAX_LENGTH
    );
    if (error) {
      setEditError(error);
      return;
    }
    const ok = await save(shortcuts.map(s => (s.id === editingId ? { id, text } : s)));
    if (ok) {
      setEditingId(null);
      setEditError(null);
      toast.success(t('settings.chat_shortcuts.updated', { id }));
    } else {
      toast.error(t('common.error'));
    }
  };

  const handleAdd = async () => {
    const id = draftId.trim().toLowerCase();
    const text = draftText.trim();
    if (!id || !text) return;
    const error = validateShortcutId(
      id,
      shortcuts.map(s => s.id),
      CHAT_SHORTCUT_ID_MAX_LENGTH
    );
    if (error) {
      setFormError(error);
      return;
    }
    setFormError(null);
    const ok = await save([...shortcuts, { id, text }]);
    if (ok) {
      setDraftId('');
      setDraftText('');
      toast.success(t('settings.chat_shortcuts.added', { id }));
    } else {
      toast.error(t('common.error'));
    }
  };

  const handleRemove = async (id: string) => {
    const ok = await save(shortcuts.filter(s => s.id !== id));
    if (!ok) toast.error(t('common.error'));
    else listRegionRef.current?.focus();
  };

  const content = loading ? null : (
    // `tabIndex={-1}` adds no tab stop — it only makes this container a legal
    // destination for the deliberate post-deletion `.focus()`, and it outlives
    // every row, the empty state included (a ref on the <ul> would be null the
    // moment the LAST shortcut is removed).
    <div ref={listRegionRef} tabIndex={-1} className="space-y-4 focus:outline-none">
      <p className="text-xs text-muted-foreground">{t('settings.chat_shortcuts.description')}</p>

      {shortcuts.length === 0 ? (
        <p className="text-sm italic text-muted-foreground">{t('settings.chat_shortcuts.empty')}</p>
      ) : (
        <ul className="space-y-1" role="list">
          {shortcuts.map(shortcut =>
            editingId === shortcut.id ? (
              <li
                key={shortcut.id}
                className="space-y-2 rounded-lg border border-primary/40 bg-card/60 px-3 py-2"
              >
                <div className="flex flex-col gap-2 sm:flex-row sm:items-center">
                  {/* Names carry the shortcut they act on. Reusing the add
                      form's labels put two identically-named fields on the
                      page, which a screen-reader user cannot tell apart. */}
                  <Input
                    aria-label={t('settings.chat_shortcuts.edit_id_label', { id: shortcut.id })}
                    value={editId}
                    maxLength={CHAT_SHORTCUT_ID_MAX_LENGTH}
                    onChange={event => {
                      setEditId(event.target.value);
                      setEditError(null);
                    }}
                    className="sm:w-44"
                  />
                  <Input
                    aria-label={t('settings.chat_shortcuts.edit_text_label', { id: shortcut.id })}
                    value={editText}
                    maxLength={CHAT_SHORTCUT_TEXT_MAX_LENGTH}
                    onChange={event => setEditText(event.target.value)}
                    className="min-w-0 flex-1"
                  />
                  <div className="flex shrink-0 items-center gap-2">
                    <Button
                      type="button"
                      size="sm"
                      onClick={() => void handleSaveEdit()}
                      disabled={saving || !editId.trim() || !editText.trim()}
                      className="gap-1.5"
                    >
                      <Check className="h-3.5 w-3.5" aria-hidden />
                      {t('settings.chat_shortcuts.save')}
                    </Button>
                    <Button type="button" size="sm" variant="ghost" onClick={cancelEdit}>
                      <X className="h-3.5 w-3.5" aria-hidden />
                      <span className="sr-only sm:not-sr-only sm:ml-1.5">
                        {t('settings.chat_shortcuts.cancel')}
                      </span>
                    </Button>
                  </div>
                </div>
                {editError && (
                  <p className="text-sm text-destructive" role="alert">
                    {t(`settings.chat_shortcuts.error_${editError}`)}
                  </p>
                )}
              </li>
            ) : (
              <ShortcutRow
                key={shortcut.id}
                shortcut={shortcut}
                saving={saving}
                t={t}
                onEdit={() => startEdit(shortcut)}
                onRemove={() => void handleRemove(shortcut.id)}
              />
            )
          )}
        </ul>
      )}

      {maxCount > 0 && (
        <p className="text-xs text-muted-foreground tabular-nums">
          {/* `current`, not i18next's plural-triggering `count` option. */}
          {t('settings.chat_shortcuts.count', { current: shortcuts.length, max: maxCount })}
        </p>
      )}

      {atCapacity ? (
        <p className="text-sm text-muted-foreground" role="status">
          {t('settings.chat_shortcuts.limit_reached')}
        </p>
      ) : (
        <div className="space-y-3 rounded-lg border border-border/40 p-3">
          <div className="space-y-3">
            <Label htmlFor="chat-shortcut-id">{t('settings.chat_shortcuts.id_label')}</Label>
            <Input
              id="chat-shortcut-id"
              value={draftId}
              maxLength={CHAT_SHORTCUT_ID_MAX_LENGTH}
              placeholder={t('settings.chat_shortcuts.id_placeholder')}
              onChange={event => {
                setDraftId(event.target.value);
                setFormError(null);
              }}
            />
          </div>
          <div className="space-y-3">
            <Label htmlFor="chat-shortcut-text">{t('settings.chat_shortcuts.text_label')}</Label>
            <Textarea
              id="chat-shortcut-text"
              value={draftText}
              maxLength={CHAT_SHORTCUT_TEXT_MAX_LENGTH}
              rows={2}
              placeholder={t('settings.chat_shortcuts.text_placeholder')}
              onChange={event => setDraftText(event.target.value)}
            />
          </div>
          {formError && (
            <p className="text-sm text-destructive" role="alert">
              {t(`settings.chat_shortcuts.error_${formError}`)}
            </p>
          )}
          <Button
            type="button"
            size="sm"
            onClick={() => void handleAdd()}
            disabled={saving || !draftId.trim() || !draftText.trim()}
          >
            {t('settings.chat_shortcuts.add')}
          </Button>
        </div>
      )}
    </div>
  );

  return (
    <SettingsSection
      value="chat-shortcuts"
      title={t('settings.chat_shortcuts.title')}
      description={t('settings.chat_shortcuts.description')}
      icon={TerminalSquare}
    >
      {content}
    </SettingsSection>
  );
}
