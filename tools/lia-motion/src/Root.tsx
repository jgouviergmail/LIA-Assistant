import React from 'react';
import { Composition } from 'remotion';
import { FULL_SCENES, SHORT_SCENES, FOCUS_SCENES } from './content';
import { RealProductFilm, RealProductProof } from './RealProductFilm';
import { ProductStory } from './ProductStory';
import { PresentationFilm, filmFrames } from './PresentationFilm';
import { PRESENTATION_CHAPTERS, PRESENTATION_LANDING_CHAPTERS, PRESENTATION_FOCUS_PLAN } from './presentation-plan';
import { PRODUCT_STORY_FPS, PRODUCT_STORY_FRAMES } from './product-story-timing';
import { buildTimeline } from './timeline';
import music from './music.json';

const filmDuration = (scenes: typeof FULL_SCENES, fps: number) =>
  buildTimeline(scenes, music.beats, fps).reduce((end, item) => end + item.durationInFrames, 0) + fps * 4;

const landingChapters=PRESENTATION_LANDING_CHAPTERS;

export const MotionRoot = () => (
  <>
    <Composition
      id="LIA-Full"
      component={PresentationFilm}
      fps={30}
      width={1920}
      height={1080}
      durationInFrames={filmFrames(PRESENTATION_CHAPTERS,30)}
      defaultProps={{chapters:PRESENTATION_CHAPTERS,withAudio:true}}
    />
    <Composition
      id="LIA-Landing"
      component={PresentationFilm}
      fps={30}
      width={1920}
      height={1080}
      durationInFrames={filmFrames(landingChapters,30)}
      defaultProps={{chapters:landingChapters,withAudio:true}}
    />
    <Composition
      id="LIA-Master25"
      component={PresentationFilm}
      fps={25}
      width={1920}
      height={1080}
      durationInFrames={filmFrames(PRESENTATION_CHAPTERS,25)}
      defaultProps={{chapters:PRESENTATION_CHAPTERS,withAudio:true}}
    />
    {PRESENTATION_FOCUS_PLAN.map(focus=><Composition
      key={focus.id}
      id={`LIA-${focus.id}`}
      component={PresentationFilm}
      fps={30}
      width={1920}
      height={1080}
      durationInFrames={Math.round(focus.durationSeconds*30)}
      defaultProps={{focus,withAudio:true}}
    />)}
    <Composition
      id="LIA-Story24"
      component={ProductStory}
      fps={PRODUCT_STORY_FPS}
      width={1920}
      height={1080}
      durationInFrames={PRODUCT_STORY_FRAMES}
      defaultProps={{ withAudio: true }}
    />
    <Composition
      id="LIA-LegacyFull"
      component={RealProductFilm}
      fps={30}
      width={1920}
      height={1080}
      durationInFrames={filmDuration(FULL_SCENES, 30)}
      defaultProps={{ scenes: FULL_SCENES }}
    />
    <Composition
      id="LIA-LegacyLanding"
      component={RealProductFilm}
      fps={30}
      width={1920}
      height={1080}
      durationInFrames={filmDuration(SHORT_SCENES, 30)}
      defaultProps={{ scenes: SHORT_SCENES }}
    />
    <Composition
      id="LIA-LegacyMaster25"
      component={RealProductFilm}
      fps={25}
      width={1920}
      height={1080}
      durationInFrames={filmDuration(FULL_SCENES, 25)}
      defaultProps={{ scenes: FULL_SCENES }}
    />
    {FOCUS_SCENES.filter(scene => scene.status !== 'planned').map(scene => (
      <Composition
        key={scene.id}
        id={`LIA-Legacy-${scene.id}`}
        component={RealProductFilm}
        fps={30}
        width={1920}
        height={1080}
        durationInFrames={filmDuration([scene], 30)}
        defaultProps={{ scenes: [scene] }}
      />
    ))}
    <Composition
      id="LIA-Proof30"
      component={RealProductProof}
      fps={30}
      width={1920}
      height={1080}
      durationInFrames={900}
      defaultProps={{}}
    />
  </>
);
