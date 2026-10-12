import React, { type CSSProperties, type ReactNode, createContext, useContext, useEffect, useLayoutEffect, useRef, useState } from 'react';
import { AbsoluteFill, Audio, Sequence, staticFile, useCurrentFrame, useVideoConfig, delayRender, continueRender, cancelRender } from 'remotion';
import { FeatureScreen, FEATURE_SCREEN_FOCUSES, FEATURE_SCREEN_METADATA, REMINDER_DEMO_TRIGGER_SECONDS, type FeatureScreenDetail, type FeatureScreenKind } from './FeatureScreens';
import { NativeWindow } from './ProductStory';
import { NativeComposer } from './FaithfulUi';
import { StoryMascot } from './StoryMascot';
import { AvatarDemonstration } from './AvatarDemonstration';
import { StoryLandingBackdrop } from './StoryLandingBackdrop';
import { easeProgress } from './product-story-timing';
import {
  PRESENTATION_CHAPTERS, PRESENTATION_NOTE, PRESENTATION_NATIVE_SHOTS, PRESENTATION_FOCUS_SHOTS,
  type PresentationChapter, type PresentationFocus, type PresentationTitle,
} from './presentation-plan';
import { createBeatTrack } from '../../../apps/web/src/lib/landing/beat-sync';
import { timePresentation } from './presentation-timing';
import { fixedWindow, fixedFocus, nativeShotAt, focusOpacity, NATIVE_MOBILE_RECT, assertFixedGeometry, heldNativeStateFrame, type SourceRect } from './presentation-geometry';
import music from './music-film.json';
import './presentation-film.css';

export interface PresentationFilmProps {
  chapters?: readonly PresentationChapter[];
  focus?: PresentationFocus;
  withAudio?: boolean;
  /** Emits measured DOM records for the offline geometry verifier only. */
  verifyGeometry?: boolean;
}

const GeometryAuditContext=createContext(false);

const beatTrack = createBeatTrack({version:1, beats:music.beatEntries.map(entry => [Number(entry[0]),Number(entry[1]),Boolean(entry[2])])});
const clamp = (value:number) => Math.max(0,Math.min(1,value));
const focusTable=FEATURE_SCREEN_FOCUSES as unknown as Record<string,Partial<Record<string,readonly SourceRect[]>>>;

export function filmFrames(chapters:readonly PresentationChapter[],fps:number) {
  return chapters.reduce((sum,chapter)=>sum+Math.round(chapter.durationSeconds*fps),0);
}

/** All editorial positions are fixed. Only opacity can reveal text. */
function EditorialCopy({chapter,frame,fps,full=false}:{chapter:PresentationChapter;frame:number;fps:number;full?:boolean}) {
  const seconds=frame/fps;
  const horizontal=!full&&['top','full'].includes(chapter.layout);
  const longest=Math.max(...chapter.title.map(line=>line.length));
  const maximum=full?98:horizontal?76:chapter.layout==='right'?76:longest>23?69:longest>18?77:88;
  const available=full?835:horizontal?1340:chapter.layout==='right'?570:596;
  const spacing=full?-4.8:horizontal?-3.7:chapter.layout==='right'?-3.6:-4.2;
  const [fontSize,setFontSize]=useState(maximum);
  const [fontHandle]=useState(()=>delayRender('Measure editorial title with native Inter'));
  useEffect(()=>{
    let mounted=true;
    document.fonts.load(`690 ${maximum}px "Lia Story Inter"`).then(()=>{
      const context=document.createElement('canvas').getContext('2d');
      if(!context)throw new Error('Title measurement unavailable');
      context.font=`690 ${maximum}px "Lia Story Inter"`;
      const widths=chapter.title.map(line=>context.measureText(line).width);
      const raw=horizontal?widths.reduce((a,b)=>a+b,0):Math.max(...widths);
      const letters=horizontal?chapter.title.reduce((sum,line)=>sum+line.length-1,0):chapter.title[widths.indexOf(Math.max(...widths))].length-1;
      const gap=horizontal?(chapter.title.length-1)*22:0;
      const fitted=Math.min(maximum,Math.floor((available-4-gap-spacing*letters)/raw*maximum));
      if(mounted)setFontSize(fitted);
    }).catch(error=>cancelRender(error)).finally(()=>continueRender(fontHandle));
    return ()=>{mounted=false;};
  },[chapter.title,maximum,available,spacing,horizontal,fontHandle]);
  return <div className={`film-copy film-copy-${chapter.layout} ${full?'film-copy-signature':''}`} style={{'--film-accent':chapter.accent,opacity:easeProgress(seconds,.1,.38)} as CSSProperties}>
    <h1 style={{fontSize}}>{chapter.title.map((line,index)=><span key={line} style={{opacity:easeProgress(seconds,.12+index*.1,.4+index*.1)}}>{line}</span>)}</h1>
    <p style={{opacity:easeProgress(seconds,.5,.8)}}>{chapter.detail}</p>
  </div>;
}

