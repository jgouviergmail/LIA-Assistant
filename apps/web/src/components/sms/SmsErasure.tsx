'use client';
import { createContext, useContext, useEffect, useRef, useState } from 'react';
import { Trash2 } from 'lucide-react';
import { useTranslation } from 'react-i18next';
import { Button } from '@/components/ui/button';
import { civilDateInstant } from '@/lib/civil-date-instant';
import { cn } from '@/lib/utils';

export type SmsEraseScope =
  | { message_ids: [string] }
  | { sender_id: string }
  | { from_ts: string; to_ts: string };
interface SmsErasureActions {
  busy: boolean;
  request: (scope: SmsEraseScope) => void;
}
const SmsErasureContext = createContext<SmsErasureActions | undefined>(undefined);
export const SmsErasureProvider = SmsErasureContext.Provider;

/** Only personal settings supplies the existing server-scoped mutation flow. */
export function SmsEraseButton({
  kind,
  target,
  scope,
  className,
}: {
  kind: 'message' | 'sender' | 'day';
  target: string;
  scope: () => SmsEraseScope;
  /** Placement within the caller's layout; the control itself stays the same. */
  className?: string;
}) {
  const actions = useContext(SmsErasureContext);
  const { t } = useTranslation();
  const [invalid, setInvalid] = useState(false);
  // Where the focus returns once this button is gone: the button, then the
  // summary of every disclosure around it, nearest first. A grouped erasure
  // (sender, day) closes its dialog while the button still exists, so the
  // dialog hands the focus back to it — and the refresh then removes the group
  // with the button. Only this unmount can still act, and only when the focus
  // fell to the document: a control the person chose in between is kept.
  const returnTargets = useRef<HTMLElement[]>([]);
  useEffect(
    () => () => {
      const targets = returnTargets.current;
      queueMicrotask(() => {
        if (document.activeElement === document.body && !targets[0]?.isConnected)
          targets.find(target => target.isConnected)?.focus();
      });
    },
    []
  );
  if (!actions) return null;
  const label = t(`sms.erase_${kind}`);
  return (
    <span className={cn('inline-flex flex-wrap items-center gap-2', className)}>
      <Button
        type="button"
        variant={kind === 'message' ? 'ghost' : 'outline'}
        size={kind === 'message' ? 'icon' : 'sm'}
        className={
          kind === 'message' ? 'text-destructive hover:text-destructive' : 'gap-2 font-normal'
        }
        aria-label={`${label} · ${target}`}
        title={kind === 'message' ? label : undefined}
        aria-disabled={actions.busy}
        onClick={event => {
          if (actions.busy) return;
          try {
            const selected = scope();
            const targets: HTMLElement[] = [event.currentTarget];
            for (let node = event.currentTarget.parentElement; node; node = node.parentElement) {
              if (node instanceof HTMLDetailsElement) {
                const summary = node.querySelector<HTMLElement>(':scope > summary');
                if (summary) targets.push(summary);
              }
            }
            returnTargets.current = targets;
            setInvalid(false);
            actions.request(selected);
          } catch {
            setInvalid(true);
          }
        }}
      >
        <Trash2 className="h-4 w-4" aria-hidden="true" />
        {kind !== 'message' && label}
      </Button>
      {invalid && (
        <span role="alert" className="text-xs text-destructive">
          {t('common.error')}
        </span>
      )}
    </span>
  );
}

/** Half-open civil day; DST days deliberately need not last 24 hours. */
export function smsDayEraseScope(day: string, timezone: string): SmsEraseScope {
  const next = new Date(`${day}T00:00:00.000Z`);
  next.setUTCDate(next.getUTCDate() + 1);
  return {
    from_ts: civilDateInstant(day, timezone),
    to_ts: civilDateInstant(next.toISOString().slice(0, 10), timezone),
  };
}
