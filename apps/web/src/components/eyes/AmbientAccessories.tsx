/** Offline physical props; their material and motion belong to the existing rig's CSS. */
import { scarfLayoutStyle } from './layout-profiles';
import { DEFAULT_SCARF_FIT, type ScarfFit } from './volume/scarf-fit';
import { scarfWrapFacets, scarfKnotFacets, scarfFacetStyle } from './volume/scarf-wrap';

const DEFAULT_SCARF_STYLE = scarfLayoutStyle(DEFAULT_SCARF_FIT, 'scarf-default');
const WEATHER_PROPS = [
  { weather: 'rain', motion: '' },
  { weather: 'storm', motion: '' },
  { weather: 'cold', motion: '' },
  { weather: 'freezing', motion: '' },
  { weather: 'snow', motion: 'lia-ambient-weather-fall lia-ambient-weather-fall--snow' },
  { weather: 'hot', motion: 'lia-ambient-weather-fan' },
  { weather: 'heat', motion: 'lia-ambient-weather-sweat' },
  { weather: 'fog', motion: '' },
  { weather: 'wind', motion: '' },
  { weather: 'night', motion: '' },
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

function WeatherMaterial({ weather, motion }: WeatherProp) {
  if (weather === 'cold')
    return (
      <span className="lia-ambient-prop lia-scarf-material">
        <span className="lia-scarf-band" />
        <span className="lia-scarf-tail" />
      </span>
    );
  if (weather === 'snow')
    return (
      <span className={motion}>
        {(['a', 'b', 'c'] as const).map(edge => (
          <span key={edge} className={'lia-ambient-prop lia-ambient-prop--snow-' + edge} />
        ))}
      </span>
    );
  return <span className={'lia-ambient-prop ' + motion} />;
}

/** CSS installs a local bitmap only when its weather prop is active. */
export function AmbientAccessories({ fit }: { fit?: ScarfFit }) {
  return (
    <>
      {WEATHER_PROPS.map(({ weather, motion }) =>
        // A closed garment is projected beside the head, not inside its turn.
        weather === 'cold' && fit?.wrap ? null : (
          <span
            key={weather}
            aria-hidden="true"
            className={'lia-ambient-weather lia-ambient-weather--' + weather}
            style={weather === 'cold' ? DEFAULT_SCARF_STYLE : undefined}
          >
            <WeatherMaterial weather={weather} motion={motion} />
          </span>
        )
      )}
    </>
  );
}