/** This frame guard reads actual DOM bounds, also in a scaled Studio preview.
 * A future decorative transform or reflow cannot silently move a capture. */
function FixedCapture({x,y,width=1440,height=960,scale=1,opacity=1,frame,className='film-feature-window',target,children}:{
  x:number;y:number;width?:number;height?:number;scale?:number;opacity?:number;frame:number;
  className?:string;target?:string;children:ReactNode;
}) {
  const ref=useRef<HTMLDivElement>(null);
  const audit=useContext(GeometryAuditContext);
  const expected={x,y,width:width*scale,height:height*scale};
  useLayoutEffect(()=>{
    const handle=delayRender(`Verify native capture geometry at ${frame}`);
    let completed=false,animationFrame=0;
    const inspect=()=>{
      const element=ref.current,root=element?.closest('.presentation-film');
      if(!element||!root){cancelRender(new Error('Native geometry reference is absent'));return;}
      const canvas=root.getBoundingClientRect(),actual=element.getBoundingClientRect();
      const sx=canvas.width/1920,sy=canvas.height/1080;
      // Remotion assigns its composition size after the first React commit.
      if(sx<=0||sy<=0){animationFrame=requestAnimationFrame(inspect);return;}
      try{
        const measured={x:(actual.left-canvas.left)/sx,y:(actual.top-canvas.top)/sy,width:actual.width/sx,height:actual.height/sy};
        assertFixedGeometry(expected,measured);
        if(audit)console.log(`LIA_GEOMETRY:${JSON.stringify({frame,className,target:target??null,expected,measured})}`);
      }catch(error){cancelRender(error as Error);}
      finally{completed=true;continueRender(handle);}
    };
    inspect();
    return ()=>{cancelAnimationFrame(animationFrame);if(!completed)continueRender(handle);};
  });
  return <div ref={ref} className={className} data-motion-role={target?'native-focus':'screen'} data-native-focus={target}
    data-fixed-geometry={JSON.stringify(expected)} data-verified-frame={frame}
    style={{left:x,top:y,width,height,opacity,transform:`scale(${scale})`,transformOrigin:'0 0'}}>{children}</div>;
}

function kindForDetail(detail:FeatureScreenDetail,preferred:FeatureScreenKind):FeatureScreenKind {
  if(FEATURE_SCREEN_METADATA[preferred]?.[detail])return preferred;
  const match=(Object.keys(FEATURE_SCREEN_METADATA) as FeatureScreenKind[]).find(kind=>FEATURE_SCREEN_METADATA[kind][detail]);
  if(!match)throw new Error(`No faithful UI for ${detail}`);
  return match;
}

