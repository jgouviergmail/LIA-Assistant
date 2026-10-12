import React, { type CSSProperties } from 'react';
import {
  AbsoluteFill,
  Audio,
  Easing,
  Freeze,
  Img,
  OffthreadVideo,
  Sequence,
  interpolate,
  spring,
  staticFile,
  useCurrentFrame,
  useVideoConfig,
} from 'remotion';
import { NativeCharacter } from './AvatarShowcase';
import type { MotionScene } from './content';
import { buildTimeline } from './timeline';
import {
  NATIVE_CAPTURES,
  PROOF_SHOTS,
  timeChapterShots,
  type Camera,
  type NativeCapture,
  type ProductShot,
  type TimedProductShot,
} from './real-product-shots';
import captureManifest from '../public/capture-v2/manifest.json';
import music from './music.json';
import './real-product-film.css';

type CapturedAsset = {
  id: string;
  path: string;
  type: string;
  width: number;
  height: number;
  clipPath?: string;
  beforePath?: string;
  fromSeconds?: number;
  durationSeconds?: number;
  scene?: { exercised?: string[] };
  exercised?: string[];
};

/** Provenance controls which pixels can enter the film. */
const resolvedCaptures: Readonly<Record<string, NativeCapture>> = Object.fromEntries(
  (captureManifest.assets as CapturedAsset[]).map(asset => [
    asset.id,
    {
      ...NATIVE_CAPTURES[asset.id],
      id: asset.id,
      kind: asset.clipPath ? 'video' : 'image',
      path: asset.clipPath ?? asset.path,
      width: asset.width,
      height: asset.height,
      provenance: 'capture-v2/manifest.json',
      capturedActions: asset.exercised ?? asset.scene?.exercised ?? [],
      visibleFeatures: NATIVE_CAPTURES[asset.id]?.visibleFeatures ?? [],
      durationSeconds: asset.durationSeconds,
      clipFromSeconds: asset.fromSeconds,
    } satisfies NativeCapture,
  ])
);

const frenchChat = (captureManifest.assets as CapturedAsset[]).find(
  asset => asset.id === 'chat' && asset.beforePath
);
export const CURRENT_CAPTURES: Readonly<Record<string, NativeCapture>> = {
  ...resolvedCaptures,
  ...(frenchChat
    ? {
        'dossier-still': {
          ...NATIVE_CAPTURES.dossier,
          id: 'dossier-still',
          path: frenchChat.beforePath!,
          width: frenchChat.width,
          height: frenchChat.height,
          provenance: 'capture-v2/manifest.json',
        },
      }
    : {}),
};

export type RealProductFilmProps = {
  scenes: readonly MotionScene[];
  captures?: Readonly<Record<string, NativeCapture>>;
  soundtrack?: {
    audio: string;
    beats: number[];
    title?: string;
    artist?: string;
    license?: string;
    attribution?: string;
  };
};

const clamp = (value: number, min = 0, max = 1) => Math.max(min, Math.min(max, value));
const animation = (frame: number, fps: number, delay = 0, damping = 19) =>
  spring({
    frame: Math.max(0, frame - delay),
    fps,
    config: { damping, stiffness: 175, mass: 0.8 },
  });
const between = (a: number, b: number, progress: number) => a + (b - a) * progress;
const cameraAt = (start: Camera, end: Camera, progress: number): Camera => ({
  x: between(start.x, end.x, progress),
  y: between(start.y, end.y, progress),
  width: between(start.width, end.width, progress),
  roll: between(start.roll ?? 0, end.roll ?? 0, progress),
});

/** Pixel-space camera; boundaries preserve the captured surface without synthetic fill. */
export function nativeCameraStyle(
  camera: Camera,
  asset: Pick<NativeCapture, 'width' | 'height'>,
  viewport: { width: number; height: number }
): CSSProperties {
  const scale = viewport.width / (asset.width * camera.width);
  const viewWidth = viewport.width / scale;
  const viewHeight = viewport.height / scale;
  const x =
    asset.width <= viewWidth
      ? 0.5
      : clamp(camera.x, viewWidth / asset.width / 2, 1 - viewWidth / asset.width / 2);
  const y =
    asset.height <= viewHeight
      ? 0.5
      : clamp(camera.y, viewHeight / asset.height / 2, 1 - viewHeight / asset.height / 2);
  return {
    width: asset.width,
    height: asset.height,
    transformOrigin: '0 0',
    transform: `translate(${viewport.width / 2 - x * asset.width * scale}px, ${viewport.height / 2 - y * asset.height * scale}px) scale(${scale})`,
  };
}

