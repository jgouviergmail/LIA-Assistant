import React from 'react';
import { AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame } from 'remotion';
import { CalendarDays, Mail, Mic, Brain, Radio, FileText, ArrowRight, ShieldCheck } from 'lucide-react';
import { BriefingScene, ContextScene, ApprovalScene } from './DailyScenes';
import { VoiceScene, MemoryScene, MeetingScene } from './HumanScenes';
import { RoutineScene, SkillScene, RadioScene } from './WorkScenes';
import { FilmBip, FilmBrand, ease, uiSpring } from './shared';
import { frameForScene } from './film-timing';
import score from '../../public/audio/feature-film/score.json';
import './feature-film.css';

export const FEATURE_FILM_FPS = 60;
export const FEATURE_FILM_FRAMES = 4800;
export const FEATURE_CHAPTERS = [
  { id: 'day', label: 'Ta journée', component: BriefingScene },
  { id: 'context', label: 'Tes sources', component: ContextScene },
  { id: 'approval', label: 'Tes décisions', component: ApprovalScene },
  { id: 'voice', label: 'La voix', component: VoiceScene },
  { id: 'memory', label: 'La mémoire', component: MemoryScene },
  { id: 'meetings', label: 'Les réunions', component: MeetingScene },
  { id: 'routines', label: 'Le suivi', component: RoutineScene },
  { id: 'skills', label: 'Tes outils', component: SkillScene },
  { id: 'radio', label: 'Ta radio', component: RadioScene },
];
export const FEATURE_CUTS = score.cues.map(cue => cue.frame);
// Canonical interaction/result frames, retimed by at most eight real frames
// onto measured attacks while preserving a continuous, monotone scene clock.
const ACTION_FRAMES = [
  [145, 168, 300], [130, 218, 272], [87, 220, 238, 368, 393],
  [53, 198, 218, 275], [106, 192, 334], [164, 230],
  [133, 169, 218, 286], [82, 130, 166, 209, 246, 309], [91, 112, 274, 431],
];

function Opening({ frame }: { frame: number }) {
  const badges = [
    { icon: CalendarDays, name: 'Ta journée', x: 1115, y: 160 },
    { icon: Mail, name: 'Tes e-mails', x: 1535, y: 285 },
    { icon: Mic, name: 'La voix', x: 1040, y: 440 },
    { icon: Brain, name: 'La mémoire', x: 1530, y: 570 },
    { icon: FileText, name: 'Tes réunions', x: 1100, y: 770 },
    { icon: Radio, name: 'Ta radio', x: 1530, y: 840 },
  ];
  const title = uiSpring(frame, 9);
  const out = ease(frame, 210, 243);
  return <AbsoluteFill className="feature-opening">
    <div className="feature-opening-light" />
    <div className="feature-opening-brand"><FilmBrand size={61} /></div>
    <div className="feature-opening-copy" style={{ transform: `translateY(${(1-title)*85}px)`, opacity: title * (1-out) }}>
      <h1>Un assistant.<br />Tout ton quotidien.</h1>
      <p>Comprendre. Préparer. Agir avec toi.</p>
    </div>
    <div className="feature-opening-bip" style={{ opacity: uiSpring(frame, 15), transform: `translateY(${(1-uiSpring(frame,15))*110}px) scale(${1-out*.12})` }}><FilmBip frame={frame} size={390} expression="joy" gazeX={-.35} /></div>
    {badges.map(({ icon: Icon, name, x, y }, index) => {
      const enter = uiSpring(frame, 20 + index * 10);
      return <div key={name} className="feature-orbit-label" style={{ left:x, top:y, opacity:enter*(1-out), transform:`translateY(${(1-enter)*75}px) rotate(${(1-enter)*(index%2?8:-8)}deg)` }}><Icon size={30} /><span>{name}</span></div>;
    })}
    <div className="feature-opening-proof" style={{ opacity: ease(frame, 85, 115) * (1-out) }}><ShieldCheck size={24} />LIA garde le fil. Tu gardes la main.</div>
  </AbsoluteFill>;
}

