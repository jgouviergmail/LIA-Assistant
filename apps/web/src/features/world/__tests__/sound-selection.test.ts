import { expect, it } from 'vitest';
import { ambientFor } from '../audio/catalogue';
import { NEUTRAL_ATMOSPHERE } from '../atmosphere';
it('gives every indoor room its sound identity and leaves the library silent', () => {
  const sounds = {
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
  } as const;
  for (const [zone, sound] of Object.entries(sounds))
    expect(ambientFor(zone, { ...NEUTRAL_ATMOSPHERE, phase: 'night', weather: 'rain' })).toBe(
      sound
    );
});
it('matches outdoor sound to weather and daylight, even on grass outside the named garden', () => {
  const day = { ...NEUTRAL_ATMOSPHERE, phase: 'noon' as const };
  expect(ambientFor('garden', day)).toBe('birds');
  expect(ambientFor('terrace', day)).toBe('cicadas');
  expect(ambientFor(null, day)).toBe('birds');
  for (const zone of ['garden', 'terrace', null]) {
    expect(ambientFor(zone, { ...day, weather: 'rain' })).toBe('rain');
    expect(ambientFor(zone, { ...day, phase: 'night' })).toBeNull();
  }
});