function NativeScreen({
  shot,
  capture,
  duration,
}: {
  shot: ProductShot;
  capture: NativeCapture;
  duration: number;
}) {
  const frame = useCurrentFrame();
  const { fps, width, height } = useVideoConfig();
  const start = shot.start ?? { x: 0.5, y: 0.5, width: 1.04 };
  const end = shot.end ?? start;
  // A quick camera move establishes the detail; the remaining time keeps it readable.
  const travel = interpolate(
    frame,
    [0, Math.min(duration - 1, fps * 1.25), duration - 1],
    [0, 0.82, 1],
    {
      extrapolateLeft: 'clamp',
      extrapolateRight: 'clamp',
      easing: Easing.bezier(0.19, 1, 0.22, 1),
    }
  );
  const camera = cameraAt(start, end, travel);
  const lift = animation(frame, fps, 0, 23);
  const targetStyle = nativeCameraStyle(camera, capture, { width, height });
  const clipRate = shot.clipRate ?? 1;
  const requestedStart = (capture.clipFromSeconds ?? 0) + (shot.videoStartSeconds ?? 0);
  const sourceStart = Math.max(
    0,
    Math.min(requestedStart, (capture.durationSeconds ?? Infinity) - 1 / fps)
  );
  const availableFrames = Math.max(
    1,
    Math.floor((((capture.durationSeconds ?? Infinity) - sourceStart) * fps) / clipRate) - 1
  );
  return (
    <AbsoluteFill className="real-product-screen">
      <div className="real-product-capture" style={targetStyle}>
        {capture.kind === 'video' ? (
          <Freeze frame={availableFrames} active={frame > availableFrames}>
            <OffthreadVideo
              src={staticFile(capture.path)}
              muted
              trimBefore={Math.floor(sourceStart * fps)}
              playbackRate={clipRate}
              style={{ width: capture.width, height: capture.height }}
            />
          </Freeze>
        ) : (
          <Img
            src={staticFile(capture.path)}
            style={{ width: capture.width, height: capture.height }}
          />
        )}
      </div>
      {shot.caption && (
        <div
          className="real-product-caption"
          style={{ opacity: lift, transform: `translateY(${(1 - lift) * 65}px)` }}
        >
          <span>{shot.caption}</span>
        </div>
      )}
      <div className="real-product-provenance">
        Interface réelle de LIA · données de démonstration
        {capture.kind === 'video' ? ' · interaction enregistrée' : ''}
      </div>
    </AbsoluteFill>
  );
}

/** Cards are literal native screenshot regions; only their editorial placement moves. */
function NativeExtracts({ shot, capture }: { shot: ProductShot; capture: NativeCapture }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const regions = shot.extracts ?? [];
  return (
    <AbsoluteFill className="real-product-extracts">
      <Img src={staticFile(capture.path)} className="real-product-extract-context" />
      <div className="real-product-extract-brand">LIA</div>
      {regions.map((region, index) => {
        const arrive = animation(frame, fps, index * 4, 20);
        const scale = between(1.12, 1.8, arrive);
        return (
          <div
            key={index}
            className="real-product-native-extract"
            style={{
              left: 960 - region.width / 2,
              top: regions.length === 1 ? 500 : 285 + index * 205,
              width: region.width,
              height: region.height,
              opacity: arrive,
              transform: `translate(${(1 - arrive) * (index % 2 ? 420 : -420)}px, ${(1 - arrive) * 240}px) rotate(${(index - 1) * 2.5}deg) scale(${scale})`,
            }}
          >
            <Img
              src={staticFile(capture.path)}
              style={{
                position: 'absolute',
                width: capture.width,
                height: capture.height,
                maxWidth: 'none',
                left: -region.x,
                top: -region.y,
              }}
            />
          </div>
        );
      })}
      <div className="real-product-provenance">
        Extraits de l’interface réelle de LIA · données de démonstration
      </div>
    </AbsoluteFill>
  );
}

function KineticType({ shot, duration }: { shot: ProductShot; duration: number }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const entry = animation(frame, fps, 0, 20);
  const exit = clamp((frame - duration + Math.max(4, fps * 0.16)) / Math.max(4, fps * 0.16));
  const words = (shot.headline ?? '').split(' ');
  return (
    <AbsoluteFill className="real-product-type">
      <div
        className="real-product-type-plane"
        style={{ transform: `scaleX(${entry})`, opacity: 1 - exit }}
      />
      <div className="real-product-wordline" style={{ transform: `translateX(${-exit * 190}px)` }}>
        {words.map((word, index) => {
          const wordEntry = animation(frame, fps, index * 1.1, 18);
          return (
            <span
              key={`${word}-${index}`}
              style={{
                transform: `translateY(${(1 - wordEntry) * 235}px) rotate(${(1 - wordEntry) * 7}deg)`,
                opacity: wordEntry,
              }}
            >
              {word}
            </span>
          );
        })}
      </div>
      <span className="real-product-type-brand">LIA</span>
    </AbsoluteFill>
  );
}

