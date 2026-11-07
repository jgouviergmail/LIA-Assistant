'use client';

/**
 * ShortcutsHelp — what a tool's keys do, and the switch that silences them
 * (ADR-369, lot 2; WCAG 2.1.4).
 *
 * « ? » opens it while the shortcuts are on; its button stays for when they are
 * off, and for anyone who never learnt the key. Below `lg` there is no keyboard
 * to speak of, so the button is not drawn.
 */
import { Keyboard } from 'lucide-react';
import { useId, useMemo, useState } from 'react';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { Label } from '@/components/ui/label';
import { Switch } from '@/components/ui/switch';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
import { WORKBENCH_HEADER_ICON } from '@/lib/workbench/tools';

import {
  useShortcutsEnabled,
  useToolShortcuts,
  writeShortcutsEnabled,
  type ToolShortcut,
} from './useToolShortcuts';
import { ToolDialogHeader } from './ToolForm';

export interface ShortcutsHelpProps {
  lng: Language;
  shortcuts: readonly ToolShortcut[];
}

export function ShortcutsHelp({ lng, shortcuts }: ShortcutsHelpProps) {
  const { t } = useTranslation(lng);
  const [open, setOpen] = useState(false);
  const enabled = useShortcutsEnabled();
  const switchId = useId();
  const keys = useMemo(
    () => [
      ...shortcuts,
      { key: '?', labelKey: 'workbench.shortcuts.help', run: () => setOpen(true) },
    ],
    [shortcuts]
  );
  useToolShortcuts(keys);
  return (
    <>
      <Button
        variant="outline"
        size="icon"
        className={cn(WORKBENCH_HEADER_ICON, 'hidden lg:inline-flex')}
        aria-label={t('workbench.shortcuts.title')}
        onClick={() => setOpen(true)}
      >
        <Keyboard className="h-4 w-4" aria-hidden="true" />
      </Button>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent>
          <ToolDialogHeader>
            <DialogTitle>{t('workbench.shortcuts.title')}</DialogTitle>
            <DialogDescription>{t('workbench.shortcuts.description')}</DialogDescription>
          </ToolDialogHeader>
          <dl className="grid grid-cols-[auto_1fr] items-center gap-x-4 gap-y-2 text-sm">
            {keys.map(item => (
              <div key={item.key} className="contents">
                <dt>
                  <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-xs">
                    {item.key}
                  </kbd>
                </dt>
                <dd>{t(item.labelKey)}</dd>
              </div>
            ))}
          </dl>
          <div className="flex items-center gap-3 border-t pt-3">
            <Switch
              id={switchId}
              aria-labelledby={`${switchId}-label`}
              checked={enabled}
              onCheckedChange={writeShortcutsEnabled}
            />
            <Label id={`${switchId}-label`} htmlFor={switchId}>
              {t('workbench.shortcuts.enabled')}
            </Label>
          </div>
        </DialogContent>
      </Dialog>
    </>
  );
}
