import { afterEach, beforeEach, expect, it, vi } from 'vitest';
import { PcmSendQueue } from '../pcm-send-queue';
import { AVATAR_PCM_SEND_STALL_MS } from '../types';

beforeEach(() => {
  vi.useFakeTimers();
});
afterEach(() => {
  vi.useRealTimers();
});
it('forwards every accepted packet at once, in order, never held back to the PCM clock', () => {
  const sent: number[] = [];
  const queue = new PcmSendQueue(packet => {
    sent.push(packet[0]);
    return true;
  }, vi.fn());
  for (let i = 0; i < 25; i++) queue.enqueue(new Uint8Array(6000).fill(i));
  expect(sent).toEqual(Array.from({ length: 25 }, (_, i) => i));
  expect(queue.pendingBytes).toBe(0);
  expect(vi.getTimerCount()).toBe(0);
  queue.dispose();
});

it('bounds backlog and refuses a transport blocked longer than the stall bound', () => {
  const send = vi.fn(() => false);
  const failed = vi.fn();
  const queue = new PcmSendQueue(send, failed);
  for (let i = 0; i < 26; i++) queue.enqueue(new Uint8Array(6000));
  expect(queue.pendingBytes).toBe(156000);
  expect(() => queue.enqueue(new Uint8Array(6000))).toThrow('voice_pcm_backlog_full');
  vi.advanceTimersByTime(AVATAR_PCM_SEND_STALL_MS - 40);
  expect(failed).not.toHaveBeenCalled();
  vi.advanceTimersByTime(60);
  expect(failed).toHaveBeenCalledTimes(1);
  expect(queue.pendingBytes).toBe(0);
  queue.dispose();
});

it('cancels held packets, handles a throwing socket, and refuses disposal reuse', () => {
  let writable = false;
  const send = vi.fn(() => writable);
  const failed = vi.fn();
  const queue = new PcmSendQueue(send, failed);
  queue.enqueue(new Uint8Array(6000));
  queue.enqueue(new Uint8Array(6000));
  expect(send).toHaveBeenCalledTimes(1);
  queue.clear();
  writable = true;
  vi.advanceTimersByTime(500);
  expect(send).toHaveBeenCalledTimes(1);
  send.mockImplementation(() => {
    throw new Error('socket_failed');
  });
  queue.enqueue(new Uint8Array(200));
  expect(failed).toHaveBeenCalledTimes(1);
  expect(queue.pendingBytes).toBe(0);
  queue.dispose();
  expect(() => queue.enqueue(new Uint8Array(200))).toThrow();
});

it('recovers a short stall by forwarding the held packets in order, unmodified', () => {
  let writable = false;
  const accepted: { time: number; value: number }[] = [];
  const queue = new PcmSendQueue(packet => {
    if (!writable) return false;
    accepted.push({ time: performance.now(), value: packet[0] });
    return true;
  }, vi.fn());
  const first = new Uint8Array(6000).fill(1);
  queue.enqueue(first);
  queue.enqueue(new Uint8Array(6000).fill(2));
  first.fill(9);
  vi.advanceTimersByTime(200);
  writable = true;
  vi.advanceTimersByTime(20);
  expect(accepted).toEqual([
    { time: 220, value: 1 },
    { time: 220, value: 2 },
  ]);
  expect(queue.pendingBytes).toBe(0);
  queue.dispose();
});

it('a blocked transport that resumes resets the stall clock', () => {
  let writable = false;
  const failed = vi.fn();
  const queue = new PcmSendQueue(() => writable, failed);
  queue.enqueue(new Uint8Array(6000));
  vi.advanceTimersByTime(AVATAR_PCM_SEND_STALL_MS - 100);
  writable = true;
  vi.advanceTimersByTime(20);
  expect(queue.pendingBytes).toBe(0);
  writable = false;
  queue.enqueue(new Uint8Array(6000));
  vi.advanceTimersByTime(AVATAR_PCM_SEND_STALL_MS - 100);
  expect(failed).not.toHaveBeenCalled();
  queue.dispose();
});

it('refuses empty, odd and oversized packets without calling the transport', () => {
  const send = vi.fn(() => true);
  const queue = new PcmSendQueue(send, vi.fn());
  for (const size of [0, 3, 6002])
    expect(() => queue.enqueue(new Uint8Array(size))).toThrow('voice_invalid_pcm_packet');
  expect(send).not.toHaveBeenCalled();
  expect(queue.pendingBytes).toBe(0);
  queue.dispose();
});

it('a synchronous transport teardown cannot make the cleared backlog negative', () => {
  const queue = new PcmSendQueue(() => {
    queue.dispose();
    return true;
  }, vi.fn());
  queue.enqueue(new Uint8Array(6000));
  expect(queue.pendingBytes).toBe(0);
  expect(vi.getTimerCount()).toBe(0);
});