const CAST = ['moss', 'lumen', 'nimbo', 'orbit', 'boulon', 'oscar'] as const;

function NativeCompanions({ shot, duration }: { shot: ProductShot; duration: number }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const entry = animation(frame, fps, 0, 20);
  const hero = shot.character ?? 'bip';
  const isRange = !shot.character;
  // The native rig's expression tape advances with film time, not the wall clock.
  const expressionFrame = Math.floor(frame * 4 + (hero === 'smiley' ? 11 * fps : 0));
  const drift = interpolate(frame, [0, duration], [-22, 22], { extrapolateRight: 'clamp' });
  return (
    <AbsoluteFill className="real-product-companions">
      <div
        className="real-product-companion-word"
        style={{ transform: `translateX(${(1 - entry) * 550 - drift}px)` }}
      >
        LIA
      </div>
      <div
        className="real-product-avatar-shadow"
        style={{ transform: `scale(${0.6 + entry * 0.4})`, opacity: entry * 0.25 }}
      />
      <div
        className="real-product-hero-character"
        style={{
          transform: `translate(${(1 - entry) * -400 + drift}px, ${(1 - entry) * 180}px) scale(${0.82 + entry * 0.18})`,
          opacity: entry,
        }}
      >
        <NativeCharacter kind={hero} size={isRange ? 390 : 650} frame={expressionFrame} />
      </div>
      {isRange &&
        CAST.map((kind, index) => {
          const arrival = animation(frame, fps, 5 + index * 3, 18);
          return (
            <div
              key={kind}
              className="real-product-cast-character"
              style={{
                left: 250 + index * 245,
                transform: `translateY(${(1 - arrival) * 500}px) rotate(${(1 - arrival) * (index % 2 ? 10 : -10)}deg)`,
                opacity: arrival,
              }}
            >
              <NativeCharacter
                kind={kind}
                size={180}
                variant={index % 2 ? 'female' : 'male'}
                frame={expressionFrame + index * 4}
              />
            </div>
          );
        })}
      <div
        className="real-product-companion-copy"
        style={{ opacity: entry, transform: `translateY(${(1 - entry) * 35}px)` }}
      >
        {shot.caption ??
          (hero === 'smiley' ? 'Des expressions. Une présence.' : 'Ton compagnon, à tes côtés.')}
      </div>
      <span className="real-product-native-note">Personnages et animations natifs de LIA</span>
    </AbsoluteFill>
  );
}

function ProductShotView({
  entry,
  captures,
}: {
  entry: TimedProductShot;
  captures: Readonly<Record<string, NativeCapture>>;
}) {
  const frame = useCurrentFrame();
  const { shot, durationInFrames, accent } = entry;
  const { fps, width } = useVideoConfig();
  const transitionFrames = Math.max(6, Math.round(fps * 0.24));
  const incoming = entry.from === 0 || !shot.transition ? 1 : clamp(frame / transitionFrames);
  const outgoing = clamp((frame - durationInFrames) / transitionFrames);
  const shift = shot.transition === 'push' ? (1 - incoming - outgoing) * width : -outgoing * width;
  const mask = shot.transition === 'iris' ? `circle(${incoming * 115}% at 50% 50%)` : undefined;
  let content: React.ReactNode;
  if (shot.kind === 'type') content = <KineticType shot={shot} duration={durationInFrames} />;
  else if (shot.kind === 'companions')
    content = <NativeCompanions shot={shot} duration={durationInFrames} />;
  else {
    const capture = captures[shot.assetId ?? ''];
    if (!capture) throw new Error(`Missing real capture for ${shot.id}: ${shot.assetId}`);
    content =
      shot.kind === 'extracts' ? (
        <NativeExtracts shot={shot} capture={capture} />
      ) : (
        <NativeScreen shot={shot} capture={capture} duration={durationInFrames} />
      );
  }
  return (
    <AbsoluteFill
      style={
        {
          '--real-accent': accent,
          transform: `translateX(${shift}px)`,
          clipPath: mask,
        } as CSSProperties
      }
    >
      {content}
    </AbsoluteFill>
  );
}

