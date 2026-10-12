import React, { type CSSProperties } from 'react';
import { AbsoluteFill, Audio, staticFile, useCurrentFrame, useVideoConfig } from 'remotion';
import { StoryMascot, type StoryMascotAct } from './StoryMascot';
import { createBeatTrack } from '../../../apps/web/src/lib/landing/beat-sync';
import { StoryLandingBackdrop } from './StoryLandingBackdrop';
import {
  NativeApprovalCard, NativeChatHeader, NativeComposer, NativeDateCallout,
  NativeDraftResponse, NativeNavigation, NativeResearchResponse, NativeResult,
  NativeSourceBlock, NativeUserMessage, STORY_DEMO,
} from './FaithfulUi';
import { easeProgress, liftedProgress, STORY_TIMING as T, unitProgress } from './product-story-timing';
import music from './music-v3.json';
import './product-story.css';

export type ProductStoryProps = {
  /** Omit only in an explicitly silent visual comparison. */
  withAudio?: boolean;
  /** Source-sized UI state for a side-by-side fidelity review. */
  comparison?: 'research' | 'approval' | 'result';
};

const lerp = (from: number, to: number, progress: number) => from + (to - from) * progress;
const beatTrack = createBeatTrack({ version: 1, beats: music.beatEntries.map(entry => [Number(entry[0]), Number(entry[1]), Boolean(entry[2])]) });
const at = (x: number, y: number, scale = 1): CSSProperties => ({
  left: x, top: y, transform: `scale(${scale})`, transformOrigin: '0 0',
});

function Cursor({ x, y, opacity, pressed }: { x: number; y: number; opacity: number; pressed: number }) {
  return <div className="story-cursor" style={{ left: x, top: y, opacity, transform: `scale(${1 - pressed * 0.12})` }}>
    <svg width="30" height="36" viewBox="0 0 30 36"><path d="M3 2L3 27L10 21L16 33L21 30L15 18L25 17Z" fill="#fff" stroke="#173b4c" strokeWidth="2" strokeLinejoin="round" /></svg>
  </div>;
}

export type NativeWindowProps = {
  frame: number; seconds: number; sourceOpacity?: number; calloutOpacity?: number; approvalOpacity?: number; resultOpacity?: number; comparison?: ProductStoryProps['comparison'];
};

export function NativeWindow({ frame, seconds, sourceOpacity = 1, calloutOpacity = 1, approvalOpacity = 1, resultOpacity = 1, comparison }: NativeWindowProps) {
  const { fps } = useVideoConfig();
  const isDraft = comparison === 'approval' || comparison === 'result' || seconds >= T.approval;
  const isResult = comparison === 'result' || seconds >= T.confirmedMessage;
  const reveal = comparison ? 1 : easeProgress(seconds, T.response, T.responseReady);
  const typing = !comparison && seconds < T.submitRequest ? STORY_DEMO.request.slice(0, Math.floor(unitProgress(seconds, T.typeRequest, T.submitRequest - 0.12) * STORY_DEMO.request.length)) : '';
  const userEnter = comparison ? 1 : easeProgress(seconds, T.submitRequest, T.submitRequest + 0.24);
  const columnScroll = comparison ? (isDraft ? 1 : 0) : easeProgress(seconds, T.approval, T.approval + 0.5);
  const approvalEnter = comparison ? 1 : easeProgress(seconds, T.draftReady, T.draftReady + 0.2);
  const resultEnter = comparison ? 1 : easeProgress(seconds, T.result, T.result + 0.24);
  return <div className="story-native-window">
    <StoryLandingBackdrop width={1440} height={960} frame={frame} fps={fps} beat={beatTrack.intensityAt(seconds)} />
    <NativeNavigation />
    <div className="story-native-page-panel">
      <NativeChatHeader frame={frame} />
      <div className="story-native-message-viewport">
        <div className="story-native-research-scene" style={{ opacity: columnScroll < 1 ? 1 : 0, transform: `translateY(${-650 * columnScroll}px)` }}>
          <NativeUserMessage text={STORY_DEMO.request} style={{ left: 95, top: 17, opacity: userEnter, transform: `translateY(${(1 - userEnter) * 12}px)` }} />
          <div style={{ opacity: comparison || seconds >= T.response ? 1 : 0 }}>
            <NativeResearchResponse frame={frame} reveal={reveal} sourceOpacity={sourceOpacity} calloutOpacity={calloutOpacity} highlight={0} />
          </div>
        </div>
        <div className="story-native-draft-scene" style={{ opacity: isDraft ? 1 : 0, transform: `translateY(${650 * (1 - columnScroll)}px)` }}>
          <NativeUserMessage text={STORY_DEMO.draftRequest} style={{ left: 95, top: 39 }} />
          <div style={{ opacity: comparison ? 1 : easeProgress(seconds, T.approval + 0.5, T.draftReady) }}><NativeDraftResponse frame={frame} /></div>
          {isResult ? <>
            <NativeUserMessage text="Confirmer" style={{ left: 95, top: 399, opacity: comparison ? 1 : easeProgress(seconds, T.confirmedMessage, T.confirmedMessage + 0.2) }} />
            <div style={{ opacity: resultEnter * resultOpacity }}><NativeResult frame={frame} /></div>
          </> : null}
        </div>
      </div>
      {!isResult && isDraft ? <div className="story-native-inline-approval" style={{ opacity: approvalOpacity * approvalEnter }}><NativeApprovalCard status={seconds >= T.confirm ? 'resolved' : 'awaiting'} /></div> : null}
      <NativeComposer text={typing} />
    </div>
  </div>;
}

