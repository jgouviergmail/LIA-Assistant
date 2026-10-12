import {bundle} from '@remotion/bundler';
import {getCompositions,openBrowser,renderStill} from '@remotion/renderer';
import {mkdir,mkdtemp,readFile,writeFile} from 'node:fs/promises';
import {createHash} from 'node:crypto';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
import {PRESENTATION_CHAPTERS,PRESENTATION_LANDING_CHAPTERS,PRESENTATION_FOCUS_PLAN,PRESENTATION_REVISION} from '../src/presentation-plan.ts';
import {timePresentation} from '../src/presentation-timing.ts';

const project=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const root=path.resolve(project,'../..');
const mode=process.argv[2]??'all';
if(!['all','critical'].includes(mode))throw new Error('Use all or critical');
const music=JSON.parse(await readFile(path.resolve(project,'src/music-film.json'),'utf8'));
await mkdir(path.resolve(project,'build'),{recursive:true});
const directory=await mkdtemp(path.resolve(project,`build/geometry-${PRESENTATION_REVISION}-`));
const sourcePaths=['PresentationFilm.tsx','presentation-plan.ts','presentation-geometry.ts','presentation-film.css','FeatureScreens.tsx','feature-screens.css','AvatarDemonstration.tsx','FaithfulUi.tsx','ProductStory.tsx'];
const fingerprints=await Promise.all(sourcePaths.map(async name=>({path:`src/${name}`,sha256:createHash('sha256').update(await readFile(path.resolve(project,'src',name))).digest('hex')})));
const serveUrl=await bundle({entryPoint:path.resolve(project,'src/index.ts'),publicDir:path.resolve(project,'public'),outDir:path.resolve(directory,'bundle'),webpackOverride:config=>({...config,cache:false,resolve:{...config.resolve,alias:{...config.resolve?.alias,'@':path.resolve(root,'apps/web/src')}}})});
const browser=await openBrowser('chrome',{browserExecutable:process.env.REMOTION_BROWSER_EXECUTABLE,logLevel:'error'});
const records=[];
try{
  const compositions=await getCompositions(serveUrl,{puppeteerInstance:browser,inputProps:{withAudio:false,verifyGeometry:true}});
  const tasks=[];
  const critical=new Set(['notifications','context','control','mobile']);
  for(const [id,chapters,fps] of [['LIA-Full',PRESENTATION_CHAPTERS,30],['LIA-Landing',PRESENTATION_LANDING_CHAPTERS,30],['LIA-Master25',PRESENTATION_CHAPTERS,25]]){
    for(const entry of timePresentation(chapters,music.beats,fps)){
      if(['intro','finale','avatars'].includes(entry.chapter.kind))continue;
      if((mode==='critical'||id!=='LIA-Full')&&!critical.has(entry.chapter.kind))continue;
      const offsets=[.8,entry.duration/fps*.5,entry.duration/fps-.65];
      for(const offset of offsets)tasks.push({id,scope:entry.chapter.id,frame:entry.start+Math.round(offset*fps)});
    }
  }
  const focusSelection=mode==='all'?PRESENTATION_FOCUS_PLAN:PRESENTATION_FOCUS_PLAN.filter(item=>['conversation','control','mobile','llm-config','relations','notifications','planning'].includes(item.variant));
  for(const focus of focusSelection){
    if(focus.kind==='avatars')continue;
    const body=focus.durationSeconds-4;
    for(const offset of [body*.3,body*.78])tasks.push({id:`LIA-${focus.id}`,scope:focus.id,frame:Math.round(offset*30)});
  }
  for(const task of tasks){
    const composition=compositions.find(item=>item.id===task.id);
    if(!composition)throw new Error(`Missing ${task.id}`);
    const measurements=[];
    const browserMessages=[];
    await renderStill({composition:{...composition,props:{...composition.props,withAudio:false,verifyGeometry:true}},serveUrl,puppeteerInstance:browser,frame:task.frame,output:null,imageFormat:'jpeg',jpegQuality:30,inputProps:{withAudio:false,verifyGeometry:true},logLevel:'error',onBrowserLog:log=>{
      if(browserMessages.length<12)browserMessages.push(log.text);
      if(log.text.startsWith('LIA_GEOMETRY:'))measurements.push(JSON.parse(log.text.slice('LIA_GEOMETRY:'.length)));
    }});
    if(!measurements.length)throw new Error(`No actual DOM capture measurements at ${task.id}/${task.frame}; browser logs ${JSON.stringify(browserMessages)}`);
    records.push({...task,measurements});
    if(records.length%10===0||records.length===tasks.length)console.log(`DOM geometry ${records.length}/${tasks.length}`);
  }
  const baseline=new Map();
  for(const record of records)for(const measurement of record.measurements){
    const key=JSON.stringify([record.id,record.scope,measurement.className,measurement.target]);
    const first=baseline.get(key);
    if(first){
      for(const field of ['x','y','width','height'])if(Math.abs(first[field]-measurement.measured[field])>.15)throw new Error(`Capture moved across sampled frames: ${key}/${field}`);
    }else baseline.set(key,measurement.measured);
  }
  for(const file of fingerprints){
    const current=createHash('sha256').update(await readFile(path.resolve(project,file.path))).digest('hex');
    if(current!==file.sha256)throw new Error(`Source changed during geometry verification: ${file.path}`);
  }
  const report={generation:PRESENTATION_REVISION,status:'passed',scope:'Sampled real Remotion DOM frames; fixed capture geometry and exact declared focus crops. No video, media replacement, provider action or full visual/editorial certification.',mode,frames:records.length,captureInstances:baseline.size,toleranceCanvasPixels:.15,fingerprints,records};
  await writeFile(path.resolve(directory,'geometry-review.json'),JSON.stringify(report,null,2)+'\n');
  console.log(`PASS ${records.length} sampled frames, ${baseline.size} fixed capture instances. Report ${path.resolve(directory,'geometry-review.json')}`);
}finally{
  await browser.close({silent:true});
}
