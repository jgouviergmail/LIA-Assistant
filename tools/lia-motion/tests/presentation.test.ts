import assert from 'node:assert/strict';
import {readFile} from 'node:fs/promises';
import test from 'node:test';
import {PRESENTATION_CHAPTERS,PRESENTATION_LANDING_CHAPTERS,PRESENTATION_FOCUS_PLAN,FOCUS_FEATURE_OWNERS} from '../src/presentation-plan.ts';
import {timePresentation} from '../src/presentation-timing.ts';
import {REQUIRED_FEATURE_KEYS} from '../../../apps/web/src/components/landing/editorial/chapters-data.ts';

const music=JSON.parse(await readFile(new URL('../src/music-film.json',import.meta.url),'utf8'));

test('every canonical capability has exactly one editorial focus owner',()=>{
  const owned=PRESENTATION_FOCUS_PLAN.filter(item=>item.coverageOwner).flatMap(item=>item.features);
  assert.equal(new Set(owned).size,owned.length);
  assert.deepEqual([...owned].sort(),[...REQUIRED_FEATURE_KEYS].sort());
  assert.deepEqual(Object.keys(FOCUS_FEATURE_OWNERS).sort(),[...REQUIRED_FEATURE_KEYS].sort());
  assert.ok(PRESENTATION_FOCUS_PLAN.some(item=>item.availability==='experimental'&&!item.coverageOwner));
});

test('musical cuts keep the complete film contiguous at web and working-master rates',()=>{
  assert.ok(music.beats.every((beat:number,index:number)=>beat>=0&&beat<music.durationSeconds&&(!index||beat>music.beats[index-1])));
  for(const fps of [25,30]){
    const timeline=timePresentation(PRESENTATION_CHAPTERS,music.beats,fps);
    assert.equal(timeline[0].start,0);
    assert.equal(timeline.at(-1)!.start+timeline.at(-1)!.duration,158*fps);
    timeline.forEach((entry,index)=>{
      assert.ok(entry.duration>=2*fps);
      if(index)assert.equal(entry.start,timeline[index-1].start+timeline[index-1].duration);
      if(index<timeline.length-1){
        const end=(entry.start+entry.duration)/fps;
        assert.ok(music.beats.some((beat:number)=>Math.abs(beat-end)<=.5/fps));
      }
    });
    assert.deepEqual(timePresentation(PRESENTATION_CHAPTERS,music.beats,fps),timeline);
    const landing=timePresentation(PRESENTATION_LANDING_CHAPTERS,music.beats,fps);
    assert.equal(landing.at(-1)!.start+landing.at(-1)!.duration,65*fps);
    for(const entry of landing.slice(0,-1))assert.ok(music.beats.some((beat:number)=>Math.abs(beat-(entry.start+entry.duration)/fps)<=.5/fps));
    assert.ok(PRESENTATION_LANDING_CHAPTERS.some(chapter=>chapter.kind==='avatars'));
    assert.ok(PRESENTATION_LANDING_CHAPTERS.some(chapter=>chapter.kind==='notifications'));
  }
});

test('invalid pulses and unreadable chapters cannot produce a render timeline',()=>{
  assert.throws(()=>timePresentation(PRESENTATION_CHAPTERS,[1,1],30));
  assert.throws(()=>timePresentation(PRESENTATION_CHAPTERS,[Number.NaN],30));
  assert.throws(()=>timePresentation([{...PRESENTATION_CHAPTERS[0],durationSeconds:.2}],[],30));
});
