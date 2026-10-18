import { describe, expect, it } from 'vitest';
import { parsePlacePosition } from '../place-position-data';

const value = {
  version: 1,
  omitted_count: 0,
  unlocated_count: 0,
  places: [
    {
      ref: 'place_one',
      label: 'Equator',
      url: 'https://www.google.com/maps/place/?q=place_id:one',
      position: { lat: 0, lng: 0 },
    },
  ],
};
describe('closed Position archive wire', () => {
  it('preserves zero coordinates and rejects mutation of the wire schema', () => {
    expect(parsePlacePosition(JSON.stringify(value))?.places[0].position).toEqual({
      lat: 0,
      lng: 0,
    });
    expect(parsePlacePosition(JSON.stringify({ ...value, api_key: 'forged' }))).toBeNull();
    expect(parsePlacePosition(JSON.stringify({ ...value, version: 2 }))).toBeNull();
  });
  it.each([NaN, Infinity, 91, '0', true])('rejects invalid latitude %s', lat => {
    const place = { ...value.places[0], position: { lat, lng: 0 } };
    expect(parsePlacePosition(JSON.stringify({ ...value, places: [place] }))).toBeNull();
  });
  it.each([
    'javascript:alert(1)',
    'https://evil.test/maps/',
    'https://www.google.com.evil.test/maps/',
    'https://x@www.google.com/maps/',
  ])('refuses noncanonical link %s', url => {
    expect(
      parsePlacePosition(JSON.stringify({ ...value, places: [{ ...value.places[0], url }] }))
    ).toBeNull();
  });
  it('keeps explicitly unlocated entries and refuses duplicate references or impossible counts', () => {
    expect(
      parsePlacePosition(
        JSON.stringify({
          ...value,
          unlocated_count: 1,
          places: [{ ...value.places[0], position: null }],
        })
      )?.unlocated_count
    ).toBe(1);
    expect(
      parsePlacePosition(JSON.stringify({ ...value, places: [value.places[0], value.places[0]] }))
    ).toBeNull();
    expect(parsePlacePosition(JSON.stringify({ ...value, unlocated_count: 99 }))).toBeNull();
  });
});
