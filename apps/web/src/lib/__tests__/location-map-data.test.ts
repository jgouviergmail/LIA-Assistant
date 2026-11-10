import { describe, expect, it } from 'vitest';
import { locationMapPresentation, parseLocationMap } from '../location-map-data';

const data = {
  version: 1,
  label: 'Equator',
  address: 'Received address',
  position: { lat: 0, lng: 0 },
};

describe('closed address-map projection', () => {
  it('preserves literal received text and zero coordinates without creating a registry item', () => {
    const parsed = parseLocationMap(
      JSON.stringify({ ...data, label: '<img src=x onerror=alert(1)>' })
    );
    expect(parsed?.label).toBe('<img src=x onerror=alert(1)>');
    expect(parsed?.position).toEqual({ lat: 0, lng: 0 });
    expect(parsed && locationMapPresentation(parsed).places[0]).toEqual({
      ref: 'address',
      label: parsed?.label,
      position: { lat: 0, lng: 0 },
      url: 'https://www.google.com/maps/search/?api=1&query=0,0',
    });
  });
  it.each([NaN, Infinity, 91, -91, '0', true, null])('refuses invalid latitude %s', lat => {
    expect(parseLocationMap(JSON.stringify({ ...data, position: { lat, lng: 0 } }))).toBeNull();
  });
  it.each([
    { ...data, version: 2 },
    { ...data, api_key: 'forged' },
    { ...data, url: 'javascript:alert(1)' },
    { ...data, label: '' },
    { ...data, address: 'x'.repeat(1001) },
    { ...data, position: { lat: 0, lng: 181 } },
  ])('refuses a changed or oversized contract', value => {
    expect(parseLocationMap(JSON.stringify(value))).toBeNull();
  });
  it.each([null, {}, '{', ' '.repeat(16385)])('refuses a malformed wire', wire => {
    expect(parseLocationMap(wire)).toBeNull();
  });
});
