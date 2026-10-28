'use client';
import { useEffect, useEffectEvent, useRef, useState, type RefObject } from 'react';
import { Hand } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { WorldWidgetButton } from './WorldWidgetButton';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { EMOTES, EMOTE_SYMBOLS, type EmoteKind } from './emote-catalogue';

/**
 * Paused gestures stay focusable: `aria-disabled` plus the handler guards refuse them,
 * because a native `disabled` would drop a focused control's focus to <body>.
 */
export function WorldEmoteControls({
  lng,
  canvasRef,
  disabled,
  presentation = 'menu',
  onSelect,
  onReturnFocus,
}: {
  lng: Language;
  canvasRef: RefObject<HTMLCanvasElement | null>;
  disabled: boolean;
  presentation?: 'menu' | 'direct';
  onSelect(kind: EmoteKind): void;
  onReturnFocus(): void;
}) {
  const { t } = useTranslation(lng);
  const selected = useRef(false);
  const [menuOpen, setMenuOpen] = useState(false);
  // A pause closes the menu for good: it must not reappear when the pause ends.
  if (disabled && menuOpen) setMenuOpen(false);
  const shortcut = useEffectEvent((event: KeyboardEvent) => {
    if (
      disabled ||
      document.hidden ||
      event.repeat ||
      event.altKey ||
      event.ctrlKey ||
      event.metaKey ||
      document.activeElement !== canvasRef.current
    )
      return;
    const index = /^Digit[1-6]$/.test(event.code) ? Number(event.code.slice(-1)) - 1 : -1;
    const kind = EMOTES[index];
    if (!kind) return;
    event.preventDefault();
    onSelect(kind);
  });
  useEffect(() => {
    document.addEventListener('keydown', shortcut);
    return () => document.removeEventListener('keydown', shortcut);
  }, []);
  if (presentation === 'direct')
    return (
      <div className="world-emote-buttons" role="group" aria-label={t('world.emotes.title')}>
        {EMOTES.map((kind, index) => (
          <Button
            key={kind}
            type="button"
            variant="ghost"
            size="icon"
            className="world-touch-button text-xl aria-disabled:opacity-50"
            aria-disabled={disabled}
            aria-label={t('world.emotes.' + kind)}
            aria-keyshortcuts={String(index + 1)}
            title={t('world.emotes.' + kind)}
            onClick={() => {
              if (disabled || document.hidden) return;
              onSelect(kind);
              onReturnFocus();
            }}
          >
            <span aria-hidden="true">{EMOTE_SYMBOLS[kind]}</span>
          </Button>
        ))}
      </div>
    );
  return (
    <DropdownMenu open={menuOpen} onOpenChange={open => setMenuOpen(open && !disabled)}>
      <DropdownMenuTrigger asChild>
        <WorldWidgetButton
          icon={Hand}
          label={t('world.emotes.title')}
          aria-disabled={disabled}
          aria-label={t('world.emotes.title')}
        />
      </DropdownMenuTrigger>
      <DropdownMenuContent
        align="start"
        onCloseAutoFocus={event => {
          if (!selected.current) return;
          selected.current = false;
          event.preventDefault();
          onReturnFocus();
        }}
      >
        {EMOTES.map((kind, index) => (
          <DropdownMenuItem
            key={kind}
            className="min-h-11 gap-2"
            aria-keyshortcuts={String(index + 1)}
            onSelect={() => {
              if (disabled || document.hidden) return;
              selected.current = true;
              onSelect(kind);
            }}
          >
            <span aria-hidden="true">{EMOTE_SYMBOLS[kind]}</span>
            {t('world.emotes.' + kind)}
            <kbd className="ml-auto pl-4 text-xs text-muted-foreground">{index + 1}</kbd>
          </DropdownMenuItem>
        ))}
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
