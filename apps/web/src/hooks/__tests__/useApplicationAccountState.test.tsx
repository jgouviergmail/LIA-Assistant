import { act, renderHook } from '@testing-library/react';
import { expect, it } from 'vitest';
import { useApplicationAccountState } from '../useApplicationAccountState';

it('queues functional edits without losing previous edits and rejects an old account setter', () => {
  const { result, rerender } = renderHook(
    ({ owner }) => useApplicationAccountState(owner, { a: 0, b: 0 }),
    { initialProps: { owner: 'one' } }
  );
  act(() => {
    result.current[1](previous => ({ ...previous, a: 1 }));
    result.current[1](previous => ({ ...previous, b: 2 }));
  });
  expect(result.current[0]).toEqual({ a: 1, b: 2 });
  const old = result.current[1];
  rerender({ owner: 'two' });
  expect(result.current[0]).toEqual({ a: 0, b: 0 });
  act(() => old(previous => ({ ...previous, a: 9 })));
  expect(result.current[0]).toEqual({ a: 0, b: 0 });
  rerender({ owner: 'one' });
  expect(result.current[0]).toEqual({ a: 0, b: 0 });
});