function NativeCrop({rect,chapter,frame,opacity,target,children}:{rect:SourceRect;chapter:PresentationChapter;frame:number;opacity:number;target:string;children:ReactNode}) {
  const pose=fixedFocus(rect,chapter.layout);
  return <FixedCapture x={pose.x} y={pose.y} width={rect.width} height={rect.height} scale={pose.scale} opacity={opacity}
    frame={frame} className="film-native-crop" target={target}>
    <div className="film-crop-source" style={{left:-rect.x,top:-rect.y,width:1440,height:960}}>{children}</div>
  </FixedCapture>;
}

function FeatureObjects({chapter,frame,fps,focus,startTime=0}:{chapter:PresentationChapter;frame:number;fps:number;focus?:PresentationFocus;startTime?:number}) {
  const preferred=chapter.kind as FeatureScreenKind;
  const shots=focus?PRESENTATION_FOCUS_SHOTS[focus.variant]??PRESENTATION_NATIVE_SHOTS[preferred]:PRESENTATION_NATIVE_SHOTS[preferred];
  const active=nativeShotAt(shots,frame,fps,chapter.durationSeconds,startTime,music.beats);
  const detail=active.shot.detail as FeatureScreenDetail;
  const kind=kindForDetail(detail,preferred);
  const targetIndex=active.shot.focusTarget;
  const rect=targetIndex===undefined?undefined:focusTable[kind]?.[detail]?.[targetIndex];
  if(targetIndex!==undefined&&!rect)throw new Error(`Missing declared native focus ${kind}/${detail}/${targetIndex}`);
  const highlight=focusOpacity(active.localSeconds,active.duration,Boolean(rect),active.shot.focusFromSeconds);
  const stateFrame=heldNativeStateFrame(detail,targetIndex,fps);
  const pose=fixedWindow(chapter.layout);
  const source=<div data-native-still-frame={stateFrame}><FeatureScreen kind={kind} detail={detail} frame={stateFrame} fps={fps} withBackdrop={false}/></div>;
  return <>
    <FixedCapture {...pose} width={1440} height={960} frame={frame} opacity={easeProgress(frame/fps,0,.25)*(1-highlight*.55)}>{source}</FixedCapture>
    {rect&&highlight>0?<NativeCrop rect={rect} chapter={chapter} frame={frame} opacity={highlight} target={`${kind}/${detail}/${targetIndex}`}>{source}</NativeCrop>:null}
  </>;
}

function NotificationObjects({chapter,frame,fps}:{chapter:PresentationChapter;frame:number;fps:number}) {
  const seconds=frame/fps;
  const rect=focusTable.notifications.reminder?.[1];
  if(!rect)throw new Error('Missing native notification focus');
  const highlight=seconds>=REMINDER_DEMO_TRIGGER_SECONDS?easeProgress(seconds,REMINDER_DEMO_TRIGGER_SECONDS+.12,REMINDER_DEMO_TRIGGER_SECONDS+.36):0;
  const pose=fixedWindow(chapter.layout);
  const source=<FeatureScreen kind="notifications" detail="reminder" frame={frame} fps={fps} withBackdrop={false} reminderToastOpacity={1}/>;
  return <><FixedCapture {...pose} width={1440} height={960} frame={frame} opacity={easeProgress(seconds,0,.25)*(1-highlight*.55)}>{source}</FixedCapture>
    {highlight>0?<NativeCrop rect={rect} chapter={chapter} frame={frame} opacity={highlight} target="notifications/reminder/1">{source}</NativeCrop>:null}</>;
}

const CONTEXT_TARGETS={
  sources:'.story-native-source-list', dates:'.story-native-warning',
  approval:'.story-native-inline-approval', result:'.story-native-result', costs:'.story-native-usage',
} as const;

/** The context uses frozen native states. Its target is measured from the
 * actual DOM element, rather than guessed coordinates or a rebuilt small DL. */
