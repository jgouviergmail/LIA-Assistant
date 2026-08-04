'use client';

/**
 * PeerVisibilityCard — the "my visibility" zone of the Connexions section
 * (layout program, 2026-08-05): the two consents and the identity they act
 * on, in ONE card. Flat among six separator-cut blocks, the reader had no way
 * to tell settings from data.
 *
 * Owns the copy-feedback state: it is pure UI and travels with the identity
 * row it decorates (extracting this card also keeps the section shell under
 * the complexity cap).
 */

import { useEffect, useState } from 'react';

import { Check, Copy } from 'lucide-react';

import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

export interface PeerVisibilityCardProps {
  lng: Language;
  /** The identity peers search for; null renders the "undiscoverable" note. */
  fullName: string | null;
  discoveryEnabled: boolean;
  emailVisible: boolean;
  mutating: boolean;
  onSetDiscovery: (value: boolean) => void;
  onSetEmailVisible: (value: boolean) => void;
}

export function PeerVisibilityCard({
  lng,
  fullName,
  discoveryEnabled,
  emailVisible,
  mutating,
  onSetDiscovery,
  onSetEmailVisible,
}: PeerVisibilityCardProps) {
  const { t } = useTranslation(lng);
  const [nameCopied, setNameCopied] = useState(false);

  // The check-mark reverts on a timer; the cleanup keeps a fast unmount (tab
  // away, section collapsed) from firing a setState on a dead component.
  useEffect(() => {
    if (!nameCopied) return;
    const timer = setTimeout(() => setNameCopied(false), 2000);
    return () => clearTimeout(timer);
  }, [nameCopied]);

  return (
    // No frame or heading of its own: the section shell folds this card
    // behind a `SettingsDisclosure` whose summary carries both (owner
    // arbitration 2026-08-05 — the Connexions section reads as an index).
    <div className="space-y-4">
      <div className="flex items-center justify-between gap-2">
        <div className="space-y-0.5">
          <Label htmlFor="peers-discovery-enabled" className="text-sm font-medium">
            {t('settings.peers.discovery.toggle_label')}
          </Label>
          <p className="text-xs text-muted-foreground">
            {t('settings.peers.discovery.toggle_hint')}
          </p>
        </div>
        {/* `aria-disabled`, not `disabled`: a control disabled while it is
            focused is blurred by the browser and leaves the tab order, so a
            keyboard user who toggles this switch is thrown back to the top of
            the document. The state is still announced, and the guard below —
            not the attribute — is what actually prevents a double submit. */}
        <Switch
          id="peers-discovery-enabled"
          checked={discoveryEnabled}
          aria-disabled={mutating}
          className={mutating ? 'cursor-not-allowed opacity-50' : undefined}
          onCheckedChange={value => {
            if (mutating) return;
            onSetDiscovery(value);
          }}
        />
      </div>

      {/* Lot 7: users could not SEE their own name — the identity peers
          search for. Shown at the point of need, with one-click copy; empty
          name = undiscoverable, said plainly. */}
      <div className="rounded-md border border-border/40 bg-muted/40 px-3 py-2 text-sm">
        {fullName ? (
          <div className="flex flex-wrap items-center gap-2">
            <span className="text-muted-foreground">{t('settings.peers.my_name.label')}</span>
            <span className="font-medium">{fullName}</span>
            <Button
              type="button"
              variant="ghost"
              size="icon"
              className="h-7 w-7"
              onClick={() => {
                void navigator.clipboard.writeText(fullName);
                setNameCopied(true);
              }}
              aria-label={t('settings.peers.my_name.copy')}
            >
              {nameCopied ? (
                <Check className="h-3.5 w-3.5 text-success" aria-hidden="true" />
              ) : (
                <Copy className="h-3.5 w-3.5 text-muted-foreground" aria-hidden="true" />
              )}
            </Button>
            <span className="w-full text-xs text-muted-foreground">
              {t('settings.peers.my_name.hint')}
            </span>
          </div>
        ) : (
          <p className="text-muted-foreground">{t('settings.peers.my_name.missing')}</p>
        )}
      </div>

      {/* ADR-189: a SECOND, independent consent. Being findable and handing
          your address over are different decisions — and this one only ever
          reaches people you already accepted. Same aria-disabled treatment as
          the switch above: disabling a focused control loses the keyboard. */}
      <div className="flex items-center justify-between gap-2">
        <div className="space-y-0.5">
          <Label htmlFor="peers-email-visible" className="text-sm font-medium">
            {t('settings.peers.email_visibility.toggle_label')}
          </Label>
          <p className="text-xs text-muted-foreground">
            {t('settings.peers.email_visibility.toggle_hint')}
          </p>
        </div>
        <Switch
          id="peers-email-visible"
          checked={emailVisible}
          aria-disabled={mutating}
          className={mutating ? 'cursor-not-allowed opacity-50' : undefined}
          onCheckedChange={value => {
            if (mutating) return;
            onSetEmailVisible(value);
          }}
        />
      </div>
    </div>
  );
}
