'use client';

import { ExpressiveEyes, type ExpressiveEyesProps } from '@/components/eyes/ExpressiveEyes';
import { cn } from '@/lib/utils';
import { useId, type CSSProperties } from 'react';
import type { SpiritVariant } from './catalogue';
import { avatarLayoutProfile } from '@/components/eyes/layout-profiles';
import { sourceAlphaTransfer } from '@/components/eyes/volume/source-alpha';
import {
  companionBodyAsset,
  COMPANION_BODY_ALPHA_FLOOR,
  COMPANION_FACE_STYLES,
  type CompanionCharacter,
} from './companion-catalogue';

type SpiritCompanionProps = Omit<ExpressiveEyesProps, 'styleId'> & {
  variant: SpiritVariant;
  animate: boolean;
  character?: CompanionCharacter;
};

/** Original offline 3D body; every facial channel comes from the existing rig. */
export function SpiritCompanion({
  variant,
  animate,
  character = 'spirit',
  className,
  ...props
}: SpiritCompanionProps) {
  const alphaId = `${useId()}-body-alpha`;
  const alpha = sourceAlphaTransfer(COMPANION_BODY_ALPHA_FLOOR);
  const faceStyle = COMPANION_FACE_STYLES[character];
  const bodyStyle: CSSProperties & {
    '--spirit-body-url': string;
    '--spirit-body-alpha-filter': string;
  } = {
    '--spirit-body-url': `url('${companionBodyAsset(character, variant)}')`,
    '--spirit-body-alpha-filter': `url("#${alphaId}")`,
  };
  return (
    <span
      aria-hidden="true"
      data-style={character}
      data-character={character}
      data-renderer="hybrid"
      data-spirit-companion={variant}
      className={cn('lia-spirit-companion', className)}
      style={bodyStyle}
    >
      <svg width="0" height="0" focusable="false" style={{ position: 'absolute' }}>
        <defs>
          <filter id={alphaId} colorInterpolationFilters="sRGB">
            <feComponentTransfer>
              <feFuncA type="linear" slope={alpha.slope} intercept={alpha.intercept} />
            </feComponentTransfer>
          </filter>
        </defs>
      </svg>
      <ExpressiveEyes
        {...props}
        styleId={faceStyle}
        characterId={character}
        volumeCharacter={character}
        volumeVariant={variant}
        layoutProfile={avatarLayoutProfile(character, variant)}
        motionEnabled={animate}
        pupilClip={faceStyle === 'billes'}
        faceMask
        sculptedFace={character !== 'bip'}
        className="lia-spirit-rig"
      />
    </span>
  );
}
