'use client';

/**
 * EyesStyleSettings — pick the look of the expressive-eyes chat widget.
 *
 * Options come straight from the eye-style registry (`eye-styles.ts`): adding
 * a style there with its renderer and locale entries makes it appear here.
 * Monitor cards show neutral and joyful faces; companions show both identities.
 * Prerendered previews wake only on hover or focus. The preference is a
 * device display setting
 * (localStorage via eyesWidgetStore), like the widget's size and position.
 */

import { useState, useSyncExternalStore } from 'react';
import { Check, Eye } from 'lucide-react';

import { EyesFace } from '@/components/eyes/EyesFace';
import { EYE_STYLE_IDS, isRigEyeStyle, type EyeStyleId } from '@/components/eyes/eye-styles';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { useEyesWidgetStore } from '@/stores/eyesWidgetStore';

interface EyesStyleSettingsProps {
  lng: Language;
}

/** Inert subscription for the hydration gate (no setState-in-effect). */
const hydrationSubscribe = () => () => {};

function StylePreviews({
  id,
  animate,
  femaleLabel,
  maleLabel,
}: {
  id: EyeStyleId;
  animate: boolean;
  femaleLabel: string;
  maleLabel: string;
}) {
  const hasGenderVariants = id === 'smiley' || !isRigEyeStyle(id);
  return (
    <div className="flex min-h-20 items-center justify-center gap-3" aria-hidden="true">
      {(['female', 'male'] as const).map((variant, index) => (
        <div key={variant} className="flex w-14 flex-col items-center gap-1">
          <EyesFace
            styleId={id}
            expression={hasGenderVariants || index === 0 ? 'neutral' : 'joy'}
            gaze={null}
            size="sm"
            life={false}
            animate={animate}
            variant={variant}
          />
          {hasGenderVariants && (
            <span className="text-px-10 leading-tight text-muted-foreground">
              {variant === 'female' ? femaleLabel : maleLabel}
            </span>
          )}
        </div>
      ))}
    </div>
  );
}

export function EyesStyleSettings({ lng }: EyesStyleSettingsProps) {
  const { t } = useTranslation(lng);
  const style = useEyesWidgetStore(s => s.style);
  const setStyle = useEyesWidgetStore(s => s.setStyle);
  const [hoveredStyle, setHoveredStyle] = useState<EyeStyleId | null>(null);
  const [focusedStyle, setFocusedStyle] = useState<EyeStyleId | null>(null);
  const previewStyle = hoveredStyle ?? focusedStyle;
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
            onClick={() => {
              if (!isSelected) setStyle(id);
            }}
            onMouseEnter={() => setHoveredStyle(id)}
            onMouseLeave={() => setHoveredStyle(null)}
            onFocus={() => setFocusedStyle(id)}
            onBlur={() => setFocusedStyle(null)}
            aria-label={t(`eyes.styles.${id}.name`)}
            aria-current={isSelected ? 'true' : undefined}
            className={`
              relative flex flex-col gap-3 rounded-lg border-2 p-4 text-left transition-all
              hover:bg-accent hover:shadow-sm
              ${isSelected ? 'border-primary bg-primary/5 shadow-sm' : 'border-border bg-card'}
            `}
          >
            <div className="flex items-start gap-3">
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

              <div className="min-w-0 flex-1 space-y-1">
                <p
                  className={`text-sm font-medium ${isSelected ? 'text-primary' : 'text-foreground'}`}
                >
                  {t(`eyes.styles.${id}.name`)}
                </p>
                <p className="text-xs text-muted-foreground">
                  {t(`eyes.styles.${id}.description`)}
                </p>
              </div>
            </div>
            <StylePreviews
              id={id}
              animate={previewStyle === id}
              femaleLabel={t('eyes.variants.female')}
              maleLabel={t('eyes.variants.male')}
            />
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
