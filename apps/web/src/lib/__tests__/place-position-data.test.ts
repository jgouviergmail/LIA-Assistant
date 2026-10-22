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
    expect(parsePlacePosition(JSON.stringify({ ...value, version: 3 }))).toBeNull();
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
  const details = {
    address: '1 Main Street',
    rating: 0,
    reviews_count: 0,
    phone: '+33 1 23 45 67 89',
    website: 'https://example.test/?a=1&b=2',
    opening_hours: ['Monday: 09:00–18:00'],
  };
  function withDetails(overrides = {}) {
    return JSON.stringify({
      ...value,
      version: 2,
      places: [{ ...value.places[0], details: { ...details, ...overrides } }],
    });
  }
  it('reads old archives and preserves bounded details as text in new archives', () => {
    expect(parsePlacePosition(JSON.stringify(value))?.places[0].details).toBeUndefined();
    expect(parsePlacePosition(withDetails())?.places[0].details).toEqual(details);
    const text = '<img src=x onerror="alert(1)">';
    expect(parsePlacePosition(withDetails({ address: text }))?.places[0].details?.address).toBe(
      text
    );
    expect(
      parsePlacePosition(
        withDetails({
          address: null,
          rating: null,
          reviews_count: null,
          phone: null,
          website: null,
          opening_hours: [],
        })
      )
    ).not.toBeNull();
    expect(
      parsePlacePosition(
        JSON.stringify({ ...value, version: 2, places: [{ ...value.places[0], details: null }] })
      )
    ).not.toBeNull();
  });
  it('accepts a bounded large projection but refuses archives above the total budget', () => {
    const wire = withDetails({ address: 'a'.repeat(1000), opening_hours: ['a'.repeat(500)] });
    expect(parsePlacePosition(wire.padEnd(512 * 1024, ' '))).not.toBeNull();
    expect(parsePlacePosition(wire.padEnd(512 * 1024 + 1, ' '))).toBeNull();
  });
  it('measures detail text with the same Unicode character bounds as the Python projection', () => {
    const address = '📍'.repeat(1000);
    const opening_hours = ['🕘'.repeat(500)];
    expect(parsePlacePosition(withDetails({ address, opening_hours }))?.places[0].details).toEqual({
      ...details,
      address,
      opening_hours,
    });
    expect(parsePlacePosition(withDetails({ address: address + 'a' }))).toBeNull();
  });
  it.each([
    { website: 'javascript:alert(1)' },
    { website: 'https://user:secret@example.test/' },
    { website: 'https://user@example.test/' },
    { website: 'https://example.test/\npath' },
    { website: 'https://example.test\\@evil.test' },
    { website: 'https://' },
    { website: 'https://example.test/' + 'a'.repeat(4096) },
    { address: 'a'.repeat(1001) },
    { phone: 'a'.repeat(129) },
    { rating: 6 },
    { rating: true },
    { reviews_count: 1.5 },
    { reviews_count: -1 },
    { reviews_count: Number.MAX_SAFE_INTEGER + 1 },
    { opening_hours: Array.from({ length: 8 }, () => 'Monday') },
    { opening_hours: ['a'.repeat(501)] },
    { opening_hours: [{ raw: 'tree' }] },
    { photos: [{ name: 'not-projected' }] },
    { home: { lat: 1, lng: 2 } },
  ])('refuses malformed or unbounded detail fields %j', overrides => {
    expect(parsePlacePosition(withDetails(overrides))).toBeNull();
  });
});
