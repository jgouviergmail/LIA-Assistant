import type { PresentationLayout, PresentationNativeShot } from './presentation-plan';
import { MAX_MUSICAL_CUT_SHIFT_SECONDS } from './presentation-timing.ts';

export interface SourceRect { x:number; y:number; width:number; height:number; title?:string }
export interface FixedWindow { x:number; y:number; scale:number; width:number; height:number }
export const NATIVE_SCREEN_SIZE = {width:1440,height:960} as const;
export const NATIVE_MOBILE_RECT:SourceRect = {x:525,y:58,width:390,height:844};

/** Offline UI folds/modal are selected before the shot and then held. */
export function heldNativeStateFrame(detail:string,targetIndex:number|undefined,fps:number):number {
  const seconds=detail==='radio'?4:detail==='memories'?1:detail==='llm-config'&&targetIndex===0?4:0;
  return Math.round(seconds*fps);
}

/** No frame, effect, beat or focus argument can change the parent geometry. */
export function fixedWindow(layout:PresentationLayout):FixedWindow {
  const top=layout==='top'||layout==='full';
  const scale=top?.69:.72;
  return {x:top?348:layout==='right'?121:770,y:top?316:190,scale,
    width:NATIVE_SCREEN_SIZE.width*scale,height:NATIVE_SCREEN_SIZE.height*scale};
}

export function validateSourceRect(rect:SourceRect,source=NATIVE_SCREEN_SIZE):void {
  if (![rect.x,rect.y,rect.width,rect.height].every(Number.isFinite)
    ||rect.width<=0||rect.height<=0||rect.x<0||rect.y<0
    ||rect.x+rect.width>source.width+.01||rect.y+rect.height>source.height+.01) {
    throw new Error('A focus must name a finite rectangle inside its native screen');
  }
}

/** A focus is an exact crop of the same source-sized UI. It never reflows. */
export function fixedFocus(rect:SourceRect,layout:PresentationLayout) {
  validateSourceRect(rect);
  const window=fixedWindow(layout);
  const top=layout==='top'||layout==='full';
  const area=top?{x:256,y:402,width:1408,height:524}
    :{x:window.x+24,y:264,width:window.width-48,height:584};
  const scale=Math.min(1.9,area.width/rect.width,area.height/rect.height);
  const width=rect.width*scale,height=rect.height*scale;
  return {x:area.x+(area.width-width)/2,y:area.y+(area.height-height)/2,
    scale,width,height,sourceLeft:-rect.x*scale,sourceTop:-rect.y*scale};
}

/** Native detail cuts use measured beats. Geometry is independent from them. */
export function nativeShotAt(shots:readonly PresentationNativeShot[],frame:number,fps:number,
  durationSeconds:number,startSeconds:number,beats:readonly number[]) {
  if(!shots.length||!Number.isFinite(frame)||fps<=0||durationSeconds<=0)throw new Error('Invalid native shot');
  const boundaries=[0,...shots.slice(1).map((_,index)=>{
    const ideal=startSeconds+durationSeconds*(index+1)/shots.length;
    const nearest=beats.reduce((best,beat)=>Math.abs(beat-ideal)<Math.abs(best-ideal)?beat:best,
      ideal+MAX_MUSICAL_CUT_SHIFT_SECONDS+.001);
    return Math.round((Math.abs(nearest-ideal)<=MAX_MUSICAL_CUT_SHIFT_SECONDS?nearest-startSeconds:ideal-startSeconds)*fps)/fps;
  }),durationSeconds];
  const seconds=Math.max(0,Math.min(durationSeconds-1/fps,frame/fps));
  const next=boundaries.findIndex(end=>end>seconds);
  const index=Math.max(0,Math.min(shots.length-1,next-1));
  return {shot:shots[index],index,start:boundaries[index],end:boundaries[index+1],
    seconds,localSeconds:seconds-boundaries[index],duration:boundaries[index+1]-boundaries[index]};
}

/** A short scene holds the full UI rather than flashing an unreadable crop. */
export function focusOpacity(localSeconds:number,duration:number,hasDeclaredTarget:boolean,enter=1.2):number {
  if(!hasDeclaredTarget||duration<3.2)return 0;
  const exit=duration-.45,fade=.24;
  return Math.max(0,Math.min(1,(localSeconds-enter)/fade,(exit-localSeconds)/fade));
}

/** Used against real DOM bounds on every rendered frame, after preview scaling. */
export function assertFixedGeometry(expected:SourceRect,actual:SourceRect,tolerance=.15):void {
  for(const key of ['x','y','width','height'] as const){
    if(!Number.isFinite(actual[key])||Math.abs(actual[key]-expected[key])>tolerance){
      throw new Error(`Native geometry drift: ${key} expected ${expected[key]}, received ${actual[key]}`);
    }
  }
}
