import React, { useMemo } from 'react';
import { CHANNEL_KEYS, CHANNELS, type ChannelValues } from '../../../apps/web/src/components/eyes/rig/channels';
import { deriveExpression } from '../../../apps/web/src/components/eyes/expression-engine';
import { resolvePose } from '../../../apps/web/src/components/eyes/rig/poses';
import { springStep, type SpringState } from '../../../apps/web/src/components/eyes/rig/spring';
import { speechTapes } from '../../../apps/web/src/components/eyes/rig/speech';
import { tapeTargetAt } from '../../../apps/web/src/components/eyes/rig/tape';
import type { RigEyeStyleId } from '../../../apps/web/src/components/eyes/eye-styles';
import { NativeAvatarPose, NativeMonitor } from './AvatarShowcase';
import { avatarContextAt, AVATAR_GALLERY_CHARACTERS } from './avatar-context';
import { easeProgress, liftedProgress } from './product-story-timing';

export type AvatarDemonstrationProps = {
  frame: number;
  fps: number;
  width?: number;
  height?: number;
  durationSeconds?: number;
  mode?: 'lumo' | 'ensemble' | 'all';
  labels?: boolean;
};

function randomWithSeed(seed: number) {
  let state = seed >>> 0;
  return () => {
    state = (state * 1664525 + 1013904223) >>> 0;
    return state / 4294967296;
  };
}

/** Replays the application's signal→expression→pose→spring path on video time.
 * Native speech tapes illustrate the speaking state; no speech or provider is
 * executed. A frame seek samples exactly the same result as sequential render. */
function sampleContextRig(style: RigEyeStyleId, fps: number, durationSeconds: number) {
  const first = resolvePose(deriveExpression(avatarContextAt(0, durationSeconds).inputs).expression, style);
  const springs = Object.fromEntries(CHANNEL_KEYS.map(channel => [channel, { value: first[channel], velocity: 0 }])) as Record<keyof ChannelValues, SpringState>;
  const tapes = speechTapes(randomWithSeed(54109));
  const samples: ChannelValues[] = [];
  for (let frame = 0; frame <= Math.ceil(durationSeconds * fps); frame++) {
    const seconds = frame / fps;
    const context = avatarContextAt(seconds, durationSeconds);
    const expression = deriveExpression(context.inputs);
    const target = resolvePose(expression.expression, style);
    target.gazeX = expression.gaze?.x ?? (context.id === 'joy' ? 0 : -0.16);
    target.gazeY = expression.gaze?.y ?? 0;
    target.headYaw = target.gazeX * 0.5;
    target.headPitch = target.gazeY * 0.4;
    target.mass = 1 + Math.sin(seconds * 1.43) * 0.006;
    const blink = [1.48, 4.7, 7.62, 10.38, 13.6, 16.88, 20.42].reduce((value, at) => Math.max(value, liftedProgress(seconds, at, at + 0.055, 0.072)), 0);
    target.blinkL = blink;
    target.blinkR = blink;
    if (expression.expression === 'speaking') {
      for (const tape of tapes) {
        const value = tapeTargetAt(tape, (seconds - context.at) * 1000);
        if (value !== null) target[tape.channel] = (tape.relative ? target[tape.channel] : 0) + value;
      }
    }
    const sample = { ...target };
    for (const channel of CHANNEL_KEYS) {
      const group = CHANNELS[channel].group;
      const frequency = group === 'blink' ? 13 : group === 'mouth' ? 7 : group === 'gaze' ? 4.8 : 3.4;
      springs[channel] = springStep(springs[channel], target[channel], { frequency, damping: 0.85 }, 1000 / fps);
      sample[channel] = springs[channel].value;
    }
    sample.mouthArc = Math.abs(sample.mouthCurve);
    samples.push(sample);
  }
  return samples;
}

const INK = '#1b293b';
const QUIET = '#53647a';
const ACCENT = '#1583a3';

/** Standalone editorial stage, not a fabricated application window. Lumo is
 * enlarged without changing the native artwork, facial geometry or poses. */
