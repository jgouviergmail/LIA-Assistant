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
} as const;
export type SoundId = keyof typeof SOUND_FILES;
export type Ambience = Exclude<SoundId, 'message'>;
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
  return '/world/audio/v1/' + SOUND_FILES[id] + '.mp3?v=3';
}
export function ambientFor(zone: string | null, a: Atmosphere): Ambience | null {
  if (zone && Object.hasOwn(INDOORS, zone)) return INDOORS[zone];
  if (zone && zone !== 'garden' && zone !== 'terrace') return null;
  if (a.weather === 'rain') return 'rain';
  if (a.weather === 'snow' || !['dawn', 'morning', 'noon', 'afternoon'].includes(a.phase))
    return null;
  return zone === 'terrace' ? 'cicadas' : 'birds';
}
