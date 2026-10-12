import {bundle} from '@remotion/bundler';
import {getCompositions,renderStill} from '@remotion/renderer';
import {mkdir,mkdtemp,readFile,writeFile} from 'node:fs/promises';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {PRESENTATION_CHAPTERS,PRESENTATION_FOCUS_PLAN,PRESENTATION_REVISION} from '../src/presentation-plan.ts';
import {timePresentation} from '../src/presentation-timing.ts';

const project=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const root=path.resolve(project,'../..');
const output=path.resolve(root,`exports/lia-motion/review-${PRESENTATION_REVISION}`);
await mkdir(output,{recursive:true});
const bundleDir=await mkdtemp(path.resolve(project,`build/review-${PRESENTATION_REVISION}-`));
const serveUrl=await bundle({entryPoint:path.resolve(project,'src/index.ts'),publicDir:path.resolve(project,'public'),outDir:bundleDir,webpackOverride:config=>({...config,cache:false,resolve:{...config.resolve,alias:{...config.resolve?.alias,'@':path.resolve(root,'apps/web/src')}}})});
const compositions=await getCompositions(serveUrl,{browserExecutable:process.env.REMOTION_BROWSER_EXECUTABLE});
const mode=process.argv[2]??'all';
const music=JSON.parse(await readFile(path.resolve(project,'src/music-film.json'),'utf8'));
const full=compositions.find(item=>item.id==='LIA-Full');
if(!full)throw new Error('Current full film missing');
const timeline=timePresentation(PRESENTATION_CHAPTERS,music.beats,30);
const reviewed=[];
const offsets={intro:2.5,avatars:13.2,appearance:4.5,'briefing-radio':5.8,notifications:3.3,memory:7.4,context:7.8,knowledge:4,'voice-meetings':5.5,workboard:4,creation:4,routines:9.8,ecosystem:7.5,administration:7.5,mobile:3.5,control:6.5,finale:2.7};
if(mode!=='focus')for(const entry of timeline){
  const frame=entry.start+Math.round(Math.min(offsets[entry.chapter.kind]??3.5,entry.duration/30-.3)*30);
  const target=path.resolve(output,`main-${String(entry.index+1).padStart(2,'0')}.png`);
  await renderStill({composition:full,serveUrl,frame,output:target,imageFormat:'png',inputProps:{withAudio:false},logLevel:'error'});
  reviewed.push({id:entry.chapter.id,frame,file:path.basename(target)});
  console.log(`Reviewed ${entry.chapter.id}`);
  const extra = entry.chapter.kind==='avatars' ? [['lumo',3.4]] : entry.chapter.kind==='mobile' ? [['install',7.5]] : [];
  for(const [label,seconds] of extra) {
    const extraFrame=entry.start+Math.round(Number(seconds)*30);
    const extraTarget=path.resolve(output,`main-${String(entry.index+1).padStart(2,'0')}-${label}.png`);
    await renderStill({composition:full,serveUrl,frame:extraFrame,output:extraTarget,imageFormat:'png',inputProps:{withAudio:false},logLevel:'error'});
    reviewed.push({id:`${entry.chapter.id}-${label}`,frame:extraFrame,file:path.basename(extraTarget)});
  }
}
if(mode!=='main')for(const focus of PRESENTATION_FOCUS_PLAN){
  const composition=compositions.find(item=>item.id===`LIA-${focus.id}`);
  if(!composition)throw new Error(`Missing ${focus.id}`);
  const frame=Math.round((focus.variant==='mobile'?8:4)*30);
  const target=path.resolve(output,`${focus.id}.png`);
  await renderStill({composition,serveUrl,frame,output:target,imageFormat:'png',inputProps:{withAudio:false},logLevel:'error'});
  reviewed.push({id:focus.id,frame,file:path.basename(target)});
  console.log(`Reviewed ${focus.id}`);
}
await writeFile(path.resolve(output,`review-${mode}.json`),JSON.stringify({scope:'Rendered frames for visual review; editorial reading remains separate',reviewed},null,2)+'\n');
