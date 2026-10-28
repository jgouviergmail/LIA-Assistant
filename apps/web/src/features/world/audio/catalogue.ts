import type { Atmosphere } from '../atmosphere';
export const SOUND_FILES = {
  birds: 'birds',
  rain: 'rain',
  cicadas: 'cicadas',
  studio: 'studio',
  mystic: 'mystic',
  cafeteria: 'cafeteria',
  typewriters: 'typewriters',
  arcade: 'arcade',
  atrium: 'atrium',
  water: 'water',
  printers: 'printers',
  children: 'children',
  gym: 'gym',
  phone: 'phone',
  message: 'message',
  leaves: 'leaves',
  billiards: 'billiards',
  splash: 'splash',
  'machine-start': 'machine-start',
  'machine-gantry': 'machine-gantry',
  'machine-printer': 'machine-printer',
  'cat-meow': 'cat-meow',
  'workout-effort': 'workout-effort',
} as const;
export type SoundId = keyof typeof SOUND_FILES;
export type EffectSoundId =
  | 'leaves'
  | 'billiards'
  | 'splash'
  | 'machine-start'
  | 'machine-gantry'
  | 'machine-printer'
  | 'cat-meow'
  | 'workout-effort';
export type Ambience = Exclude<SoundId, 'message' | EffectSoundId>;
const INDOORS: Readonly<Record<string, Ambience | null>> = {
  arrival: 'atrium',
  meeting: 'typewriters',
  multimedia: 'arcade',
  phone: 'phone',
  memory: 'children',
  cafeteria: 'cafeteria',
  engineering: 'printers',
  gym: 'gym',
  divination: 'mystic',
  home: 'studio',
  library: null,
  restroom: 'water',
};
export function soundUrl(id: SoundId): string {
  return '/world/audio/v1/' + SOUND_FILES[id] + '.mp3?v=6';
}
export function ambientFor(zone: string | null, a: Atmosphere): Ambience | null {
  if (zone && Object.hasOwn(INDOORS, zone)) return INDOORS[zone];
  if (zone && zone !== 'garden' && zone !== 'terrace') return null;
  if (a.weather === 'rain') return 'rain';
  if (a.weather === 'snow' || !['dawn', 'morning', 'noon', 'afternoon'].includes(a.phase))
    return null;
  return zone === 'terrace' ? 'cicadas' : 'birds';
}
