import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { JevCallTrace } from '@/types/jev';

function fields(text: string): [string, unknown][] | null {
  try {
    const value: unknown = JSON.parse(text);
    return value !== null && typeof value === 'object' && !Array.isArray(value)
      ? Object.entries(value)
      : null;
  } catch {
    return null;
  }
}

function readable(value: unknown): string {
  return typeof value === 'string' ? value : JSON.stringify(value, null, 2);
}

/** Render source data as text only. A truncated JSON envelope stays inspectable. */
export function JevContext({
  context,
  lng,
  labelKey = 'context',
}: {
  context: JevCallTrace['context'];
  lng: Language;
  labelKey?: 'context' | 'observedResult';
}) {
  const { t } = useTranslation(lng);
  const parts = context.omitted_characters === 0 ? fields(context.text) : null;
  return (
    <details>
      <summary className="cursor-pointer py-1 font-semibold focus-visible:outline focus-visible:outline-ring">
        {t('chat.debug_panel.jev.' + labelKey)}
      </summary>
      <div
        role="region"
        aria-label={t('chat.debug_panel.jev.' + labelKey)}
        tabIndex={0}
        className="mt-2 max-h-64 space-y-3 overflow-y-auto rounded bg-muted p-2 focus-visible:outline focus-visible:outline-ring"
      >
        {parts ? (
          parts.map(([key, value]) => (
            <section key={key} className="space-y-1">
              <h4 className="font-semibold">
                {t(`chat.debug_panel.jev.${key}`, { defaultValue: key })}
              </h4>
              {value !== null && typeof value === 'object' && !Array.isArray(value) ? (
                Object.entries(value).map(([name, item]) => (
                  <div key={name} className="border-t pt-1">
                    <p className="font-mono text-muted-foreground">{name}</p>
                    <pre className="whitespace-pre-wrap font-sans">{readable(item)}</pre>
                  </div>
                ))
              ) : (
                <pre className="whitespace-pre-wrap font-sans">{readable(value)}</pre>
              )}
            </section>
          ))
        ) : (
          <pre className="whitespace-pre-wrap font-mono">{context.text}</pre>
        )}
      </div>
      {context.omitted_characters > 0 && (
        <div className="space-y-1 text-muted-foreground">
          <p>
            {t('chat.debug_panel.jev.truncated', {
              omitted: context.omitted_characters,
              total: context.original_characters,
            })}
          </p>
          {labelKey === 'context' && <p>{t('chat.debug_panel.jev.contextDisplayHelp')}</p>}
        </div>
      )}
    </details>
  );
}
