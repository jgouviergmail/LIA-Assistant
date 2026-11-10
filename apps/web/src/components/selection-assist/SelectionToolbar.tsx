'use client';
import { useTranslation } from '@/i18n/client';
import {
  X,
  BookOpenText,
  Feather,
  Languages,
  MessageCircleQuestion,
  ListPlus,
  CalendarPlus,
  Brain,
  SpellCheck,
  Scissors,
  Briefcase,
  Smile,
  ListOrdered,
  Globe,
  Volume2,
  FileText,
  Bell,
  Ticket,
  MessageCircle,
  type LucideIcon,
} from '@/lib/icons';
import {
  EDIT_ACTIONS,
  READ_ACTIONS,
  isDestination,
  type SelectionAction,
  type SelectionOffer,
} from '@/lib/selection-assist/contracts';
import type { SelectionTarget } from '@/lib/selection-assist/targets';
import type { Language } from '@/i18n/settings';
import { AssistStars } from './AssistStars';

const ACTION_ICONS: Record<SelectionAction, LucideIcon> = {
  explain: BookOpenText,
  simplify: Feather,
  translate: Languages,
  ask: MessageCircleQuestion,
  task: ListPlus,
  event: CalendarPlus,
  memory: Brain,
  fix: SpellCheck,
  shorter: Scissors,
  formal: Briefcase,
  warm: Smile,
  format: ListOrdered,
  internet: Globe,
  read: Volume2,
  summarize: FileText,
  reminder: Bell,
  ticket: Ticket,
  lia: MessageCircle,
};

export function SelectionToolbar({
  target,
  lng,
  offer,
  creates,
  onAction,
  onClose,
}: {
  target: SelectionTarget;
  lng: Language;
  offer: SelectionOffer;
  creates: boolean;
  onAction: (action: SelectionAction) => void;
  onClose: () => void;
}) {
  const { t } = useTranslation(lng);
  const actions = target.mode === 'read' ? READ_ACTIONS : EDIT_ACTIONS;
  const tooLong = exceedsCharacters(target.text, offer.text_max_chars);
  return (
    <>
      <AssistStars className="mx-1 h-4 w-4 shrink-0" aria-hidden="true" />
      {actions.map(action => {
        const Icon = ACTION_ICONS[action];
        const unavailable =
          tooLong ||
          (isDestination(action) && (!creates || !offer.destinations.includes(action))) ||
          (action === 'internet' && !offer.internet_available) ||
          (action === 'read' && !offer.read_aloud_available);
        return (
          <button
            key={action}
            type="button"
            aria-disabled={unavailable || undefined}
            title={
              unavailable
                ? t(tooLong ? 'selectionAssist.too_long' : 'selectionAssist.unavailable', {
                    count: offer.text_max_chars,
                  })
                : undefined
            }
            onMouseDown={event => event.preventDefault()}
            onClick={() => {
              if (!unavailable) onAction(action);
            }}
            className="inline-flex min-h-9 min-w-0 items-center gap-1.5 rounded-md px-2 py-1.5 text-xs font-medium text-foreground/90 transition-colors hover:bg-muted/70 hover:text-primary focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring aria-disabled:opacity-50"
          >
            <Icon className="h-3.5 w-3.5 shrink-0 text-primary" aria-hidden="true" />
            {t(`selectionAssist.actions.${action}`)}
          </button>
        );
      })}
      <button
        type="button"
        aria-label={t('common.close')}
        onClick={onClose}
        className="flex min-h-9 min-w-9 items-center justify-center rounded-md text-muted-foreground hover:bg-muted/60 focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring"
      >
        <X className="h-4 w-4" aria-hidden="true" />
      </button>
      <p className="sr-only">{t('selectionAssist.keyboard_hint')}</p>
      {tooLong && (
        <p role="status" className="w-full px-2 text-sm">
          {t('selectionAssist.too_long', { count: offer.text_max_chars })}
        </p>
      )}
    </>
  );
}

/** Count code points without allocating a copy of an arbitrarily large selection. */
function exceedsCharacters(text: string, limit: number): boolean {
  let count = 0;
  for (const _character of text) if (++count > limit) return true;
  return false;
}
