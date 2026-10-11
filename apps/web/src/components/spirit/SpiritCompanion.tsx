'use client';

import { ExpressiveEyes, type ExpressiveEyesProps } from '@/components/eyes/ExpressiveEyes';
import { cn } from '@/lib/utils';
import type { CSSProperties } from 'react';
import type { SpiritVariant } from './catalogue';
import { avatarLayoutProfile } from '@/components/eyes/layout-profiles';
import {
  companionBodyAsset,
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
  const faceStyle = COMPANION_FACE_STYLES[character];
  const bodyStyle: CSSProperties & { '--spirit-body-url': string } = {
    '--spirit-body-url': `url('${companionBodyAsset(character, variant)}')`,
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
