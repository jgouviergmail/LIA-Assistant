import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { JevCallTrace } from '@/types/jev';
import { JevContext } from './JevContext';

const prefix = 'chat.debug_panel.jev.';

function isCompleteEmptyArray(context: JevCallTrace['context']): boolean {
  if (context.omitted_characters !== 0) return false;
  try {
    const value: unknown = JSON.parse(context.text);
    return Array.isArray(value) && value.length === 0;
  } catch {
    return false;
  }
}

/** The generative proposal is a separate observation, never the native Choice. */
export function JevObservedResult({ call, lng }: { call: JevCallTrace; lng: Language }) {
  const { t } = useTranslation(lng);
  if (!call.observed_result) return null;
  return (
    <div className="space-y-2 border-t pt-2">
      <p className="text-muted-foreground">{t(prefix + 'observedResultHelp')}</p>
      {call.usage === 'observe_memory' && (
        <>
          <p className="text-muted-foreground">{t(prefix + 'memoryObservationHelp')}</p>
          {isCompleteEmptyArray(call.observed_result) && (
            <p className="font-semibold">{t(prefix + 'memoryEmptyProposal')}</p>
          )}
        </>
      )}
      <JevContext context={call.observed_result} lng={lng} labelKey="observedResult" />
    </div>
  );
}
