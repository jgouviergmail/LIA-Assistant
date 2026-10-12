import assert from 'node:assert/strict';
import test from 'node:test';
import {fixedWindow,fixedFocus,nativeShotAt,focusOpacity,validateSourceRect,assertFixedGeometry,heldNativeStateFrame} from '../src/presentation-geometry.ts';
import {PRESENTATION_CHAPTERS,PRESENTATION_LANDING_CHAPTERS,PRESENTATION_NATIVE_SHOTS,PRESENTATION_FOCUS_SHOTS,PRESENTATION_FOCUS_PLAN} from '../src/presentation-plan.ts';

test('native window corners remain identical on every frame, including detail cuts and focus holds',()=>{
  for(const fps of [25,30])for(const chapter of [...PRESENTATION_CHAPTERS,...PRESENTATION_LANDING_CHAPTERS]){
    const expected=fixedWindow(chapter.layout);
    const shots=PRESENTATION_NATIVE_SHOTS[chapter.kind as keyof typeof PRESENTATION_NATIVE_SHOTS];
    if(!shots)continue;
    for(let frame=0;frame<chapter.durationSeconds*fps;frame++){
      const active=nativeShotAt(shots,frame,fps,chapter.durationSeconds,0,[]);
      assert.deepEqual(fixedWindow(chapter.layout),expected);
      // A target's appearance cannot modify the parent coordinates/scale.
      const opacity=focusOpacity(active.localSeconds,active.duration,active.shot.focusTarget!==undefined);
      assert.ok(opacity>=0&&opacity<=1);
      assert.equal(expected.x+expected.width,expected.x+1440*expected.scale);
      assert.equal(expected.y+expected.height,expected.y+960*expected.scale);
    }
  }
});

test('a native crop preserves the exact source rectangle with no reflow or drift',()=>{
  const source={x:280,y:446.21875,width:884,height:95};
  for(const layout of ['left','right','top','full'] as const){
    const projected=fixedFocus(source,layout);
    // The native rectangle's two corners coincide exactly with the crop corners.
    assert.equal(source.x*projected.scale+projected.sourceLeft,0);
    assert.equal(source.y*projected.scale+projected.sourceTop,0);
    assert.ok(Math.abs((source.x+source.width)*projected.scale+projected.sourceLeft-projected.width)<1e-9);
    assert.ok(Math.abs((source.y+source.height)*projected.scale+projected.sourceTop-projected.height)<1e-9);
    assert.ok(projected.x>=0&&projected.y>=0&&projected.x+projected.width<=1920&&projected.y+projected.height<=1080);
    for(const frame of [0,1,30,90,180,300])assert.deepEqual(fixedFocus(source,layout),projected);
  }
});

test('an absent, short, malformed or out-of-source focus cannot create a camera move',()=>{
  assert.equal(focusOpacity(4,10,false),0);
  assert.equal(focusOpacity(1.5,3,true),0);
  for(const invalid of [{x:-1,y:0,width:10,height:10},{x:1400,y:0,width:80,height:10},
    {x:0,y:0,width:0,height:10},{x:0,y:0,width:NaN,height:10}])assert.throws(()=>validateSourceRect(invalid));
});

test('musical detail cuts change the selected native content, never the source geometry',()=>{
  const shots=[{detail:'first'},{detail:'second',focusTarget:0 as const}];
  assert.equal(nativeShotAt(shots,119,30,8,12,[16]).shot.detail,'first');
  assert.equal(nativeShotAt(shots,120,30,8,12,[16]).shot.detail,'second');
  assert.deepEqual(fixedWindow('left'),{x:770,y:190,scale:.72,width:1036.8,height:691.1999999999999});
});

test('PWA has explicit film, landing and independent source shots',()=>{
  assert.ok(PRESENTATION_CHAPTERS.some(chapter=>chapter.kind==='mobile'&&chapter.editorialTopics?.includes('pwa_installation')));
  assert.ok(PRESENTATION_LANDING_CHAPTERS.some(chapter=>chapter.kind==='mobile'));
  assert.deepEqual(PRESENTATION_FOCUS_SHOTS.mobile?.map(shot=>shot.detail),['pwa-mobile','pwa-install']);
  assert.equal(PRESENTATION_FOCUS_PLAN.find(focus=>focus.id==='focus-mobile')?.kind,'mobile');
});

test('the frame guard rejects a slide, zoom or reflow in actual measured geometry',()=>{
  const expected={x:770,y:190,width:1036.8,height:691.2};
  assert.doesNotThrow(()=>assertFixedGeometry(expected,{...expected,x:770.01}));
  assert.throws(()=>assertFixedGeometry(expected,{...expected,x:771}),/Native geometry drift/);
  assert.throws(()=>assertFixedGeometry(expected,{...expected,width:expected.width*1.01}),/Native geometry drift/);
  assert.throws(()=>assertFixedGeometry(expected,{...expected,height:700}),/Native geometry drift/);
});

test('folds and modals are held in a chosen native state throughout each shot',()=>{
  for(const fps of [25,30]){
    assert.equal(heldNativeStateFrame('memories',0,fps),fps);
    assert.equal(heldNativeStateFrame('llm-config',0,fps),4*fps);
    assert.equal(heldNativeStateFrame('llm-config',1,fps),0);
    assert.equal(heldNativeStateFrame('radio',1,fps),4*fps);
  }
});
