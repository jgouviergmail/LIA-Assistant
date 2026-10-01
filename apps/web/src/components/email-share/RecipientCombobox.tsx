'use client';

/**
 * The recipient field of « Send by e-mail », with contact suggestions
 * (ADR-321 amendment).
 *
 * The field stays what it was — free addresses, separated by commas,
 * semicolons or spaces — and, while one recipient is being typed, the
 * account's contacts matching it by name, first name or phone number are
 * offered; picking one puts its ADDRESS in place of what was typed and opens
 * the next recipient. What is matched, and how, is the server's
 * (`GET /email-share/recipients`): accents and punctuation are ignored there,
 * by the same fold that decides who is who elsewhere.
 *
 * A WAI-ARIA combobox with a list: arrows move, Enter picks, Escape closes
 * the list (the dialog stays — `DialogContent` lets an expanded combobox have
 * its Escape first), Tab leaves. A pick is made on `mousedown`, whose default
 * is prevented, so the field never loses the focus a phone keyboard needs.
 */

import { useId, useLayoutEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Input } from '@/components/ui/input';
import { useRecipientSuggestions } from '@/hooks/useRecipientSuggestions';
import { activeRecipient, insertRecipient, parseRecipients } from '@/lib/email-share/share';
import { cn } from '@/lib/utils';

export interface RecipientComboboxProps {
  value: string;
  onChange: (value: string) => void;
  /** Already translated. */
  label: string;
  placeholder: string;
  error?: string;
  /** The published shortest query. */
  minChars: number;
  /**
   * The recipient being typed while the field has the focus, null once it
   * leaves: a name being typed to search is not yet a wrong address.
   */
  onTypingChange?: (query: string | null) => void;
}

export function RecipientCombobox({
  value,
  onChange,
  label,
  placeholder,
  error,
  minChars,
  onTypingChange,
}: RecipientComboboxProps) {
  const { t } = useTranslation();
  const inputRef = useRef<HTMLInputElement>(null);
  const pendingCaret = useRef<number | null>(null);
  const [caret, setCaret] = useState(value.length);
  const [open, setOpen] = useState(false);
  // The highlighted line, and the list it belongs to: a new list starts with
  // nothing highlighted, so Enter never picks a line the person did not move to.
  const [cursor, setCursor] = useState({ list: '', index: -1 });
  const listboxId = useId();

  const active = activeRecipient(value, caret);
  const { suggestions, truncated } = useRecipientSuggestions(active.query, true, minChars);
  // An address already in the field is not offered again.
  const chosen = new Set(
    parseRecipients(`${value.slice(0, active.start)} ${value.slice(active.end)}`).map(address =>
      address.toLowerCase()
    )
  );
  const offered = suggestions.filter(item => !chosen.has(item.email.toLowerCase()));
  const expanded = open && offered.length > 0;
  // An unquoted address holds no space: joined by one, the list is its identity.
  const list = offered.map(item => item.email).join(' ');
  const highlighted = expanded && cursor.list === list ? cursor.index : -1;
  const highlight = (index: number) => setCursor({ list, index });
  const optionId = (index: number) => `${listboxId}-option-${index}`;

  // After a pick, the caret goes after the inserted « , » — once React has
  // written the new value into the input.
  useLayoutEffect(() => {
    const at = pendingCaret.current;
    if (at === null || !inputRef.current) return;
    inputRef.current.setSelectionRange(at, at);
    pendingCaret.current = null;
  }, [value]);

  const pick = (email: string) => {
    const next = insertRecipient(value, active, email);
    pendingCaret.current = next.caret;
    setCaret(next.caret);
    highlight(-1);
    onTypingChange?.('');
    onChange(next.value);
  };

  const onKeyDown = (event: React.KeyboardEvent<HTMLInputElement>) => {
    const count = offered.length;
    if (event.key === 'ArrowDown' || event.key === 'ArrowUp') {
      if (count === 0) return;
      event.preventDefault();
      setOpen(true);
      const step = event.key === 'ArrowDown' ? 1 : -1;
      highlight(highlighted < 0 && step < 0 ? count - 1 : (highlighted + step + count) % count);
      return;
    }
    if (event.key === 'Enter' && highlighted >= 0) {
      event.preventDefault();
      pick(offered[highlighted].email);
      return;
    }
    if (event.key === 'Escape' && expanded) {
      event.preventDefault();
      setOpen(false);
      return;
    }
    if (event.key === 'Tab') setOpen(false);
  };

  return (
    <div className="relative">
      <Input
        ref={inputRef}
        label={label}
        placeholder={placeholder}
        value={value}
        error={error}
        role="combobox"
        aria-expanded={expanded}
        aria-controls={listboxId}
        aria-autocomplete="list"
        aria-activedescendant={highlighted >= 0 ? optionId(highlighted) : undefined}
        inputMode="email"
        autoComplete="off"
        autoCapitalize="none"
        spellCheck={false}
        onChange={event => {
          const at = event.target.selectionStart ?? event.target.value.length;
          setCaret(at);
          setOpen(true);
          onTypingChange?.(activeRecipient(event.target.value, at).query);
          onChange(event.target.value);
        }}
        onSelect={event => {
          // The caret moved (click, arrows): the recipient being typed is
          // the one it now sits in.
          const field = event.currentTarget;
          const at = field.selectionStart ?? field.value.length;
          setCaret(at);
          onTypingChange?.(activeRecipient(field.value, at).query);
        }}
        onFocus={() => {
          setOpen(true);
          onTypingChange?.(active.query);
        }}
        onBlur={() => {
          setOpen(false);
          onTypingChange?.(null);
        }}
        onKeyDown={onKeyDown}
      />
      {expanded && (
        <div className="absolute z-10 mt-1 w-full overflow-hidden rounded-md border border-border bg-popover shadow-lg">
          <ul
            id={listboxId}
            role="listbox"
            aria-label={t('email_share.suggestions_label')}
            className="max-h-60 overflow-auto py-1"
          >
            {offered.map((item, index) => (
              <li
                key={item.email}
                id={optionId(index)}
                role="option"
                aria-selected={index === highlighted}
                // mousedown, not click: the pick happens before the field
                // would blur, and the prevented default keeps the focus.
                onMouseDown={event => {
                  event.preventDefault();
                  pick(item.email);
                }}
                onMouseEnter={() => highlight(index)}
                className={cn(
                  'flex min-h-11 cursor-pointer flex-col justify-center px-3 py-1.5',
                  index === highlighted ? 'bg-muted' : 'hover:bg-muted'
                )}
              >
                <span className="truncate text-sm text-foreground">{item.name}</span>
                <span className="truncate text-xs text-muted-foreground">{item.email}</span>
              </li>
            ))}
          </ul>
          {truncated && (
            <p className="border-t border-border px-3 py-1.5 text-xs text-muted-foreground">
              {t('email_share.suggestions_truncated')}
            </p>
          )}
        </div>
      )}
      <p role="status" className="sr-only">
        {expanded ? t('email_share.suggestions_count', { count: offered.length }) : ''}
      </p>
    </div>
  );
}
