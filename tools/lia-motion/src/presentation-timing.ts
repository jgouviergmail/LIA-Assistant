import type { PresentationChapter } from './presentation-plan';

export type TimedPresentationChapter={chapter:PresentationChapter;index:number;start:number;duration:number};
export const MAX_MUSICAL_CUT_SHIFT_SECONDS=.45;

/** Musical cuts may move by at most 450ms; total length and usable holds remain fixed. */
export function timePresentation(chapters:readonly PresentationChapter[],beats:readonly number[],fps:number):TimedPresentationChapter[] {
  if(!Number.isInteger(fps)||fps<1||!chapters.length)throw new Error('Invalid film timeline');
  if(chapters.some(chapter=>!Number.isFinite(chapter.durationSeconds)||chapter.durationSeconds<2))throw new Error('A chapter needs a readable duration');
  if(beats.some((beat,index)=>!Number.isFinite(beat)||beat<0||(index>0&&beat<=beats[index-1])))throw new Error('Invalid measured beat map');
  const total=Math.round(chapters.reduce((sum,chapter)=>sum+chapter.durationSeconds,0)*fps);
  let expected=0;
  let start=0;
  return chapters.map((chapter,index)=>{
    expected+=chapter.durationSeconds;
    let end=Math.round(expected*fps);
    if(index<chapters.length-1){
      const closest=beats.reduce((candidate,beat)=>Math.abs(beat-expected)<Math.abs(candidate-expected)?beat:candidate,expected+MAX_MUSICAL_CUT_SHIFT_SECONDS+.001);
      if(Math.abs(closest-expected)<=MAX_MUSICAL_CUT_SHIFT_SECONDS)end=Math.round(closest*fps);
    }else end=total;
    if(end-start<fps)throw new Error('A musical cut consumed a chapter');
    const duration=end-start;
    const timed={chapter:{...chapter,durationSeconds:duration/fps},index,start,duration};
    start=end;
    return timed;
  });
}
