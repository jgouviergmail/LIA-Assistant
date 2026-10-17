'use client';

import { Square, Volume2 } from 'lucide-react';

import { Button } from '@/components/ui/button';
import type { TtsVoiceSamplePlayback } from '@/hooks/useTtsVoiceSample';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';

/** One compact listening control for all the voice pickers of a settings block. */
export function VoiceSamplePlayback({
  lng,
  sample,
}: {
  lng: Language;
  sample: TtsVoiceSamplePlayback;
}) {
  const { t } = useTranslation(lng);
  const active = sample.status === 'loading' || sample.status === 'playing';
  const failed = sample.status === 'error';
  const message =
    sample.status === 'idle'
      ? t('settings.voice_sample.hint')
      : t(`settings.voice_sample.${failed ? 'failed' : sample.status}`);
  return (
    <div className="space-y-1.5">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-2">
        {sample.canReplay && (
          <Button
            type="button"
            variant="outline"
            size="sm"
            className="h-auto min-h-9 whitespace-normal text-left"
            onClick={() => (active ? sample.stop() : void sample.replay())}
          >
            {active ? (
              <Square className="size-3.5 shrink-0" aria-hidden="true" />
            ) : (
              <Volume2 className="size-4 shrink-0" aria-hidden="true" />
            )}
            {t(`settings.voice_sample.${active ? 'stop' : 'listen'}`)}
          </Button>
        )}
        <p
          role={failed ? 'alert' : 'status'}
          aria-live={failed ? 'assertive' : 'polite'}
          className={`min-w-0 flex-1 text-xs ${failed ? 'text-destructive' : 'text-muted-foreground'}`}
        >
          {message}
        </p>
      </div>
      {sample.radioPaused && (
        <p className="text-xs text-muted-foreground">{t('settings.voice_sample.radio_paused')}</p>
      )}
    </div>
  );
}