function MeasuredNativeCrop({chapter,frame,parent,selector,opacity,children}:{
  chapter:PresentationChapter;frame:number;parent:React.RefObject<HTMLDivElement|null>;selector:string;opacity:number;children:ReactNode;
}) {
  const [rect,setRect]=useState<SourceRect|null>(null);
  const [handle]=useState(()=>delayRender(`Measure native focus ${selector}`));
  useEffect(()=>{
    let mounted=true;
    document.fonts.ready.then(async()=>{
      const window=parent.current;
      const element=window?.querySelector(selector);
      if(!window||!element)throw new Error(`Missing actual native focus ${selector}`);
      while(window.getBoundingClientRect().width<=0){
        await new Promise<void>(resolve=>requestAnimationFrame(()=>resolve()));
        if(!mounted)return;
      }
      const boundary=window.getBoundingClientRect(),target=element.getBoundingClientRect();
      const scale=boundary.width/1440;
      const measured={x:(target.left-boundary.left)/scale,y:(target.top-boundary.top)/scale,width:target.width/scale,height:target.height/scale};
      if(mounted)setRect(measured);
    }).catch(error=>cancelRender(error)).finally(()=>continueRender(handle));
    return ()=>{mounted=false;};
  },[parent,selector,handle]);
  return rect?<NativeCrop rect={rect} chapter={chapter} frame={frame} opacity={opacity} target={selector}>{children}</NativeCrop>:null;
}

function ContextObjects({chapter,frame,fps,control=false}:{chapter:PresentationChapter;frame:number;fps:number;control?:boolean}) {
  const seconds=frame/fps,length=chapter.durationSeconds;
  const progress=seconds/length;
  const comparison=control?(progress>=.84?'research':progress>=.68?'result':'approval'):'research';
  const nativeSeconds=comparison==='research'?4:comparison==='approval'?14:20.52;
  const pose=fixedWindow(chapter.layout);
  const parent=useRef<HTMLDivElement>(null);
  const budget=control&&length>13&&seconds>=length-4;
  const target=budget?null:!control?(progress>=.66?'dates':'sources'):progress>=.84?'costs':progress>=.68?'result':'approval';
  const selector=target?CONTEXT_TARGETS[target]:null;
  const targetStart=!control?(progress>=.66?length*.66:0):progress>=.84?length*.84:progress>=.68?length*.68:0;
  const opacity=selector?easeProgress(seconds,targetStart+.5,targetStart+.74):0;
  // frame=0 keeps the captured landing background and caret deterministic.
  const source=<NativeWindow frame={0} seconds={nativeSeconds} comparison={comparison}/>;
  const budgetSource=<FeatureScreen kind="ecosystem" detail="costs" frame={0} fps={fps} withBackdrop={false}/>;
  return <>
    <FixedCapture {...pose} width={1440} height={960} frame={frame} opacity={easeProgress(seconds,0,.25)*(1-opacity*.55)}>
      <div ref={parent} className="film-native-state">{budget?budgetSource:source}</div>
    </FixedCapture>
    {selector&&opacity>0?<MeasuredNativeCrop key={`${comparison}/${selector}`} chapter={chapter} frame={frame} parent={parent} selector={selector} opacity={opacity}>{source}</MeasuredNativeCrop>:null}
    {control&&target==='costs'?<p className="film-focus-label">Coût de la recherche de démonstration</p>:null}
  </>;
}

function MobileObjects({chapter,frame,fps,startTime=0}:{chapter:PresentationChapter;frame:number;fps:number;startTime?:number}) {
  const active=nativeShotAt(PRESENTATION_NATIVE_SHOTS.mobile,frame,fps,chapter.durationSeconds,startTime,music.beats);
  const detail=active.shot.detail as FeatureScreenDetail;
  const rect=NATIVE_MOBILE_RECT;
  const source=<FeatureScreen kind="mobile" detail={detail} frame={Math.round(active.localSeconds*fps)} fps={fps} withBackdrop={false}/>;
  const target=active.shot.focusTarget;
  const installer=target===undefined?null:focusTable.mobile?.[detail]?.[target];
  if(target!==undefined&&!installer)throw new Error('Missing actual PWA install focus');
  // A short, explicit Installer label gets a stable focus even in the 6s landing chapter.
  const highlight=installer?easeProgress(active.localSeconds,.85,1.1)*(1-easeProgress(active.localSeconds,active.duration-.3,active.duration)):0;
  return <><FixedCapture x={1090} y={154} width={rect.width} height={rect.height} scale={.92} opacity={easeProgress(frame/fps,0,.25)*(1-highlight*.55)} frame={frame} className="film-mobile">
    <div className="film-crop-source" style={{left:-rect.x,top:-rect.y,width:1440,height:960}}>{source}</div>
  </FixedCapture>{installer&&highlight>0?<NativeCrop rect={installer} chapter={chapter} frame={frame} opacity={highlight} target={`mobile/${detail}/${target}`}>{source}</NativeCrop>:null}</>;
}

