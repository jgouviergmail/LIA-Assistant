import { expect, it, vi } from 'vitest';
import { SeatDashboardIntent, dashboardOfferOpen } from '../seat-dashboard-intent';

const scope = { stream: 2, epoch: 'epoch-two' };
const receipt = { ...scope, seq: 4, slot: 'atrium-n:0' };
it('offers once for a current acknowledged generic seat and consumes an explicit refusal', () => {
  const intent = new SeatDashboardIntent();
  const changed = vi.fn();
  const unsubscribe = intent.subscribe(changed);
  expect(intent.getSnapshot()).toBeNull();
  expect(intent.confirm(receipt, scope)).toBe(true);
  expect(intent.getSnapshot()).toMatchObject({ slot: receipt.slot, tableKey: 'atrium-table' });
  intent.cancel();
  expect(intent.getSnapshot()).toBeNull();
  expect(intent.confirm(receipt, scope)).toBe(false);
  expect(intent.request(receipt.slot)).toBe(true);
  expect(intent.getSnapshot()?.slot).toBe(receipt.slot);
  intent.cancel();
  expect(intent.confirm({ ...receipt, seq: 3 }, scope)).toBe(false);
  expect(intent.confirm({ ...receipt, seq: 5 }, scope)).toBe(true);
  expect(changed).toHaveBeenCalledTimes(5);
  unsubscribe();
  intent.cancel();
  expect(changed).toHaveBeenCalledTimes(5);
});
it('rejects restored, foreign and specific-activity seats without stealing their behavior', () => {
  const intent = new SeatDashboardIntent();
  expect(intent.confirm(receipt, { ...scope, stream: 3 })).toBe(false);
  expect(intent.confirm(receipt, { ...scope, epoch: 'replacement' })).toBe(false);
  for (const [index, slot] of [
    'meeting-boss:0',
    'library-seat-2:0',
    'wc-seat:0',
    'missing',
  ].entries())
    expect(intent.confirm({ ...receipt, seq: receipt.seq + index, slot }, scope)).toBe(false);
  expect(intent.getSnapshot()).toBeNull();
  expect(intent.request('missing')).toBe(false);
});
it('opens the consent only for the seat still held, so a stale offer never pauses input', () => {
  const offer = { slot: 'atrium-n:0', tableKey: 'atrium-table' };
  expect(dashboardOfferOpen(offer, 'atrium-n:0', 'epoch:atrium-n:0', true)).toBe(true);
  expect(dashboardOfferOpen(offer, 'atrium-n:1', 'epoch:atrium-n:1', true)).toBe(false);
  expect(dashboardOfferOpen(offer, 'atrium-n:0', null, true)).toBe(false);
  expect(dashboardOfferOpen(offer, 'atrium-n:0', 'epoch:atrium-n:0', false)).toBe(false);
  expect(dashboardOfferOpen(null, 'atrium-n:0', 'epoch:atrium-n:0', true)).toBe(false);
});
