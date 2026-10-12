'use client';

/** A fullscreen, exclusive presentation with native media controls and focus return. */
import { Clapperboard, RotateCcw } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';
import { useTranslation } from 'react-i18next';

import { Button } from '@/components/ui/button';
import { Dialog, DialogContent, DialogDescription, DialogTitle } from '@/components/ui/dialog';
import { renditionsFor } from './use-video-playback';
import { useLandingPresentation } from './use-landing-presentation';

export default function PresentationDialog({
  request,
  onClose,
}: {
  request: number;
  onClose: () => void;
}) {
  const { t } = useTranslation();
  const [attempt, setAttempt] = useState(0);
  const [failed, setFailed] = useState(false);
  const state = useLandingPresentation(request + attempt);
  const videoRef = useRef<HTMLVideoElement>(null);

  useEffect(() => {
    const element = videoRef.current;
    return () => element?.pause();
  }, [state.status, attempt]);

  const retry = () => {
    setFailed(false);
    setAttempt(value => value + 1);
  };

  const showError = failed || state.status === 'error';

  return (
    <Dialog open onOpenChange={open => !open && onClose()}>
      <DialogContent
        className="inset-0 left-0 top-0 flex h-dvh max-h-none w-screen max-w-none translate-x-0 translate-y-0 flex-col gap-0 overflow-hidden rounded-none border-0 bg-background p-0"
        data-testid="presentation-dialog"
      >
        <header className="shrink-0 border-b px-5 py-4 pr-16 sm:px-8 sm:pr-20">
          <DialogTitle className="flex items-center gap-2 text-lg">
            <Clapperboard className="size-5 text-primary" aria-hidden="true" />
            {t('landing.presentation.film.title')}
          </DialogTitle>
          <DialogDescription className="mt-2 text-sm">
            {t('landing.presentation.film.description')}
          </DialogDescription>
        </header>
        <div className="flex min-h-0 flex-1 items-center justify-center bg-black">
          {state.status === 'ready' && !failed ? (
            <video
              key={attempt}
              ref={videoRef}
              controls
              autoPlay
              playsInline
              preload="metadata"
              poster={state.video.poster}
              className="h-full w-full object-contain"
              aria-label={t('landing.presentation.film.title')}
              onError={() => setFailed(true)}
            >
              {renditionsFor(state.video.renditions, window.innerWidth).map(rendition => (
                <source key={rendition.src} src={rendition.src} type={rendition.type} />
              ))}
            </video>
          ) : (
            <div className="max-w-lg px-6 text-center text-white" role="status">
              <p className="text-base leading-relaxed">
                {t(
                  showError
                    ? 'landing.presentation.film.error'
                    : state.status === 'unavailable'
                      ? 'landing.presentation.film.unavailable'
                      : 'landing.presentation.film.loading'
                )}
              </p>
              {(showError || state.status === 'unavailable') && (
                <Button variant="outline" className="mt-5 gap-2" onClick={retry}>
                  <RotateCcw className="size-4" aria-hidden="true" />
                  {t('common.retry')}
                </Button>
              )}
            </div>
          )}
        </div>
        {state.status === 'ready' && state.video.aiGenerated && (
          <p className="shrink-0 px-5 py-2 text-center text-xs text-muted-foreground">
            {t('landing.presentation.film.ai_music_note')}
          </p>
        )}
      </DialogContent>
    </Dialog>
  );
}
