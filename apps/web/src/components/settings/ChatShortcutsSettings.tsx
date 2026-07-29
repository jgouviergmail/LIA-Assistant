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

import { useState } from 'react';
import { TerminalSquare, Trash2 } from 'lucide-react';
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

export function ChatShortcutsSettings({ lng, collapsible = true }: BaseSettingsProps) {
  const { t } = useTranslation(lng);
  const { shortcuts, maxCount, loading, save, saving } = useChatShortcuts();
  const [draftId, setDraftId] = useState('');
  const [draftText, setDraftText] = useState('');
  const [formError, setFormError] = useState<ShortcutIdError>(null);

  const atCapacity = maxCount > 0 && shortcuts.length >= maxCount;

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
  };

  const content = loading ? null : (
    <div className="space-y-4">
      <p className="text-xs text-muted-foreground">{t('settings.chat_shortcuts.description')}</p>

      {shortcuts.length === 0 ? (
        <p className="text-sm italic text-muted-foreground">{t('settings.chat_shortcuts.empty')}</p>
      ) : (
        <ul className="space-y-1" role="list">
          {shortcuts.map(shortcut => (
            <li
              key={shortcut.id}
              className="flex items-center gap-3 rounded-lg border border-border/40 bg-card/60 px-3 py-2"
            >
              <code className="shrink-0 text-sm font-semibold text-primary">/{shortcut.id}</code>
              <span className="min-w-0 flex-1 truncate text-sm text-muted-foreground">
                {shortcut.text}
              </span>
              <button
                type="button"
                onClick={() => void handleRemove(shortcut.id)}
                disabled={saving}
                aria-label={t('settings.chat_shortcuts.remove', { id: shortcut.id })}
                className="p-1.5 rounded-md border border-border/30 bg-background/80 hover:bg-background text-muted-foreground hover:text-destructive disabled:opacity-50"
              >
                <Trash2 className="h-3.5 w-3.5" aria-hidden />
              </button>
            </li>
          ))}
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
          <div className="space-y-1.5">
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
          <div className="space-y-1.5">
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

  if (!collapsible) {
    return content;
  }

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
