import { expect, it } from 'vitest';
import { useCompanionEnvironmentStore as store } from '../companionEnvironmentStore';

it('forgets ambient data at the session owner boundary', () => {
  store.getState().setEnvironment({ timezone: 'UTC', weather: null });
  expect(store.getState().environment?.timezone).toBe('UTC');
  store.getState().reset();
  expect(store.getState().environment).toBeNull();
});
