/** Qualification UI only. Every character uses the product's component and frame owner. */
import { useEffect, useState } from 'react';
import { createRoot } from 'react-dom/client';
import { EyesFace } from '@/components/eyes/EyesFace';
import { EYE_STYLE_IDS, type EyeStyleId } from '@/components/eyes/eye-styles';
import { parseEnvironment } from '@/components/eyes/environment';
import { WEATHER_COLD_MAX } from '@/components/eyes/rig/ambient';
import { BODY_SKETCHES, type BodySketchName } from '@/components/eyes/rig/body-sketches';
import { useCompanionEnvironmentStore } from '@/stores/companionEnvironmentStore';
import type { EyeExpression } from '@/components/eyes/expression-engine';
import type { EyesSize } from '@/stores/eyesWidgetStore';
import '@/styles/eyes.css';
import './proof.css';
import { playNativeScene } from './native-scenes';

const expressions = [
  'neutral',
  'attentive',
  'thinking',
  'searching',
  'speaking',
  'joy',
  'surprise',
  'sleep',
] as const satisfies readonly EyeExpression[];
const sizes = ['sm', 'md', 'lg', 'xl'] as const satisfies readonly EyesSize[];
const query = new URLSearchParams(location.search);
const contact = query.get('contact') === 'true';
const requestedContact = query.get('characters')?.split(',');
const contactCharacters = (['bip', 'oscar', 'nimbo'] as const).filter(
  value => !requestedContact || requestedContact.includes(value)
);
const selectedCharacter = EYE_STYLE_IDS.find(value => value === query.get('character')) ?? 'bip';
const selectedExpression =
  expressions.find(value => value === query.get('expression')) ?? 'neutral';
const selectedSize = sizes.find(value => value === query.get('size')) ?? 'xl';
const selectedScene = BODY_SKETCHES.find(value => value === query.get('scene')) ?? BODY_SKETCHES[0];
const gazes = {
  center: { x: 0, y: 0 },
  left: { x: -1, y: 0 },
  right: { x: 1, y: 0 },
  up: { x: 0, y: -1 },
  down: { x: 0, y: 1 },
} as const;
type GazeName = keyof typeof gazes;
const gazeNames = Object.keys(gazes) as GazeName[];

