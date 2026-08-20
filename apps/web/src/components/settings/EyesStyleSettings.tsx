'use client';

/**
 * EyesStyleSettings — pick the look of the expressive-eyes chat widget.
 *
 * Options come straight from the eye-style registry (`eye-styles.ts`): adding
 * a style there (plus its CSS sheet and locale entries — completeness is
 * test-enforced) makes it appear here with zero changes to this component.
 * Each card shows two LIVE previews (neutral breathes, joy bounces — the
 * real widget CSS animates them), so the choice is made on the actual
 * rendering, not a description. The preference is a device display setting
 * (localStorage via eyesWidgetStore), like the widget's size and position.
 */

import { useSyncExternalStore } from 'react';
import { Check, Eye } from 'lucide-react';

import { ExpressiveEyes } from '@/components/eyes/ExpressiveEyes';
import { EYE_STYLE_IDS, type EyeStyleId } from '@/components/eyes/eye-styles';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { useEyesWidgetStore } from '@/stores/eyesWidgetStore';

interface EyesStyleSettingsProps {
  lng: Language;
}

/** Inert subscription for the hydration gate (no setState-in-effect). */
const hydrationSubscribe = () => () => {};

export function EyesStyleSettings({ lng }: EyesStyleSettingsProps) {
  const { t } = useTranslation(lng);
  const style = useEyesWidgetStore(s => s.style);
  const setStyle = useEyesWidgetStore(s => s.setStyle);
  // The persisted store hydrates client-side only — render the cards after
  // mount so the selected ring never flashes from default to stored value.
  const mounted = useSyncExternalStore(
    hydrationSubscribe,
    () => true,
    () => false
  );

  const content = !mounted ? (
    <div className="text-sm text-muted-foreground">{t('common.loading')}</div>
  ) : (
    <div className="grid gap-3 sm:grid-cols-2">
      {EYE_STYLE_IDS.map(id => {
        const isSelected = style === id;
        return (
          <button
            key={id}
            type="button"
            onClick={() => setStyle(id as EyeStyleId)}
            aria-label={t(`eyes.styles.${id}.name`)}
            className={`
              relative flex items-center gap-3 rounded-lg border-2 p-4 text-left transition-all
              hover:bg-accent hover:shadow-sm
              ${isSelected ? 'border-primary bg-primary/5 shadow-sm' : 'border-border bg-card'}
            `}
          >
            {/* Selection indicator (FontSettings pattern). */}
            <div
              className={`
                flex h-5 w-5 shrink-0 items-center justify-center rounded-full border-2 transition-colors
                ${
                  isSelected
                    ? 'border-primary bg-primary text-primary-foreground'
                    : 'border-muted-foreground/30'
                }
              `}
            >
              {isSelected && <Check className="h-3 w-3" strokeWidth={3} />}
            </div>

            {/* Live previews: the widget's own CSS animates them. */}
            <div className="flex shrink-0 flex-col items-center gap-1" aria-hidden="true">
              <ExpressiveEyes styleId={id} expression="neutral" gaze={null} size="sm" />
              <ExpressiveEyes styleId={id} expression="joy" gaze={null} size="sm" />
            </div>

            <div className="min-w-0 flex-1 space-y-1">
              <p
                className={`text-sm font-medium ${isSelected ? 'text-primary' : 'text-foreground'}`}
              >
                {t(`eyes.styles.${id}.name`)}
              </p>
              <p className="text-xs text-muted-foreground">{t(`eyes.styles.${id}.description`)}</p>
            </div>
          </button>
        );
      })}
    </div>
  );

  return (
    <SettingsSection
      value="eyes-style"
      title={t('settings.eyes_style.title')}
      description={t('settings.eyes_style.description')}
      icon={Eye}
    >
      {content}
    </SettingsSection>
  );
}
