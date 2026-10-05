import { expect, it } from 'vitest';
import { parseSimliSignal } from '../simli-protocol';

it.each(['START', 'ACK', 'SPEAK', 'SILENT', 'STOP', 'RATE', 'ERROR', 'CLOSING'])(
  'reads %s independently of socket or media readiness',
  control => {
    expect(parseSimliSignal(control)).toEqual({ kind: 'control', control });
  }
);
it('reads an SDP answer while unknown/malformed/oversized data has no side effect', () => {
  const sdp = 'v=0\r\na=fixture\r\n';
  expect(parseSimliSignal(JSON.stringify({ type: 'answer', sdp }))).toEqual({
    kind: 'answer',
    sdp,
  });
  for (const input of [
    null,
    {},
    new ArrayBuffer(3),
    'not-json',
    'ACKNOWLEDGE',
    '{',
    JSON.stringify({ type: 'offer', sdp }),
    JSON.stringify({ type: 'answer', sdp: 3 }),
    JSON.stringify({ type: 'answer', sdp: '' }),
    'x'.repeat(65537),
  ]) {
    expect(parseSimliSignal(input)).toEqual({ kind: 'unknown' });
  }
});
