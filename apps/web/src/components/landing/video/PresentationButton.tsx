'use client';

/** Explicit entry to the complete film; the heavy modal loads only on request. */
import dynamic from 'next/dynamic';
import { Clapperboard } from 'lucide-react';
import { useEffect, useRef, useState } from 'react';

import { Button } from '@/components/ui/button';
import { useLandingVideoRegistry } from './landing-video-context';

const PresentationDialog = dynamic(() => import('./PresentationDialog'), { ssr: false });

export function PresentationButton({ label }: { label: string }) {
  const [request, setRequest] = useState<number | null>(null);
  const sequence = useRef(0);
  const setExclusivePlayback = useLandingVideoRegistry()?.setExclusivePlayback;

  useEffect(() => () => setExclusivePlayback?.(false), [setExclusivePlayback]);

  const close = () => {
    setRequest(null);
    setExclusivePlayback?.(false);
  };

  return (
    <>
      <Button
        type="button"
        size="lg"
        className="gap-2 bg-blue-600 px-5 text-base text-white hover:bg-blue-700"
        aria-haspopup="dialog"
        data-testid="hero-cta-presentation"
        onClick={() => {
          setExclusivePlayback?.(true);
          setRequest(++sequence.current);
        }}
      >
        <Clapperboard className="size-5" aria-hidden="true" />
        {label}
      </Button>
      {request !== null && <PresentationDialog request={request} onClose={close} />}
    </>
  );
}
