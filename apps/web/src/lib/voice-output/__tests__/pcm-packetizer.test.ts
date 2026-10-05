import { expect, it } from 'vitest';
import { PcmPacketizer } from '../pcm-packetizer';
import { AVATAR_PCM_MAX_BACKLOG_BYTES } from '../types';

it('makes contiguous even packets and preserves a weak final tail without zero padding', () => {
  const packets = new PcmPacketizer();
  const source = Uint8Array.from({ length: 15010 }, (_, i) => i % 253);
  const output = [
    ...packets.push(source.subarray(0, 4002)),
    ...packets.push(source.subarray(4002)),
  ];
  expect(output.map(packet => packet.length)).toEqual([6000, 6000]);
  expect(output[0]).toEqual(source.subarray(0, 6000));
  expect(output[1]).toEqual(source.subarray(6000, 12000));
  expect(packets.finish()).toEqual(source.subarray(12000));
  expect(packets.finish()).toBeNull();
});
it('rejects odd PCM/oversized bursts and drops a cancelled tail', () => {
  const packets = new PcmPacketizer();
  expect(() => packets.push(new Uint8Array(3))).toThrow();
  expect(() => packets.push(new Uint8Array(AVATAR_PCM_MAX_BACKLOG_BYTES + 2))).toThrow();
  packets.push(new Uint8Array(200));
  packets.clear();
  expect(packets.finish()).toBeNull();
});