function RealFinale({ duration, attribution }: { duration: number; attribution: string }) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const arrive = animation(frame, fps, 0, 24);
  return (
    <AbsoluteFill className="real-product-finale">
      <div
        className="real-product-finale-character"
        style={{ transform: `translateY(${(1 - arrive) * 600}px)` }}
      >
        <NativeCharacter size={340} frame={frame + fps * 12} />
      </div>
      <div className="real-product-finale-copy" style={{ opacity: arrive }}>
        <strong>LIA</strong>
        <p>Ta journée. Ton contexte. Tes choix.</p>
        <span>lia.jeyswork.com</span>
      </div>
      <div
        className="real-product-finale-line"
        style={{ transform: `scaleX(${clamp(frame / duration)})` }}
      />
      <small className="real-product-music-credit">Musique : {attribution}</small>
    </AbsoluteFill>
  );
}

function RealFilmShell({
  entries,
  captures,
  soundtrack,
  finalFrames = 0,
}: {
  entries: readonly TimedProductShot[];
  captures: Readonly<Record<string, NativeCapture>>;
  soundtrack: NonNullable<RealProductFilmProps['soundtrack']>;
  finalFrames?: number;
}) {
  const { fps } = useVideoConfig();
  const pictureDuration = entries.at(-1)!.from + entries.at(-1)!.durationInFrames;
  const duration = pictureDuration + finalFrames;
  const attribution =
    soundtrack.attribution ?? `${soundtrack.title} — ${soundtrack.artist} · ${soundtrack.license}`;
  const overlap = Math.max(6, Math.round(fps * 0.24));
  return (
    <AbsoluteFill className="real-product-film">
      <style>{`@font-face { font-family: 'Lia Inter'; src: url('${staticFile('fonts/Inter-Variable.woff2')}') format('woff2'); font-weight: 100 900; font-display: block; }`}</style>
      <Audio
        src={staticFile(soundtrack.audio)}
        volume={frame =>
          interpolate(frame, [0, fps * 0.15, duration - fps * 1.5, duration], [0, 1, 1, 0], {
            extrapolateLeft: 'clamp',
            extrapolateRight: 'clamp',
          })
        }
      />
      {entries.map(entry => (
        <Sequence
          key={entry.shot.id}
          from={entry.from}
          durationInFrames={entry.durationInFrames + overlap}
        >
          <ProductShotView entry={entry} captures={captures} />
        </Sequence>
      ))}
      {finalFrames > 0 && (
        <Sequence from={pictureDuration} durationInFrames={finalFrames}>
          <RealFinale duration={finalFrames} attribution={attribution} />
        </Sequence>
      )}
      {finalFrames === 0 && (
        <Sequence from={Math.max(0, duration - fps * 4)} durationInFrames={fps * 4}>
          <div className="real-product-proof-credit">Musique : {attribution}</div>
        </Sequence>
      )}
    </AbsoluteFill>
  );
}

export function RealProductFilm({
  scenes,
  captures = CURRENT_CAPTURES,
  soundtrack = music,
}: RealProductFilmProps) {
  const { fps } = useVideoConfig();
  const chapters = buildTimeline(scenes, soundtrack.beats, fps);
  const entries = sequenceNativePlayback(
    chapters.flatMap(({ scene, from, durationInFrames }) =>
      timeChapterShots(scene, from, durationInFrames, undefined, soundtrack.beats, fps)
    ),
    captures,
    fps
  );
  return (
    <RealFilmShell
      entries={entries}
      captures={captures}
      soundtrack={soundtrack}
      finalFrames={fps * 4}
    />
  );
}

export function RealProductProof({
  captures = CURRENT_CAPTURES,
  soundtrack = music,
}: Omit<RealProductFilmProps, 'scenes'>) {
  const { fps } = useVideoConfig();
  const proofScene = {
    id: 'real-proof',
    accent: '#057baa',
    featureKeys: [],
  } as unknown as MotionScene;
  const entries = sequenceNativePlayback(
    timeChapterShots(proofScene, 0, fps * 30, PROOF_SHOTS, soundtrack.beats, fps),
    captures,
    fps
  );
  return <RealFilmShell entries={entries} captures={captures} soundtrack={soundtrack} />;
}

/** Match cuts on the same recording continue its real actions instead of restarting. */
export function sequenceNativePlayback(
  entries: readonly TimedProductShot[],
  captures: Readonly<Record<string, NativeCapture>>,
  fps: number
): TimedProductShot[] {
  const sourceCursors = new Map<string, number>();
  return entries.map(entry => {
    const { shot } = entry;
    const asset = captures[shot.assetId ?? ''];
    if (asset?.kind !== 'video' || shot.kind !== 'screen') return entry;
    const key = `${entry.chapterId}:${asset.id}`;
    const start = shot.videoStartSeconds ?? sourceCursors.get(key) ?? 0;
    sourceCursors.set(key, start + (entry.durationInFrames / fps) * (shot.clipRate ?? 1));
    return { ...entry, shot: { ...shot, videoStartSeconds: start } };
  });
}
