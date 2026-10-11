/** Offline physical props; their material and motion belong to the existing rig's CSS. */
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

function WeatherMaterial({ weather, motion }: WeatherProp) {
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
export function AmbientAccessories() {
  return (
    <>
      {WEATHER_PROPS.map(({ weather, motion }) => (
        <span
          key={weather}
          aria-hidden="true"
          className={'lia-ambient-weather lia-ambient-weather--' + weather}
        >
          <WeatherMaterial weather={weather} motion={motion} />
        </span>
      ))}
    </>
  );
}
