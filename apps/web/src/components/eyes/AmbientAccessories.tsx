/**
 * Offline physical props; their material and motion belong to the existing rig's CSS.
 *
 * The weather also HAPPENS around the face (ADR-294, follow-up of 2026-11-13): a
 * cloud rains on the umbrella and drops gather at its rim, snow falls from its
 * cloud, a gust crosses with a leaf, the freezing cold shows a breath, and an
 * ordinary day has its sky. Every particle is placed and timed by the sheet from
 * the rig's own phases (`ambientMotion`): none carries a style or a timer.
 *
 * And the weather is LIVED: the first drop of a rain lands on the head, the first
 * flake of a snow on the nose. They ride the head with the other props and are
 * placed by the sheet from the path their scene drives (`weatherDrop`,
 * `weatherFlake`, `weather-scenes.ts`).
 */
import { Fragment, type ReactNode } from 'react';

import { scarfLayoutStyle } from './layout-profiles';
import { DEFAULT_SCARF_FIT, type ScarfFit } from './volume/scarf-fit';
import { scarfWrapFacets, scarfKnotFacets, scarfFacetStyle } from './volume/scarf-wrap';

const DEFAULT_SCARF_STYLE = scarfLayoutStyle(DEFAULT_SCARF_FIT, 'scarf-default');
const WEATHER_PROPS = [
  { weather: 'rain', motion: '' },
  { weather: 'storm', motion: '' },
  { weather: 'cold', motion: '' },
  { weather: 'freezing', motion: '' },
  { weather: 'snow', motion: '' },
  { weather: 'hot', motion: 'lia-ambient-weather-fan' },
  { weather: 'heat', motion: 'lia-ambient-weather-sweat' },
  { weather: 'fog', motion: '' },
  { weather: 'wind', motion: '' },
  { weather: 'night', motion: '' },
  { weather: 'drop', motion: '' },
  { weather: 'flake', motion: '' },
] as const;

type WeatherProp = {
  readonly weather: (typeof WEATHER_PROPS)[number]['weather'];
  readonly motion: (typeof WEATHER_PROPS)[number]['motion'];
};

/** Independent projected halves surround the head without an inverse camera. */
export function WrappedScarf({ fit }: { fit?: ScarfFit }) {
  if (!fit?.wrap) return null;
  const facets = scarfWrapFacets(fit);
  const [knot, tail] = scarfKnotFacets(fit);
  return (
    <>
      {(['back', 'front'] as const).map(side => (
        <span
          key={side}
          aria-hidden="true"
          className={`lia-ambient-weather lia-ambient-weather--cold lia-scarf-wrap lia-scarf-wrap--${side}`}
          style={DEFAULT_SCARF_STYLE}
        >
          <span className={`lia-scarf-wrap-layer lia-scarf-wrap-layer--${side}`}>
            {facets.map((facet, index) => {
              const front = facet.origin.z + facet.horizontal.z / 2 > 0;
              return front === (side === 'front') ? (
                <span key={index} className="lia-scarf-wrap-facet" style={scarfFacetStyle(facet)} />
              ) : null;
            })}
            {side === 'front' ? (
              <>
                <span className="lia-scarf-wrap-knot" style={scarfFacetStyle(knot)} />
                <span className="lia-scarf-wrap-tail" style={scarfFacetStyle(tail)} />
              </>
            ) : null}
          </span>
        </span>
      ))}
    </>
  );
}

/** `count` particles of one kind, each told apart by its index class. */
function particles(kind: string, count: number, extra = ''): ReactNode[] {
  return Array.from({ length: count }, (_, index) => (
    <span key={index} className={`${extra}lia-ambient-${kind} lia-ambient-${kind}--${index}`} />
  ));
}

function WeatherMaterial({ weather, motion }: WeatherProp) {
  if (weather === 'cold')
    return (
      <span className="lia-ambient-prop lia-scarf-material">
        <span className="lia-scarf-band" />
        <span className="lia-scarf-tail" />
      </span>
    );
  if (weather === 'rain')
    return (
      <>
        <span className="lia-ambient-prop" />
        <span className="lia-ambient-cloud" />
        {particles('drop', 5)}
        {particles('rimdrop', 3)}
      </>
    );
  if (weather === 'snow')
    return (
      <>
        <span className="lia-ambient-cloud" />
        {particles('flake', 7, 'lia-ambient-prop ')}
      </>
    );
  if (weather === 'drop' || weather === 'flake')
    return <span className={`lia-ambient-scene-${weather}`} />;
  if (weather === 'wind')
    return (
      <>
        <span className="lia-ambient-gust-line lia-ambient-gust-line--a" />
        <span className="lia-ambient-gust-line lia-ambient-gust-line--b" />
        <span className="lia-ambient-prop lia-ambient-gust-leaf" />
      </>
    );
  return <span className={'lia-ambient-prop ' + motion} />;
}

/**
 * The sky of an ordinary day: a sun whose rays turn and breathe, and a cloud
 * that passes before it. Mounted beside the head, not on it: the sky stays
 * where the day is. Drawn on as few boxes as it can — it is there most days,
 * and every box under the face is restyled on each frame: the sun's slot paints
 * its glow and its core (the rays never cross the core), the rays are the one
 * part that turns, and the cloud paints itself.
 */
export function SkyAccessories() {
  return (
    <span aria-hidden="true" className="lia-ambient-weather lia-ambient-weather--sun">
      <span className="lia-sky-rays" />
      <span aria-hidden="true" className="lia-ambient-weather lia-ambient-weather--cloud" />
    </span>
  );
}

/** CSS installs a local bitmap only when its weather prop is active. */
export function AmbientAccessories({ fit }: { fit?: ScarfFit }) {
  return (
    <>
      {WEATHER_PROPS.map(({ weather, motion }) =>
        // A closed garment is projected beside the head, not inside its turn.
        weather === 'cold' && fit?.wrap ? null : (
          <Fragment key={weather}>
            <span
              aria-hidden="true"
              className={'lia-ambient-weather lia-ambient-weather--' + weather}
              style={weather === 'cold' ? DEFAULT_SCARF_STYLE : undefined}
            >
              <WeatherMaterial weather={weather} motion={motion} />
            </span>
            {weather === 'freezing' ? (
              // The breath is at the mouth, where the frost on the crown is not:
              // a stage over the head, switched by the same announcement.
              <span
                aria-hidden="true"
                className="lia-ambient-weather lia-ambient-weather--freezing lia-ambient-breath"
              >
                <span className="lia-ambient-breath-puff" />
              </span>
            ) : null}
          </Fragment>
        )
      )}
    </>
  );
}