function chapterUse(chapter:PresentationChapter):string {
  if(chapter.kind==='mobile')return 'Partout avec toi';
  if(['avatars','appearance','briefing-radio','notifications','memory'].includes(chapter.kind))return 'Ta journée, selon tes choix';
  if(['context','knowledge','voice-meetings'].includes(chapter.kind))return 'Retrouve les informations utiles';
  if(['administration','control'].includes(chapter.kind))return 'Tes accès, tes décisions';
  return 'Prépare les actions, retrouve leur suivi';
}

function Chapter({chapter,frame,fps,focus,startTime}:{chapter:PresentationChapter;frame:number;fps:number;focus?:PresentationFocus;startTime:number}) {
  const s=frame/fps;
  const isSignature=chapter.kind==='intro'||chapter.kind==='finale';
  const feature=!isSignature&&!['avatars','notifications','context','control','mobile'].includes(chapter.kind);
  return <AbsoluteFill className={`film-chapter film-chapter-${chapter.kind}`}>
    <EditorialCopy chapter={chapter} frame={frame} fps={fps} full={isSignature}/>
    {chapter.kind==='intro'?<div className="film-intro-composer" style={{opacity:easeProgress(s,1.4,1.7)}}><NativeComposer text={'Qu’ai-je prévu aujourd’hui ?'.slice(0,Math.floor(clamp((s-1.6)/1.1)*27))}/></div>:null}
    {feature?<FeatureObjects chapter={chapter} frame={frame} fps={fps} focus={focus} startTime={startTime}/>:null}
    {chapter.kind==='notifications'?<NotificationObjects chapter={chapter} frame={frame} fps={fps}/>:null}
    {chapter.kind==='avatars'?<div className="film-avatar-demonstration" style={{left:chapter.layout==='right'?121:770,top:190,opacity:easeProgress(s,0,.25)}}><AvatarDemonstration frame={frame} fps={fps} width={1040} height={700} durationSeconds={chapter.durationSeconds} mode="all"/></div>:null}
    {chapter.kind==='context'||chapter.kind==='control'?<ContextObjects chapter={chapter} frame={frame} fps={fps} control={chapter.kind==='control'}/>:null}
    {chapter.kind==='mobile'?<MobileObjects chapter={chapter} frame={frame} fps={fps} startTime={startTime}/>:null}
    {!isSignature&&!focus?<div className="film-scene-mark">{chapterUse(chapter)}</div>:null}
    {focus?.availability==='experimental'?<p className="film-scene-note">Option expérimentale · compte et crédits Simli personnels.</p>:focus?.availability==='admin-only'?<p className="film-scene-note">Réglages réservés à l’administrateur de l’instance.</p>:chapter.kind==='mobile'?<p className="film-scene-note">Installation selon ton navigateur.</p>:null}
    {chapter.kind==='finale'?<p className="film-music-credit">{music.attribution}</p>:null}
  </AbsoluteFill>;
}

