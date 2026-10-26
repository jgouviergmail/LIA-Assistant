'use client';
import { WorldEnvironmentPreview } from './WorldEnvironmentPreview';

/** Inert proof identities exist only in the separate, explicitly enabled dev host. */
import { Button } from '@/components/ui/button';
import { useApiMutation } from '@/hooks/useApiMutation';
import { useApiQuery } from '@/hooks/useApiQuery';
import { useTranslation } from '@/i18n/client';
import { languages, languageNames, type Language } from '@/i18n/settings';
import { buildLocalizedPath } from '@/utils/i18n-path-utils';
import { WorldShared } from './WorldShared';

export function WorldProof({
  lng,
  resume = false,
  translationFixture = false,
}: {
  lng: Language;
  resume?: boolean;
  translationFixture?: boolean;
}) {
  const { t } = useTranslation(lng);
  const identity = useApiQuery<{ owner_id: string; language: string }>('/world-proof/me', {
    enabled: resume,
    componentName: 'WorldProofIdentity',
  });
  const { mutate, loading, error } = useApiMutation<
    { index: number },
    { owner_id: string; language: string }
  >({ method: 'POST', componentName: 'WorldProof', retainResponse: false });
  const resumedLanguage = languages.find(value => value === identity.data?.language);
  const current =
    identity.data && resumedLanguage
      ? { owner: identity.data.owner_id, language: resumedLanguage }
      : null;
  if (current)
    return (
      <div className="world-preview" lang={current.language}>
        {translationFixture && (
          <div
            className="mb-2 shrink-0 rounded-xl border border-border bg-muted text-sm"
            role="note"
          >
            <details>
              <summary className="min-h-11 cursor-pointer px-3 py-3 font-medium">
                {t('world.session.proof_guide')}
                <span className="mt-1 block text-xs font-normal leading-relaxed">
                  {t('world.session.proof_chat_hint')}
                </span>
              </summary>
              <p className="px-3 pb-3 leading-relaxed">
                {t('world.session.proof_translation')} {t('world.session.proof_atmosphere')}
              </p>
              <p className="px-3 pb-3 leading-relaxed">{t('world.session.proof_multiplayer')}</p>
            </details>
          </div>
        )}
        <WorldEnvironmentPreview lng={current.language}>
          <WorldShared key={current.owner} lng={current.language} ownerId={current.owner} />
        </WorldEnvironmentPreview>
      </div>
    );
  return (
    <section className="mx-auto flex min-h-[70dvh] max-w-xl flex-col justify-center gap-6 p-4">
      <h1 className="text-2xl font-semibold">{t('world.title')}</h1>
      <p>{t('world.session.proof')}</p>
      <p className="text-sm leading-relaxed">{t('world.session.proof_multiplayer')}</p>
      <div className="grid grid-cols-2 gap-3">
        {(['fr', 'en', 'de', 'es', 'it', 'zh', 'fr', 'en'] as const).map((language, offset) => (
          <Button
            key={offset}
            className="h-auto min-h-11 whitespace-normal px-3 py-2"
            disabled={loading}
            onClick={async () => {
              try {
                const response = await mutate('/world-proof/session', { index: offset + 1 });
                const language = languages.find(value => value === response?.language);
                if (response && language) {
                  window.location.assign(
                    buildLocalizedPath('/world-preview', language) + '?shared=1&resume=1'
                  );
                }
              } catch {
                /* The mutation hook owns the localized error state. */
              }
            }}
          >
            {t('world.session.proof_account', { index: offset + 1 })}
            {' · ' + languageNames[language].native}
          </Button>
        ))}
      </div>
      {error && <p role="alert">{t('world.session.unavailable')}</p>}
    </section>
  );
}
