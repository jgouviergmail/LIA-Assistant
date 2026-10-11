'use client';

/** One renderer boundary for the floating companion and its settings previews. */
import { ExpressiveEyes, type ExpressiveEyesProps } from './ExpressiveEyes';
import { DEFAULT_EYE_STYLE, isRigEyeStyle, type EyeStyleId } from './eye-styles';
import { MonitorCompanion } from './MonitorCompanion';
import { SpiritCompanion } from '@/components/spirit/SpiritCompanion';
import type { SpiritVariant } from '@/components/spirit/catalogue';

export type EyesFaceProps = Omit<ExpressiveEyesProps, 'styleId' | 'smileyVariant'> & {
  styleId?: EyeStyleId;
  variant: SpiritVariant;
  /** Hybrid previews stay fixed until the parent explicitly wakes them. */
  animate?: boolean;
};

export function EyesFace({
  styleId = DEFAULT_EYE_STYLE,
  variant,
  animate = true,
  ...props
}: EyesFaceProps) {
  if (!isRigEyeStyle(styleId))
    return <SpiritCompanion {...props} character={styleId} variant={variant} animate={animate} />;
  if (styleId === 'smiley')
    return (
      <ExpressiveEyes
        {...props}
        styleId={styleId}
        smileyVariant={variant}
        motionEnabled={animate}
      />
    );
  return (
    <MonitorCompanion
      {...props}
      styleId={styleId}
      motionEnabled={animate}
      volumeVariant={variant}
    />
  );
}
