'use client';

import { EyesFace } from '@/components/eyes/EyesFace';
import type { EyeStyleId } from '@/components/eyes/eye-styles';
import type { SpiritExpression, SpiritVariant } from '@/components/spirit/catalogue';
import { useSpiritPlayback } from '@/components/spirit/playback';

interface PortraitProps {
  styleId: EyeStyleId;
  variant: SpiritVariant;
  expression: SpiritExpression;
  animate: boolean;
}

/** One visible live miniature; history keeps the exact native skin as a frozen pose. */
export function SelectedCompanionPortrait({
  styleId,
  variant,
  expression,
  animate,
}: PortraitProps) {
  const { rootRef, playing } = useSpiritPlayback(animate);
  return (
    <span
      ref={rootRef}
      aria-hidden="true"
      data-companion-portrait={styleId}
      data-portrait-variant={variant}
      data-expression={expression}
      className="lia-message-portrait"
    >
      <EyesFace
        styleId={styleId}
        variant={variant}
        expression={expression}
        gaze={null}
        size="sm"
        life={false}
        animate={playing}
        staticPose={!playing}
      />
    </span>
  );
}
