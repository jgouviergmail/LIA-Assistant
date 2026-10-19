import React from 'react';
import { Composition, registerRoot } from 'remotion';
import { FeatureFilm, FEATURE_FILM_FPS, FEATURE_FILM_FRAMES } from './FeatureFilm';

function FeatureRoot() {
  return <Composition id="LIA-Feature-Film" component={FeatureFilm} fps={FEATURE_FILM_FPS}
    width={1920} height={1080} durationInFrames={FEATURE_FILM_FRAMES} defaultProps={{withAudio:true}} />;
}
registerRoot(FeatureRoot);
