'use client';
import { Headphones, HeadphoneOff } from 'lucide-react';
import { Button } from '@/components/ui/button';
import { Slider } from '@/components/ui/slider';
import {
  Dialog,
  DialogTrigger,
  DialogContent,
  DialogTitle,
  DialogDescription,
  DialogHeader,
} from '@/components/ui/dialog';
import { useTranslation } from '@/i18n/client';
import type { Language } from '@/i18n/settings';
import type { WorldSoundControl } from './useWorldSound';
export function WorldSoundWidget({ lng, sound }: { lng: Language; sound: WorldSoundControl }) {
  const { t } = useTranslation(lng);
  const label = t(sound.enabled ? 'world.sound.disable' : 'world.sound.enable');
  const percent = Math.round(sound.volume * 100);
  return (
    <Dialog modal={false}>
      <DialogTrigger asChild>
        <Button
          size="icon"
          variant="ghost"
          className="min-h-11 min-w-11"
          aria-label={t('world.sound.settings')}
          title={t('world.sound.settings')}
        >
          <span className="world-device-icon">
            {sound.enabled && percent > 0 ? (
              <Headphones aria-hidden="true" />
            ) : (
              <HeadphoneOff aria-hidden="true" />
            )}
          </span>
          <span className="world-device-label">{t('world.sound.short')}</span>
        </Button>
      </DialogTrigger>
      <DialogContent className="max-w-xs gap-3 p-4" data-world-sound-panel>
        <DialogHeader className="pr-6 text-left">
          <DialogTitle className="flex items-center gap-2 text-base">
            <Headphones className="size-4" aria-hidden="true" />
            {t('world.sound.settings')}
          </DialogTitle>
          <DialogDescription className="text-xs leading-relaxed">
            {t('world.sound.independent')}
          </DialogDescription>
        </DialogHeader>
        <Button
          variant="outline"
          className="min-h-11 w-full"
          aria-pressed={sound.enabled}
          onClick={sound.toggle}
        >
          {label}
        </Button>
        <div className="flex items-center justify-between gap-3 text-sm">
          <span>{t('world.sound.volume')}</span>
          <output className="tabular-nums">{percent} %</output>
        </div>
        <Slider
          className="min-h-11"
          min={0}
          max={100}
          step={1}
          value={[percent]}
          aria-label={t('world.sound.volume')}
          thumbProps={{ 'aria-valuetext': percent + ' %' }}
          onValueChange={values => sound.setVolume((values[0] ?? percent) / 100)}
        />
        {sound.failed && (
          <p className="text-xs text-muted-foreground" role="status">
            {t('world.sound.unavailable')}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
