import {
  Cloud,
  CloudDrizzle,
  CloudFog,
  CloudLightning,
  CloudRain,
  Snowflake,
  Sun,
  Wind,
} from 'lucide-react';

/** The briefing API publishes OpenWeatherMap main codes, not translated descriptions. */
type WeatherKind =
  | 'clear'
  | 'clouds'
  | 'rain'
  | 'drizzle'
  | 'storm'
  | 'snow'
  | 'fog'
  | 'wind'
  | 'unknown';
const CONDITIONS: Readonly<Record<string, WeatherKind>> = {
  clear: 'clear',
  clouds: 'clouds',
  rain: 'rain',
  drizzle: 'drizzle',
  thunderstorm: 'storm',
  snow: 'snow',
  mist: 'fog',
  fog: 'fog',
  haze: 'fog',
  smoke: 'fog',
  dust: 'fog',
  sand: 'fog',
  ash: 'fog',
  squall: 'wind',
  tornado: 'wind',
};
const ICONS = {
  clear: Sun,
  clouds: Cloud,
  rain: CloudRain,
  drizzle: CloudDrizzle,
  storm: CloudLightning,
  snow: Snowflake,
  fog: CloudFog,
  wind: Wind,
};
function kindFor(code: string): WeatherKind {
  const normalized = code.trim().toLowerCase();
  return Object.hasOwn(CONDITIONS, normalized) ? CONDITIONS[normalized] : 'unknown';
}

/** Static artwork respects reduced motion without a second animated rendering. */
export function WeatherIllustration({
  conditionCode,
  fallbackEmoji,
}: {
  conditionCode: string;
  fallbackEmoji: string;
}) {
  return (
    <svg
      viewBox="0 0 140 120"
      className="block h-auto w-full min-w-0 overflow-hidden"
      aria-hidden="true"
      focusable="false"
      data-testid="weather-landscape"
    >
      <WeatherSky kind={kindFor(conditionCode)} fallbackEmoji={fallbackEmoji} />
      <path d="M-18 99Q33 61 155 101V124H-18Z" fill="#c4d7d0" />
      <path d="M34 124Q98 69 157 91V124Z" fill="#aac5bc" />
      <path d="M-12 115Q46 92 153 122V126H-12Z" fill="#82aaa0" />
    </svg>
  );
}

function WeatherSky({ kind, fallbackEmoji }: { kind: WeatherKind; fallbackEmoji: string }) {
  if (kind === 'unknown')
    return (
      <text x="77" y="64" textAnchor="middle" fontSize="43">
        {fallbackEmoji}
      </text>
    );
  return (
    <>
      {kind === 'clear' && (
        <>
          <circle cx="93" cy="33" r="35" fill="#e6bb58" opacity="0.11" />
          <circle cx="93" cy="33" r="25" fill="#e6bb58" />
        </>
      )}
      <path
        d="M49 69a14 14 0 0 1 0-28h2a23 23 0 0 1 43-9 18 18 0 0 1 18 15h6a11 11 0 0 1 0 22Z"
        className={
          kind === 'storm'
            ? 'fill-slate-400 dark:fill-slate-500'
            : 'fill-slate-200 dark:fill-slate-400'
        }
      />
      <WeatherPrecipitation kind={kind} />
      {kind === 'fog' && (
        <path
          d="M30 76h77m-65 8h86M24 91h69"
          stroke="#9dafb8"
          strokeWidth="3"
          strokeLinecap="round"
        />
      )}
      {kind === 'wind' && <Wind x="53" y="65" width="57" height="30" className="text-sky-500" />}
    </>
  );
}
function WeatherPrecipitation({ kind }: { kind: WeatherKind }) {
  if (kind === 'snow')
    return (
      <>
        <Snowflake x="48" y="73" width="13" height="13" className="text-sky-400" />
        <Snowflake x="78" y="78" width="13" height="13" className="text-sky-400" />
        <Snowflake x="106" y="72" width="13" height="13" className="text-sky-400" />
      </>
    );
  if (kind !== 'rain' && kind !== 'drizzle' && kind !== 'storm') return null;
  return (
    <>
      <path
        d="m57 76-4 9m30-9-4 9m30-9-4 9"
        stroke="#6b9fb4"
        strokeWidth={kind === 'drizzle' ? 2 : 3}
        strokeLinecap="round"
      />
      {kind === 'storm' && <path d="m89 62-12 19h11l-6 15 23-25H91l6-9Z" fill="#d6ae50" />}
    </>
  );
}

/** Reuse the same condition vocabulary for the small daily forecast icons. */
export function WeatherConditionIcon({
  conditionCode,
  fallbackEmoji,
}: {
  conditionCode: string;
  fallbackEmoji: string;
}) {
  const kind = kindFor(conditionCode);
  if (kind === 'unknown')
    return (
      <span aria-hidden="true" className="text-xl leading-none">
        {fallbackEmoji}
      </span>
    );
  const Icon = ICONS[kind];
  return (
    <Icon
      aria-hidden="true"
      className={
        kind === 'clear' ? 'size-5 text-amber-500' : 'size-5 text-sky-600 dark:text-sky-400'
      }
    />
  );
}
