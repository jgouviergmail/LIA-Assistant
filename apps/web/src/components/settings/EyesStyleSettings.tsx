'use client';

/** Registry-driven, device-local appearance choices with interaction-only previews. */
import { useId, useState, useSyncExternalStore } from 'react';
import { Eye, Palette } from 'lucide-react';

import { EyesFace } from '@/components/eyes/EyesFace';
import { EYE_STYLE_IDS, isRigEyeStyle, type EyeStyleId } from '@/components/eyes/eye-styles';
import { SettingsSection } from '@/components/settings/SettingsSection';
import { Badge } from '@/components/ui/badge';
import { Skeleton } from '@/components/ui/skeleton';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { cn } from '@/lib/utils';
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
  large = false,
}: {
  id: EyeStyleId;
  animate: boolean;
  femaleLabel: string;
  maleLabel: string;
  large?: boolean;
}) {
  const hasGenderVariants = id === 'smiley' || !isRigEyeStyle(id);
  return (
    <div
      className={cn('flex min-h-20 items-center justify-center gap-3', large && 'min-h-28 gap-4')}
      aria-hidden="true"
    >
      {(['female', 'male'] as const).map((variant, index) => (
        <div
          key={variant}
          className={cn('flex w-14 flex-col items-center gap-1', large && 'w-16 gap-2')}
        >
          <EyesFace
            styleId={id}
            expression={hasGenderVariants || index === 0 ? 'neutral' : 'joy'}
            gaze={null}
            size={large ? 'md' : 'sm'}
            life={false}
            animate={animate}
            variant={variant}
          />
          {hasGenderVariants && (
            <span className="text-px-10 leading-tight text-foreground">
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
  const catalogueId = useId();
  const [hoveredStyle, setHoveredStyle] = useState<EyeStyleId | null>(null);
  const [focusedStyle, setFocusedStyle] = useState<EyeStyleId | null>(null);
  const previewStyle = hoveredStyle ?? focusedStyle;
  // Keep the server and initial client render neutral until the device preference hydrates.
  const mounted = useSyncExternalStore(
    hydrationSubscribe,
    () => true,
    () => false
  );
  const previewLabels = {
    femaleLabel: t('eyes.variants.female'),
    maleLabel: t('eyes.variants.male'),
  };

  return (
    <SettingsSection
      value="eyes-style"
      title={t('settings.eyes_style.title')}
      description={t('settings.eyes_style.description')}
      icon={Eye}
    >
      {!mounted ? (
        <Skeleton label={t('common.loading')} className="h-64 w-full rounded-xl" />
      ) : (
        <div className="grid min-w-0 items-start gap-x-5 gap-y-3 xl:grid-cols-[minmax(12rem,0.65fr)_minmax(0,1.8fr)]">
          <section
            aria-label={t('settings.eyes_style.current')}
            className="flex min-w-0 flex-col gap-4 rounded-2xl border border-primary/15 bg-primary/5 p-4 xl:col-start-1 xl:row-start-2 xl:p-5"
          >
            <div className="rounded-2xl bg-primary/10 p-2">
              <StylePreviews id={style} animate={false} large {...previewLabels} />
            </div>
            <div className="min-w-0 space-y-3 [overflow-wrap:anywhere]">
              <p className="text-xs font-medium text-primary">{t('settings.eyes_style.current')}</p>
              <h4 className="text-xl font-semibold leading-tight tracking-tight xl:text-2xl">
                {t(`eyes.styles.${style}.name`)}
              </h4>
              <p className="text-sm leading-relaxed text-muted-foreground">
                {t(`eyes.styles.${style}.description`)}
              </p>
              <p className="text-xs leading-relaxed text-muted-foreground">
                {t('settings.eyes_style.selection_hint')}
              </p>
            </div>
          </section>
          <section aria-labelledby={catalogueId} className="contents">
            <div className="flex min-w-0 flex-wrap items-center justify-between gap-2 xl:col-start-2 xl:row-start-1">
              <h4
                id={catalogueId}
                className="flex min-w-0 items-center gap-2 text-base font-semibold"
              >
                <Palette className="size-4 shrink-0 text-primary" aria-hidden="true" />
                {t('settings.eyes_style.catalogue_title')}
              </h4>
              <p className="text-xs tabular-nums text-muted-foreground">
                {t('settings.eyes_style.catalogue_count', { count: EYE_STYLE_IDS.length })}
              </p>
            </div>
            <div className="grid min-w-0 grid-cols-1 gap-2 sm:grid-cols-2 xl:col-start-2 xl:row-start-2">
              {EYE_STYLE_IDS.map(id => {
                const isSelected = style === id;
                const descriptionId = `${catalogueId}-${id}`;
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
                    aria-describedby={descriptionId}
                    aria-current={isSelected ? 'true' : undefined}
                    className={cn(
                      'flex min-w-0 flex-col gap-3 rounded-xl border border-border/60 p-3 text-left transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2 focus-visible:ring-offset-background motion-reduce:transition-none sm:p-4',
                      isSelected ? 'bg-primary/10' : 'bg-card hover:bg-primary/5'
                    )}
                  >
                    <span className="min-w-0 space-y-2 [overflow-wrap:anywhere]">
                      <span className="flex min-w-0 flex-wrap items-center gap-x-2 gap-y-1">
                        <span className="text-sm font-semibold leading-relaxed">
                          {t(`eyes.styles.${id}.name`)}
                        </span>
                        {isSelected && <Badge size="sm">{t('personality.selected')}</Badge>}
                      </span>
                      <span
                        id={descriptionId}
                        className="block text-sm leading-relaxed text-muted-foreground"
                      >
                        {t(`eyes.styles.${id}.description`)}
                      </span>
                    </span>
                    <div className="mt-auto w-full">
                      <StylePreviews id={id} animate={previewStyle === id} {...previewLabels} />
                    </div>
                  </button>
                );
              })}
            </div>
          </section>
        </div>
      )}
    </SettingsSection>
  );
}
