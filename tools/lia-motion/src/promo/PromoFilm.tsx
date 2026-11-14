/**
 * LIA promotional film — « Ton quotidien. LIA garde le fil. »
 *
 * 114 seconds, 1920x1080, 60 fps, French, cut to the measured beat grid of
 * its original soundtrack (see `timing.ts`, including the repeated bars).
 * Six chapters, each a strong scene then an illustrated enumeration: she
 * knows you, she acts, she anticipates, she follows you everywhere, your
 * circle, and the control you keep; then everything links up around LIA and
 * the closing line lands on the final hit. Sections are mounted as
 * overlapping sequences; the cosmos ground and the grain run underneath the
 * whole film so cuts never flash to black.
 */
import React from 'react';
import { AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame } from 'remotion';
import { Cosmos, Vignette } from './parts/Cosmos';
import { Chapter } from './parts/Bento';
import { MUSIC_EDIT, beat, sectionFrom, sectionLength } from './timing';
import { ramp } from './motion';
import { Opening } from './scenes/Opening';
import { Context } from './scenes/Context';
import { Action } from './scenes/Action';
import { Anticipate } from './scenes/Anticipate';
import { ACT, CHANNELS, CIRCLE, CONTROL, FORESEE, KNOW } from './scenes/Chapters';
import { Simple } from './scenes/Simple';
import { Linked } from './scenes/Linked';
import { Outro } from './scenes/Outro';
import { SFX_CUES } from './sound';
import { Inspector } from './Inspector';
import './promo.css';

export type PromoProps = { withAudio: boolean; inspect?: boolean };

export function PromoFilm({ withAudio, inspect = false }: PromoProps) {
  const frame = useCurrentFrame();
  // Musical energy for the ground: low intro, lift on the drop, calm breakdown
  // under « Elle anticipe », full again after it, the outro settling.
  const energy =
    ramp(frame, beat(16), 20) *
    (1 - 0.6 * ramp(frame, sectionFrom('anticipate'), 30) + 0.6 * ramp(frame, sectionFrom('foresee'), 20)) *
    (1 - 0.5 * ramp(frame, sectionFrom('outro'), 300));
  const warmth = ramp(frame, sectionFrom('anticipate') + 205, 60) * (1 - ramp(frame, sectionFrom('foresee') - 20, 30));
  return (
    <AbsoluteFill className="promo">
      <Cosmos frame={frame} energy={energy} warmth={warmth} drift={frame / 600} />
      <Sequence from={0} durationInFrames={beat(24) + 15} name="Opening">
        <Opening />
      </Sequence>
      <Sequence from={sectionFrom('context') - 30} durationInFrames={sectionLength('context') + 50} name="Context">
        <Context />
      </Sequence>
      <Sequence from={sectionFrom('know')} durationInFrames={sectionLength('know') + 16} name="Ch1 know">
        <Chapter spec={KNOW} />
      </Sequence>
      <Sequence from={sectionFrom('action') - 20} durationInFrames={sectionLength('action') + 40} name="Action">
        <Action />
      </Sequence>
      <Sequence from={sectionFrom('act')} durationInFrames={sectionLength('act') + 16} name="Ch2 act">
        <Chapter spec={ACT} />
      </Sequence>
      <Sequence from={sectionFrom('anticipate') - 20} durationInFrames={sectionLength('anticipate') + 30} name="Anticipate">
        <Anticipate />
      </Sequence>
      <Sequence from={sectionFrom('foresee')} durationInFrames={sectionLength('foresee') + 16} name="Ch3 foresee">
        <Chapter spec={FORESEE} />
      </Sequence>
      <Sequence from={sectionFrom('devices') - 10} durationInFrames={sectionLength('devices') + 20} name="Devices">
        <Simple />
      </Sequence>
      <Sequence from={sectionFrom('channels')} durationInFrames={sectionLength('channels') + 16} name="Ch4 channels">
        <Chapter spec={CHANNELS} />
      </Sequence>
      <Sequence from={sectionFrom('circle')} durationInFrames={sectionLength('circle') + 16} name="Ch5 circle">
        <Chapter spec={CIRCLE} />
      </Sequence>
      <Sequence from={sectionFrom('control')} durationInFrames={sectionLength('control') + 16} name="Ch6 control">
        <Chapter spec={CONTROL} />
      </Sequence>
      <Sequence from={sectionFrom('linked') - 10} durationInFrames={sectionLength('linked') + 10} name="Linked">
        <Linked />
      </Sequence>
      <Sequence from={sectionFrom('outro') - 6} durationInFrames={sectionLength('outro') + 6} name="Outro">
        <Outro />
      </Sequence>
      <Vignette />
      {inspect && <Inspector />}
      {withAudio &&
        MUSIC_EDIT.reduce<{ at: number; parts: React.ReactNode[] }>(
          (acc, span, i) => {
            const length = span.to === null ? undefined : Math.round((span.to - span.from) * 60);
            acc.parts.push(
              <Sequence key={`music${i}`} from={acc.at} durationInFrames={length} name={`music ${span.from}-${span.to ?? 'end'} s`}>
                <Audio src={staticFile('audio/promo/lia-promo-music.mp3')} startFrom={Math.round(span.from * 60)} />
              </Sequence>,
            );
            return { at: acc.at + (length ?? 0), parts: acc.parts };
          },
          { at: 0, parts: [] },
        ).parts}
      {withAudio &&
        SFX_CUES.map((cue, i) => (
          <Sequence key={i} from={cue.frame} durationInFrames={cue.length} name={`sfx ${cue.sound}`}>
            <Audio src={staticFile(`audio/promo/sfx/${cue.sound}.mp3`)} volume={Math.min(1, cue.volume)} />
          </Sequence>
        ))}
    </AbsoluteFill>
  );
}
