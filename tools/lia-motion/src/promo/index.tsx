import React from 'react';
import { Composition, registerRoot } from 'remotion';
import { PromoFilm } from './PromoFilm';
import { FPS, HEIGHT, TOTAL_FRAMES, WIDTH } from './timing';

function PromoRoot() {
  return (
    <Composition
      id="LIA-Promo"
      component={PromoFilm}
      fps={FPS}
      width={WIDTH}
      height={HEIGHT}
      durationInFrames={TOTAL_FRAMES}
      defaultProps={{ withAudio: true }}
    />
  );
}
registerRoot(PromoRoot);
