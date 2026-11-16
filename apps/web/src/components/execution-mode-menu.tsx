'use client';

/**
 * How LIA works, chosen in the chat header (ADR-070, ADR-390): the pipeline's
 * plan, the ReAct loop, or « auto », where the router picks one of the two for
 * each request.
 *
 * Three choices replaced the two-state toggle, so the control is a menu: the
 * trigger wears the chosen mode's mark (the same mark as the ticket and routine
 * field, and as the badge under an automatic answer) and says its name to a
 * screen reader and on hover; each choice says in one line what it does. The
 * « auto » line says what « auto » does on THIS instance when it cannot decide —
 * always the loop without a decision model, always the plan without the loop —
 * read again each time the menu opens, so a change an administrator made since
 * the page loaded is told before the person chooses.
 *
 * A save keeps the trigger focusable (`isLoading`: busy, guarded, never
 * `disabled`), and only a save that FAILED is said as an error.
 */

import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuRadioGroup,
  DropdownMenuRadioItem,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { useExecutionModePreference } from '@/hooks/useExecutionModePreference';
import { useHydrated } from '@/hooks/useHydrated';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import {
  EXECUTION_MODES,
  type AutoModeResolution,
  type ExecutionMode,
} from '@/lib/execution-mode';
import { modeIcon } from '@/lib/execution-mode-icon';
import { cn } from '@/lib/utils';
import { toast } from 'sonner';

interface ExecutionModeMenuProps {
  lng?: Language;
  /** Added to the trigger's own box (the dashboard header passes its icon slot). */
  className?: string;
}

const BOX = 'w-11 h-11 px-0 max-[380px]:w-9 max-[380px]:h-9';
const GLYPH = 'h-[1.2rem] w-[1.2rem]';

/** The description key of a choice — « auto » says what it does on this instance. */
function descriptionKey(mode: ExecutionMode, resolution: AutoModeResolution | null): string {
  if (mode === 'auto' && resolution !== null && resolution !== 'decided') {
    return `executionMode.descriptions.auto_${resolution}`;
  }
  return `executionMode.descriptions.${mode}`;
}

export function ExecutionModeMenu({ lng = 'fr', className }: ExecutionModeMenuProps) {
  const { t } = useTranslation(lng);
  const mounted = useHydrated();
  const { mode, autoResolution, saving, refresh, choose } = useExecutionModePreference();

  // The server knows no account: a neutral control until the page is live, so
  // nothing announces a mode the person did not choose.
  if (!mounted) {
    return (
      <Button
        variant="ghost"
        size="sm"
        className={cn(BOX, className)}
        aria-label={t('executionMode.menu.title')}
      >
        {modeIcon('pipeline', GLYPH)}
      </Button>
    );
  }

  const label = t('executionMode.menu.trigger', { mode: t(`executionMode.modes.${mode}`) });

  const onChoose = async (value: string) => {
    const next = EXECUTION_MODES.find(candidate => candidate === value);
    if (!next) return;
    const outcome = await choose(next);
    if (outcome === 'saved') {
      toast.success(t('executionMode.menu.saved', { mode: t(`executionMode.modes.${next}`) }));
    } else if (outcome === 'failed') {
      toast.error(t('common.error'));
    }
  };

  return (
    <DropdownMenu
      onOpenChange={open => {
        if (open) void refresh();
      }}
    >
      <DropdownMenuTrigger asChild>
        <Button
          variant="ghost"
          size="sm"
          className={cn(BOX, className)}
          isLoading={saving !== null}
          aria-label={label}
          title={label}
        >
          {modeIcon(mode, GLYPH)}
        </Button>
      </DropdownMenuTrigger>
      <DropdownMenuContent align="end" className="w-72">
        <DropdownMenuRadioGroup value={mode} onValueChange={value => void onChoose(value)}>
          {EXECUTION_MODES.map(option => (
            <DropdownMenuRadioItem key={option} value={option} className="items-start gap-2">
              {modeIcon(option, 'mt-0.5 h-4 w-4 shrink-0 text-primary')}
              <span className="min-w-0 flex-1">
                <span className="block font-medium">{t(`executionMode.modes.${option}`)}</span>
                <span className="block text-xs text-muted-foreground">
                  {t(descriptionKey(option, autoResolution))}
                </span>
              </span>
            </DropdownMenuRadioItem>
          ))}
        </DropdownMenuRadioGroup>
      </DropdownMenuContent>
    </DropdownMenu>
  );
}