export function AvatarDemonstration({ frame, fps, width = 1100, height = 690, durationSeconds = 24, mode = 'all', labels = true }: AvatarDemonstrationProps) {
  const seconds = Math.max(0, frame) / fps;
  const lumoSeconds = mode === 'all' ? durationSeconds * 0.5 : durationSeconds;
  const galleryAt = mode === 'all' ? lumoSeconds : 0;
  const gallery = mode === 'ensemble' || mode === 'all' && seconds >= galleryAt;
  const context = avatarContextAt(seconds, lumoSeconds);
  const samples = useMemo(() => Object.fromEntries(
    (['cozmo','capsules','billes','amande','traits','anneaux','smiley'] as const)
      .map(style=>[style,sampleContextRig(style,fps,Math.max(durationSeconds,0.1))])
  ) as Record<RigEyeStyleId,ChannelValues[]>, [fps,durationSeconds]);
  const lumoSamples = useMemo(()=>sampleContextRig('billes',fps,Math.max(lumoSeconds,0.1)),[fps,lumoSeconds]);
  const sampleFrame = Math.min(samples.billes.length - 1, Math.floor(Math.max(0, frame)));
  const lumoFrame = Math.min(lumoSamples.length - 1, sampleFrame);
  const entrance = easeProgress(seconds, galleryAt, galleryAt + 0.35);
  const transition = mode === 'all' ? easeProgress(seconds, galleryAt - 0.25, galleryAt + 0.25) : gallery ? 1 : 0;
  const lumoSize = Math.min(height * 0.77, width * 0.49);
  const gallerySize = Math.min(height * 0.30, width * 0.132);
  const contextEntrance = easeProgress(seconds - context.at, 0, 0.28);
  return <div aria-label="Avatars animés LIA" style={{ position: 'relative', width, height, color: INK, fontFamily: 'Inter, sans-serif' }}>
    <div style={{ position: 'absolute', inset: 0, opacity: 1 - transition }}>
      <div style={{ position: 'absolute', left: width * 0.01, top: height * 0.04 }}>
        <NativeAvatarPose kind="lumen" variant="male" size={lumoSize} values={lumoSamples[lumoFrame]} />
      </div>
      {labels ? <div style={{ position: 'absolute', left: width * 0.52, top: height * 0.12, width: width * 0.45 }}>
        <div style={{ fontSize: 42, fontWeight: 750, letterSpacing: -1.5 }}>Lumo</div>
        <div style={{ fontSize: 21, color: QUIET, marginTop: 7 }}>Avatar masculin</div>
        <div style={{ marginTop: 64, opacity: contextEntrance }}>
          <div style={{ width: 38, height: 4, borderRadius: 2, background: ACCENT, marginBottom: 24 }} />
          <div style={{ fontSize: 35, fontWeight: 680, lineHeight: 1.15, letterSpacing: -0.8 }}>{context.title}</div>
          <div style={{ fontSize: 24, color: QUIET, lineHeight: 1.4, marginTop: 17 }}>{context.detail}</div>
        </div>
      </div> : null}
    </div>
    {gallery || transition > 0 ? <div style={{ position: 'absolute', inset: 0, opacity: transition * entrance }}>
      {labels ? <div style={{ position: 'absolute', top: height * 0.075, width: '100%', textAlign: 'center', fontSize: 35, fontWeight: 700, letterSpacing: -1 }}>Choisis ton compagnon</div> : null}
      {AVATAR_GALLERY_CHARACTERS.map((character,index) => {
        const column=index%7;
        const row=Math.floor(index/7);
        const center=width*(column+.5)/7;
        const style=character.renderer==='rig'?character.id:character.id==='smiley'?'smiley':'billes';
        const values=samples[style][sampleFrame];
        return <div key={character.id} data-avatar-id={character.id} style={{ position: 'absolute', left: center-gallerySize/2, top:height*(.25+row*.35),width:gallerySize,textAlign:'center' }}>
          {character.renderer==='rig'?<NativeMonitor style={character.id} size={gallerySize} values={values}/>:<NativeAvatarPose kind={character.id} size={gallerySize} values={values}/>}
          {labels ? <div style={{marginTop:14,fontSize:20,fontWeight:620,whiteSpace:'nowrap'}}>{character.name}</div> : null}
        </div>;
      })}
      {labels?<div style={{position:'absolute',bottom:height*.035,width:'100%',textAlign:'center',fontSize:19,color:QUIET}}>Des expressions qui accompagnent tes échanges.</div>:null}
    </div> : null}
  </div>;
}