function Bench() {
  const [character, setCharacter] = useState<EyeStyleId>(selectedCharacter);
  const [expression, setExpression] = useState<EyeExpression>(selectedExpression);
  const [size, setSize] = useState<EyesSize>(selectedSize);
  const [dark, setDark] = useState(query.get('theme') === 'dark');
  const [life, setLife] = useState(query.get('life') === 'true');
  const [cold, setCold] = useState(query.get('cold') === 'true');
  const [scene, setScene] = useState<BodySketchName>(selectedScene);
  const [playback, setPlayback] = useState<{ scene: BodySketchName; take: number } | null>(null);
  const [gaze, setGaze] = useState<GazeName>(
    gazeNames.find(value => value === query.get('gaze')) ?? 'center'
  );
  useEffect(() => {
    const now = Date.now();
    const observation = parseEnvironment({
      timezone: 'UTC',
      weather: cold
        ? {
            temperature_c: 5,
            condition_code: 'Clear',
            wind_speed_kmh: 0,
            observed_at: new Date(now - 1000).toISOString(),
            expires_at: new Date(now + 3_600_000).toISOString(),
          }
        : null,
    });
    if (!observation)
      throw new Error('The audit weather observation must satisfy the native contract');
    useCompanionEnvironmentStore.getState().setEnvironment(observation);
    return () => useCompanionEnvironmentStore.getState().reset();
  }, [cold]);
  const contextEnabled = cold || life || playback !== null;
  useEffect(() => {
    if (playback) playNativeScene(playback.scene);
  }, [playback]);
  return (
    <main
      data-closeup={query.get('closeup') === 'true'}
      data-contact={contact}
      data-contact-count={contact ? contactCharacters.length * 2 : 0}
      data-theme={dark ? 'dark' : 'light'}
      data-cold-target={WEATHER_COLD_MAX}
      data-weather={cold ? 'cold' : 'none'}
      data-requested-scene={playback?.scene ?? ''}
      data-scene-take={playback?.take ?? 0}
    >
      <header>
        <p className="eyebrow">LIA · Native renderer qualification</p>
        <h1>{cold ? 'Scarf fit' : 'Living limbs'}</h1>
        <p>Live native rig beside the same identity in its fixed original pose.</p>
        {cold && (
          <p className="observation">
            Observed 5 °C · clear · UTC · native environment store · one-hour validity
          </p>
        )}
      </header>
      <nav aria-label="Visual controls">
        <label htmlFor="character">
          Character
          <select
            id="character"
            value={character}
            onChange={event => {
              const value = EYE_STYLE_IDS.find(item => item === event.target.value);
              if (value) setCharacter(value);
            }}
          >
            {EYE_STYLE_IDS.map(value => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label htmlFor="gaze">
          Gaze
          <select
            id="gaze"
            value={gaze}
            onChange={event => {
              const value = gazeNames.find(item => item === event.target.value);
              if (value) setGaze(value);
            }}
          >
            {gazeNames.map(value => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label htmlFor="expression">
          Expression
          <select
            id="expression"
            value={expression}
            onChange={event => {
              const value = expressions.find(item => item === event.target.value);
              if (value) setExpression(value);
            }}
          >
            {expressions.map(value => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label htmlFor="scene">
          Native scene
          <select
            id="scene"
            value={scene}
            onChange={event => {
              const value = BODY_SKETCHES.find(item => item === event.target.value);
              if (value) setScene(value);
            }}
          >
            {BODY_SKETCHES.map(value => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <button
          type="button"
          id="play-scene"
          onClick={() => setPlayback(previous => ({ scene, take: (previous?.take ?? 0) + 1 }))}
        >
          Play scene
        </button>
        <button
          type="button"
          id="play-warm-scene"
          disabled={!contextEnabled}
          onClick={() => playNativeScene(scene)}
        >
          Play on settled context
        </button>
        <label htmlFor="size">
          Size
          <select
            id="size"
            value={size}
            onChange={event => {
              const value = sizes.find(item => item === event.target.value);
              if (value) setSize(value);
            }}
          >
            {sizes.map(value => (
              <option key={value}>{value}</option>
            ))}
          </select>
        </label>
        <label>
          <input type="checkbox" checked={dark} onChange={event => setDark(event.target.checked)} />
          Dark
        </label>
        <label>
          <input
            type="checkbox"
            checked={contextEnabled}
            disabled={cold}
            onChange={event => setLife(event.target.checked)}
          />
          Spontaneous scenes
        </label>
        <label>
          <input
            id="cold"
            type="checkbox"
            checked={cold}
            onChange={event => setCold(event.target.checked)}
          />
          Cold observation
        </label>
      </nav>
      <section className="matrix" aria-label={contact ? 'Scarf variants' : `${character} variants`}>
        {(contact ? contactCharacters : [character]).flatMap(character =>
          (['female', 'male'] as const).map(variant => (
            <article key={`${character}-${variant}`} data-variant={variant}>
              <h2>
                {character} <span>{variant}</span>
              </h2>
              <div className="pair">
                <figure data-live="true">
                  <div className="stage">
                    <EyesFace
                      key={`${character}-${variant}-${contextEnabled}-${playback?.take ?? 0}`}
                      styleId={character}
                      variant={variant}
                      expression={expression}
                      gaze={gaze === 'center' && !cold ? null : gazes[gaze]}
                      size={size}
                      animate
                      life={contextEnabled}
                      allowSleep={scene === 'body-doze'}
                    />
                  </div>
                  <figcaption>Live · {expression}</figcaption>
                </figure>
                <figure data-live="false">
                  <div className="stage">
                    <EyesFace
                      styleId={character}
                      variant={variant}
                      expression="neutral"
                      gaze={null}
                      size={size}
                      animate={false}
                      staticPose
                      life={false}
                    />
                  </div>
                  <figcaption>Original pose</figcaption>
                </figure>
              </div>
            </article>
          ))
        )}
      </section>
      <footer>
        Actual product artwork, facial rig, GPU material and visibility gates. This bench calls no
        backend.
      </footer>
    </main>
  );
}

const root = document.getElementById('root');
if (!root) throw new Error('Missing visual bench root');
createRoot(root).render(<Bench />);
