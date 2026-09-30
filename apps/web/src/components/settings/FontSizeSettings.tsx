'use client';

import { useCallback, useMemo, useState } from 'react';
import { AArrowDown, AArrowUp, ALargeSmall, Eye, RotateCcw } from 'lucide-react';
import { toast } from 'sonner';

import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { InfoBox } from '@/components/ui/info-box';
import { Slider } from '@/components/ui/slider';
import { SettingsSection } from '@/components/settings/SettingsSection';
import {
  DEFAULT_FONT_SIZE_PX,
  FONT_SIZE_MAX_PX,
  FONT_SIZE_MIN_PX,
  isValidFontSize,
} from '@/constants/fonts';
import { useAuth } from '@/hooks/useAuth';
import { useFontSizeSave } from '@/hooks/useFontSizeSave';
import { useTranslation } from '@/i18n/client';
import { type Language } from '@/i18n/settings';
import { useFontFamily } from '@/lib/font-context';

interface FontSizeSettingsProps {
  lng: Language;
}

/** The size the thumb is on while dragging, and the applied size it left from. */
interface Draft {
  px: number;
  base: number;
}

/**
 * Settings › Personalization › Font size.
 *
 * Only the TEXT changes size (every font size times `--lia-text-scale`); panels,
 * spacing and icons keep their dimensions. The page applies a size on COMMIT
 * (release of the slider, a key, A−/A+, the reset), never while the thumb is
 * dragged: every line of the page would re-wrap under the finger at each step.
 * While dragging, only the preview follows.
 */
export function FontSizeSettings({ lng }: FontSizeSettingsProps) {
  const { t } = useTranslation(lng);
  const { user } = useAuth();
  const { fontSize, setFontSize } = useFontFamily();
  const [draft, setDraft] = useState<Draft | null>(null);
  // A draft only speaks for the size it left from: Radix commits a key step
  // BEFORE it reports the change, so a draft can outlive its commit.
  const shown = draft !== null && draft.base === fontSize ? draft.px : fontSize;
  const accountFontSize = user?.font_size;
  const accountSize = isValidFontSize(accountFontSize) ? accountFontSize : DEFAULT_FONT_SIZE_PX;

  const onSaveFailure = useCallback(() => {
    // The account kept its size: the page goes back to it rather than showing
    // a choice the next sign-in would silently undo.
    setFontSize(accountSize);
    toast.error(t('settings.font_size.save_error'));
  }, [accountSize, setFontSize, t]);
  const save = useFontSizeSave(onSaveFailure);

  const percentFormat = useMemo(
    () => new Intl.NumberFormat(lng, { style: 'percent', maximumFractionDigits: 0 }),
    [lng]
  );

  const valueLabel = t('settings.font_size.value', {
    px: shown,
    percent: percentFormat.format(shown / DEFAULT_FONT_SIZE_PX),
  });
  const isDefault = shown === DEFAULT_FONT_SIZE_PX;
  const atMin = shown <= FONT_SIZE_MIN_PX;
  const atMax = shown >= FONT_SIZE_MAX_PX;

  const apply = (px: number) => {
    setDraft(null);
    if (px === fontSize || !isValidFontSize(px)) return;
    setFontSize(px);
    void save(px);
  };
  const stepDown = () => {
    if (!atMin) apply(shown - 1);
  };
  const stepUp = () => {
    if (!atMax) apply(shown + 1);
  };

  return (
    <SettingsSection
      value="font-size"
      title={t('settings.font_size.title')}
      description={t('settings.font_size.description')}
      icon={ALargeSmall}
    >
      <div className="space-y-4">
        <div className="space-y-3">
          <p className="flex items-center gap-2 text-sm font-medium text-foreground">
            <Eye className="h-4 w-4 text-primary" aria-hidden="true" />
            {t('settings.font_size.preview_label')}
          </p>
          {/* Only the TEXT follows the size, in em of the chosen size; the
              bubbles keep the chat's own fixed padding, as the page does. */}
          <div
            data-testid="font-size-preview"
            aria-hidden="true"
            className="space-y-3 overflow-hidden rounded-lg border border-border bg-background/60 p-4"
            style={{ fontSize: `${shown}px` }}
          >
            {/* The person on the LEFT, LIA on the RIGHT — the chat's own layout. */}
            <div className="flex justify-start">
              <p className="max-w-[85%] rounded-xl rounded-tl-none bg-gradient-to-br from-primary/80 to-primary/70 px-4 py-3 text-[0.875em] leading-normal text-primary-foreground shadow-sm">
                {t('settings.font_size.preview_question')}
              </p>
            </div>
            <div className="flex justify-end">
              <div className="max-w-[85%] rounded-xl rounded-tr-none border border-border/20 bg-card/70 px-4 py-3 text-foreground shadow-sm">
                <p className="text-[0.875em] leading-normal">
                  {t('settings.font_size.preview_answer')}
                </p>
                <p className="mt-2 text-[0.75em] leading-normal text-muted-foreground">
                  {t('settings.font_size.preview_caption')}
                </p>
              </div>
            </div>
          </div>
        </div>

        {/* The bounds are aria-disabled and guarded, never `disabled`: a
            focused button that turns disabled drops the keyboard to <body>. */}
        <div className="flex items-center gap-2 sm:gap-3">
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-11 w-11 shrink-0 aria-disabled:cursor-not-allowed aria-disabled:opacity-50"
            aria-label={t('settings.font_size.decrease')}
            aria-disabled={atMin}
            onClick={stepDown}
          >
            <AArrowDown className="h-5 w-5" aria-hidden="true" />
          </Button>
          <Slider
            min={FONT_SIZE_MIN_PX}
            max={FONT_SIZE_MAX_PX}
            step={1}
            value={[shown]}
            onValueChange={([px]) => setDraft({ px, base: fontSize })}
            onValueCommit={([px]) => apply(px)}
            className="flex-1 py-3"
            thumbProps={{
              'aria-label': t('settings.font_size.slider_label'),
              'aria-valuetext': valueLabel,
            }}
          />
          <Button
            type="button"
            variant="ghost"
            size="icon"
            className="h-11 w-11 shrink-0 aria-disabled:cursor-not-allowed aria-disabled:opacity-50"
            aria-label={t('settings.font_size.increase')}
            aria-disabled={atMax}
            onClick={stepUp}
          >
            <AArrowUp className="h-5 w-5" aria-hidden="true" />
          </Button>
        </div>

        <div className="flex min-h-9 flex-wrap items-center justify-between gap-2">
          <div className="flex items-center gap-2">
            <span className="text-sm font-medium tabular-nums text-foreground">{valueLabel}</span>
            {isDefault && <Badge>{t('settings.font_size.default_badge')}</Badge>}
          </div>
          {!isDefault && (
            <Button
              type="button"
              variant="ghost"
              size="sm"
              onClick={() => apply(DEFAULT_FONT_SIZE_PX)}
            >
              <RotateCcw className="mr-1.5 h-3.5 w-3.5" aria-hidden="true" />
              {t('settings.font_size.reset')}
            </Button>
          )}
        </div>

        <InfoBox>
          <p className="text-xs text-muted-foreground">{t('settings.font_size.info_note')}</p>
        </InfoBox>
      </div>
    </SettingsSection>
  );
}