export function focusChapters(focus:PresentationFocus):readonly PresentationChapter[] {
  const kind=focus.variant==='conversation'?'context':focus.variant==='control'?'control':focus.kind;
  return [{...focus,id:focus.id,durationSeconds:focus.durationSeconds-4,direction:'Vue native fixe et focus explicitement associé à son élément.',evidence:[],kind,
    layout:kind==='context'||kind==='control'?'top':focus.layout},
    {...PRESENTATION_CHAPTERS[PRESENTATION_CHAPTERS.length-1],durationSeconds:4}];
}

export function PresentationFilm({chapters=PRESENTATION_CHAPTERS,focus,withAudio=true,verifyGeometry=false}:PresentationFilmProps) {
  const frame=useCurrentFrame();
  const {fps,durationInFrames}=useVideoConfig();
  const selected=focus?focusChapters(focus):chapters;
  const timed=timePresentation(selected,music.beats,fps);
  const active=timed.find(entry=>frame>=entry.start&&frame<entry.start+entry.duration)??timed[timed.length-1];
  return <GeometryAuditContext.Provider value={verifyGeometry}><AbsoluteFill className="presentation-film">
    <style>{`@font-face{font-family:'Lia Story Inter';src:url('${staticFile('fonts/Inter-Variable.woff2')}') format('woff2');font-weight:100 900;font-display:block;}`}</style>
    <StoryLandingBackdrop width={1920} height={1080} frame={frame} fps={fps} beat={beatTrack.intensityAt(frame/fps)}/>
    {withAudio?<Audio src={staticFile(music.audio)} volume={audioFrame=>easeProgress(audioFrame/fps,0,.35)*(1-easeProgress(audioFrame/fps,durationInFrames/fps-1.4,durationInFrames/fps))*.85}/>:null}
    <div className="film-brand">LIA</div>
    {timed.map(({chapter,start,duration})=><Sequence key={chapter.id} from={start} durationInFrames={duration} layout="none"><Chapter chapter={chapter} frame={frame-start} fps={fps} focus={focus} startTime={start/fps}/></Sequence>)}
    <PersistentMascot chapter={active.chapter} frame={frame-active.start} fps={fps} first={active.index===0}/>
    {active.chapter.kind!=='finale'?<div className="film-demo-note">{PRESENTATION_NOTE}</div>:null}
    <div className="film-time-line"><span style={{width:`${frame/Math.max(1,durationInFrames-1)*100}%`}}/></div>
  </AbsoluteFill></GeometryAuditContext.Provider>;
}

/** BIP changes expression, not the capture geometry or its own carrier position. */
function PersistentMascot({chapter,frame,fps,first}:{chapter:PresentationChapter;frame:number;fps:number;first:boolean}) {
  const signature=chapter.kind==='intro'||chapter.kind==='finale';
  const right=chapter.layout==='right';
  const top=chapter.layout==='top'||chapter.layout==='full';
  const x=signature?1222:right?1420:top?1478:150;
  const y=signature?322:chapter.kind==='avatars'?660:top?749:705;
  const size=signature?430:top?245:300;
  const act=chapter.kind==='finale'?'finale':chapter.kind==='control'?'approval':chapter.kind==='context'?'clarity':'context';
  const screenSide=x>960?'left':'right';
  const opacity=chapter.kind==='avatars'?easeProgress(frame/fps,chapter.durationSeconds*.5,chapter.durationSeconds*.5+.25):first?easeProgress(frame/fps,.1,.45):1;
  return <><div className="film-mascot-carrier" style={{left:x,top:y,opacity}}><StoryMascot frame={frame} fps={fps} size={size} act={act} screenSide={screenSide} previousScreenSide={screenSide} turnProgress={1} gazeTarget={[screenSide==='left'?-.78:.78,signature?-.05:-.42]} lookAtAudience={signature} audienceGlances={chapter.kind==='avatars'?[]:chapter.durationSeconds>8?[chapter.durationSeconds*.74]:[]}/></div>{chapter.kind==='avatars'?<div className="film-mascot-name" style={{left:x,top:y+size+8,opacity}}>BIP · ta mascotte</div>:null}</>;
}