/** Faithful product components are the objects of the choreography. Extracted
 * definition list and approval are film layers, not newly claimed product UI. */
export function ProductStory({ withAudio = true, comparison }: ProductStoryProps) {
  const frame = useCurrentFrame();
  const { fps } = useVideoConfig();
  const seconds = frame / fps;
  if (comparison) {
    return <AbsoluteFill className="product-story story-comparison"><style>{`@font-face{font-family:'Lia Story Inter';src:url('${staticFile('fonts/Inter-Variable.woff2')}') format('woff2');font-weight:100 900;font-display:block;}`}</style><div style={{ ...at(240, 60), position: 'absolute' }}><NativeWindow frame={frame} seconds={comparison === 'research' ? 4 : comparison === 'approval' ? 14 : 19.8} comparison={comparison} /></div></AbsoluteFill>;
  }

  const windowEnter = easeProgress(seconds, T.enter, T.enter + 0.52);
  const windowExit = easeProgress(seconds, T.exit, T.finale);
  const sourceLift = liftedProgress(seconds, T.sourcesLift, T.sourcesReturn, 0.32);
  const dateHighlight = easeProgress(seconds, T.dates, T.datesReady);
  const calloutLift = liftedProgress(seconds, T.calloutLift, T.calloutReturn, 0.24);
  const approvalLift = liftedProgress(seconds, T.approvalLift, T.approvalReturn, 0.24);
  const resultLift = liftedProgress(seconds, T.result + 0.24, T.exit, 0.24);
  const foreground = Math.max(sourceLift, calloutLift, approvalLift, resultLift);
  const windowScale = lerp(0.77, 0.69, foreground);
  const windowX = lerp(692, 780, foreground);
  const windowY = lerp(172, 155, foreground);
  const windowStyle: CSSProperties = {
    position: 'absolute', left: windowX + (1 - windowEnter) * 140 + windowExit * 80,
    top: windowY + (1 - windowEnter) * 25,
    opacity: windowEnter * (1 - windowExit),
    transformOrigin: '0 0',
    transform: `perspective(2200px) rotateY(${-3.5 * (1 - foreground)}deg) rotateX(${1.2 * (1 - foreground)}deg) scale(${windowScale})`,
  };

  const phases = [
    { from: T.enter, until: T.clarity, eyebrow: 'AVANT TA RÉUNION', lines: ['Tes sources,', 'une réponse.'], detail: ['Documents, e-mails, compte rendu.', 'Prépare ta réunion dans un même fil.'], accent: '#2c56c4' },
    { from: T.clarity, until: T.approval, eyebrow: 'UN DÉTAIL QUI COMPTE', lines: ['Deux dates,', 'une alerte.'], detail: ['Le 19 ou le 22 octobre ?', 'Le point à clarifier apparaît.'], accent: '#7c5cf6' },
    { from: T.approval, until: T.exit, eyebrow: 'UNE ACTION QUI T’APPARTIENT', lines: ['Tu gardes', 'la main.'], detail: ['Un brouillon à relire.', 'Confirme, modifie ou annule.'], accent: '#12828c' },
  ];
  const mascotEnter = easeProgress(seconds, T.enter + 0.22, T.enter + 0.65);
  const finale = easeProgress(seconds, T.exit, T.finale);
  const confirmPress = liftedProgress(seconds, T.confirm - 0.1, T.confirm + 0.09, 0.08);
  const cursorEnter = easeProgress(seconds, T.confirm - 0.9, T.confirm - 0.6);
  const cursorExit = easeProgress(seconds, T.confirm + 0.15, T.confirm + 0.4);
  const cursorProgress = easeProgress(seconds, T.confirm - 0.85, T.confirm - 0.16);
  const approvalStatus = seconds >= T.confirm + 0.2 ? 'resolved' : seconds >= T.confirm ? 'submitting' : 'awaiting';
  const act: StoryMascotAct = seconds >= T.approval ? 'approval' : seconds >= T.clarity ? 'clarity' : 'context';
  const actStart = act === 'approval' ? T.approval : act === 'clarity' ? T.clarity : 0;
  const mascotShiftToClarity = easeProgress(seconds, T.clarity, T.clarity + 0.65);
  const mascotShiftToApproval = easeProgress(seconds, T.approval, T.approval + 0.65);
  const mascotX = 130 + 26 * mascotShiftToClarity - 10 * mascotShiftToApproval;
  const mascotY = 658 - 12 * mascotShiftToClarity + 8 * mascotShiftToApproval;

  return <AbsoluteFill className="product-story">
    <style>{`@font-face{font-family:'Lia Story Inter';src:url('${staticFile('fonts/Inter-Variable.woff2')}') format('woff2');font-weight:100 900;font-display:block;}`}</style>
    {withAudio ? <Audio src={staticFile(music.audio)} volume={audioFrame => {
      const s = audioFrame / fps;
      return easeProgress(s, 0, 0.4) * (1 - easeProgress(s, 22.8, 24)) * 0.85;
    }} /> : null}
    <StoryLandingBackdrop width={1920} height={1080} frame={frame} fps={fps} beat={beatTrack.intensityAt(seconds)} />
    <div className="story-brand" style={{ opacity: 1 - finale }}>LIA</div>
    <div className="story-progress" style={{ opacity: 1 - finale }}>
      {['Le contexte', 'La clarté', 'Ton accord'].map((label, index) => {
        const active = index === (seconds >= T.approval ? 2 : seconds >= T.clarity ? 1 : 0);
        return <div key={label} className={active ? 'is-active' : ''}>{label}</div>;
      })}
    </div>
    {phases.map(phase => {
      const enter = easeProgress(seconds, phase.from, phase.from + 0.24);
      const exit = easeProgress(seconds, phase.until - 0.05, phase.until + 0.19);
      return <div key={phase.from} className="story-value" style={{ opacity: enter * (1 - exit), transform: `translateY(${-exit * 22}px)`, '--story-accent': phase.accent } as CSSProperties}><p className="story-value-eyebrow">{phase.eyebrow}</p><h1>{phase.lines.map((line, index) => {
        const own = easeProgress(seconds, phase.from + index * 0.1, phase.from + index * 0.1 + 0.24);
        return <span key={line} style={{ clipPath: `inset(0 0 ${(1 - own) * 100}% 0)`, transform: `translateY(${(1 - own) * (index ? 28 : 10)}px)` }}>{line}</span>;
      })}</h1><p className="story-value-detail" style={{ opacity: easeProgress(seconds, phase.from + 0.28, phase.from + 0.52), transform: `translateY(${(1 - easeProgress(seconds, phase.from + 0.28, phase.from + 0.52)) * 12}px)` }}>{phase.detail.map(line => <span key={line}>{line}</span>)}</p></div>;
    })}
    <div style={windowStyle}><NativeWindow frame={frame} seconds={seconds} sourceOpacity={1 - sourceLift} calloutOpacity={1 - calloutLift} approvalOpacity={1 - approvalLift} resultOpacity={1 - resultLift} /></div>

    {/* One excerpt preserves the product's shared definition-list grid. */}
    {sourceLift > 0 ? (() => {
      const sourceX = windowX + 279 * windowScale;
      const sourceY = windowY + 444 * windowScale;
      const focus = liftedProgress(seconds, T.dates, T.datesReady + 0.65, 0.4);
      const scale = lerp(windowScale, 1.6 + focus * 0.025, sourceLift);
      const x = lerp(sourceX, 630 - focus * 8, sourceLift);
      const y = lerp(sourceY, 550 - focus * 4, sourceLift);
      const rowHighlights = [dateHighlight, easeProgress(seconds, T.dates + 0.28, T.datesReady), 0];
      return <div className="story-source-excerpt" style={{ ...at(x, y, scale), opacity: sourceLift, transform: `perspective(2000px) rotateY(${(1 - sourceLift) * -3}deg) scale(${scale})` }}><NativeSourceBlock rowHighlights={rowHighlights} /></div>;
    })() : null}

    {calloutLift > 0 ? <div className="story-callout-excerpt" style={{ ...at(lerp(windowX + 279 * windowScale, 608, calloutLift), lerp(windowY + 342 * windowScale, 566, calloutLift), lerp(windowScale, 1.34, calloutLift)), opacity: calloutLift }}><NativeDateCallout /></div> : null}

    {approvalLift > 0 ? <div className="story-approval-excerpt" style={{ ...at(lerp(windowX + 272 * windowScale, 668, approvalLift), lerp(windowY + 677 * windowScale, 534, approvalLift), lerp(windowScale, 1.3, approvalLift)), opacity: approvalLift }}><NativeApprovalCard status={approvalStatus} pressed={confirmPress > 0.3} /></div> : null}
    {resultLift > 0 ? <div className="story-result-excerpt" style={{ ...at(lerp(windowX + 627 * windowScale, 812, resultLift), lerp(windowY + 632 * windowScale, 594, resultLift), lerp(windowScale, 1.65, resultLift)), opacity: resultLift }}><NativeResult frame={frame} /></div> : null}
    <Cursor x={lerp(1710, 804, cursorProgress)} y={lerp(857, 738, cursorProgress)} opacity={cursorEnter * (1 - cursorExit)} pressed={confirmPress} />

    <div className="story-mascot" style={{ left: mascotX, top: mascotY, opacity: mascotEnter * (1 - finale), transformOrigin: '50% 89%', transform: `translateY(${(1 - mascotEnter) * 22}px)` }}><StoryMascot size={350} frame={Math.max(0, frame - Math.round(actStart * fps))} fps={fps} act={act} /></div>
    <div className="story-demo-disclosure" style={{ opacity: 1 - finale }}>Données de démonstration.</div>

    <div className="story-finale" style={{ opacity: finale, transform: `translateY(${(1 - finale) * 30}px)` }}>
      <div className="story-final-copy"><p>LIA</p><h2>Ton contexte.<br />Ton accord.</h2></div>
      <div className="story-final-mascot"><StoryMascot size={420} frame={Math.max(0, frame - Math.round(T.exit * fps))} fps={fps} act="finale" /></div>
      <p className="story-credit">{music.attribution}</p>
    </div>
  </AbsoluteFill>;
}