function Closing({ frame }: { frame: number }) {
  const enter = uiSpring(frame, 0);
  return <AbsoluteFill className="feature-closing">
    <div className="feature-closing-light" />
    <div className="feature-closing-copy" style={{ opacity:enter, transform:`translateY(${(1-enter)*60}px)` }}>
      <FilmBrand size={102} />
      <h2>Ton quotidien.<br />Avec LIA.</h2>
      <div className="feature-cta">Découvrir LIA <ArrowRight size={29} /></div>
      <p>Conçu en France · Open source · Auto-hébergeable</p>
    </div>
    <div className="feature-closing-bip" style={{ transform:`translateX(${(1-enter)*170}px)` }}><FilmBip frame={frame+280} size={480} expression="joy" gazeX={-.1} /></div>
    <div className="feature-closing-signature"><span>Tu gardes la main.</span><ShieldCheck size={26} /></div>
  </AbsoluteFill>;
}

function Chapter({ index, duration }: { index: number; duration: number }) {
  const frame = useCurrentFrame();
  const Scene = FEATURE_CHAPTERS[index].component;
  const nativeFrame = frameForScene(frame, duration, FEATURE_CUTS[index + 1], score.transients.onsetTimesSeconds, ACTION_FRAMES[index]);
  return <AbsoluteFill className={`feature-chapter feature-chapter--${FEATURE_CHAPTERS[index].id}`}>
    <Scene frame={nativeFrame} />
  </AbsoluteFill>;
}

function Cut({ at, index }: { at: number; index: number }) {
  const frame = useCurrentFrame();
  const distance = frame - at;
  if (Math.abs(distance) > 18) return null;
  const t = (distance + 18) / 36;
  if (index % 3 === 1) {
    const r = Math.abs(t - .5) * 2;
    return <AbsoluteFill className="feature-cut feature-cut--iris" style={{ clipPath:`circle(${(1-r)*130}% at 86% 62%)` }} />;
  }
  return <AbsoluteFill className="feature-cut" style={{ transform:`translateX(${(t < .5 ? -1 + t*2 : (t-.5)*2)*2100}px) skewX(${index%2?-7:7}deg)` }} />;
}

export function FeatureFilm({ withAudio = true }: { withAudio?: boolean }) {
  const frame = useCurrentFrame();
  const chapterIndex = FEATURE_CUTS.findIndex((cut, i) => i>0 && frame < cut)-2;
  return <AbsoluteFill className="lia-feature-film">
    <Sequence from={0} durationInFrames={FEATURE_CUTS[1]}><Opening frame={frame} /></Sequence>
    {FEATURE_CHAPTERS.map((chapter,index) => {
      const from=FEATURE_CUTS[index+1], to=FEATURE_CUTS[index+2];
      return <Sequence key={chapter.id} from={from} durationInFrames={to-from}><Chapter index={index} duration={to-from} /></Sequence>;
    })}
    <Sequence from={FEATURE_CUTS[10]} durationInFrames={4800-FEATURE_CUTS[10]}><Closing frame={frame-FEATURE_CUTS[10]} /></Sequence>
    {frame>=FEATURE_CUTS[1] && frame<FEATURE_CUTS[10] && <>
      {frame<FEATURE_CUTS[7] && <div className="feature-timeline">{FEATURE_CHAPTERS.map((chapter,index)=><div key={chapter.id} className={index===chapterIndex?'active':''}><span />{chapter.label}</div>)}</div>}
      <div className="feature-progress"><span style={{width:`${frame/4800*100}%`}} /></div>
    </>}
    {FEATURE_CUTS.slice(1,-1).map((at,index)=><Cut key={at} at={at} index={index} />)}
    <div className="feature-fiction">Démonstration scénarisée · données fictives · traitements condensés</div>
    {withAudio && <Audio src={staticFile('audio/feature-film/lia-feature-film-80s.wav')} />}
  </AbsoluteFill>;
}
