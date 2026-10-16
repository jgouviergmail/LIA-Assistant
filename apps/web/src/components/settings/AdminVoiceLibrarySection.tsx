'use client';

/**
 * The instance's Fish Audio voice library (ADR-345), for administrators.
 *
 * The account's own voices — rename them, delete them (never while a slot
 * speaks with one) — and two ways to add one: a CLONE from recordings, under
 * the administrator's attestation that the voice is theirs or that its owner
 * consented in writing, and a DESIGN from a description, paid by the instance.
 * The operator can switch creation off; the voices stay manageable.
 */

import Link from 'next/link';
import { MicVocal } from 'lucide-react';

import { SettingsSection } from '@/components/settings/SettingsSection';
import { CloneVoiceForm } from '@/components/settings/voice-library/CloneVoiceForm';
import { DesignVoiceForm } from '@/components/settings/voice-library/DesignVoiceForm';
import { libraryRefusal } from '@/components/settings/voice-library/wording';
import { VoiceLibraryList } from '@/components/settings/voice-library/VoiceLibraryList';
import { InfoBox } from '@/components/ui/info-box';
import { useVoiceLibrary } from '@/hooks/useVoiceLibrary';
import { useTranslation } from '@/i18n/client';
import { getIntlLocale } from '@/i18n/settings';
import { settingsSectionHref } from '@/lib/settings-sections';
import type { BaseSettingsProps } from '@/types/settings';

const PREFIX = 'settings.admin.voiceLibrary';

export default function AdminVoiceLibrarySection({ lng }: BaseSettingsProps) {
  const { t } = useTranslation(lng, 'translation');
  const { library, loading, error, clone, transcribe, design, saveDesign, rename, remove } =
    useVoiceLibrary();
  // A refresh is not a first load: the forms stay mounted while the list re-reads.
  const firstLoad = library === undefined && loading;
  const locale = getIntlLocale(lng);

  return (
    <SettingsSection
      value="admin-voice-library"
      title={t('settings.admin.voiceLibrary.title')}
      description={t('settings.admin.voiceLibrary.description')}
      icon={MicVocal}
    >
      <div className="space-y-6" aria-busy={loading}>
        {firstLoad && (
          <p role="status" className="animate-pulse text-sm text-muted-foreground">
            {t('common.loading')}
          </p>
        )}
        {error && (
          <InfoBox role="alert" variant="error">
            {libraryRefusal(error, t, locale)}
          </InfoBox>
        )}
        {library && !library.configured && (
          <InfoBox>
            <p className="text-sm">{t(`${PREFIX}.notConfigured`)}</p>
            <Link
              href={settingsSectionHref(lng, 'admin-llm-config')}
              className="text-sm font-medium text-primary underline-offset-4 hover:underline"
            >
              {t(`${PREFIX}.notConfiguredLink`)}
            </Link>
          </InfoBox>
        )}
        {library?.configured && (
          <>
            <VoiceLibraryList
              voices={library.voices}
              titleMaxChars={library.bounds.title_max_chars}
              locale={locale}
              t={t}
              onRename={rename}
              onRemove={remove}
            />
            {library.creation_enabled ? (
              <>
                <CloneVoiceForm
                  bounds={library.bounds}
                  locale={locale}
                  prefillAvailable={library.prefill_available}
                  t={t}
                  onClone={clone}
                  onTranscribe={transcribe}
                />
                <DesignVoiceForm
                  locale={locale}
                  bounds={library.bounds}
                  costUsd={library.design_cost_usd}
                  t={t}
                  onDesign={design}
                  onSave={saveDesign}
                />
              </>
            ) : (
              <InfoBox>{t(`${PREFIX}.creationDisabled`)}</InfoBox>
            )}
          </>
        )}
      </div>
    </SettingsSection>
  );
}
