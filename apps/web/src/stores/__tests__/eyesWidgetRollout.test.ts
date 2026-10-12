import { beforeEach, describe, expect, it, vi } from 'vitest';
import { EYES_WIDGET_PREFS_KEY } from '@/lib/constants';
import { useEyesWidgetStore } from '../eyesWidgetStore';

beforeEach(() => {
  localStorage.clear();
  useEyesWidgetStore.setState({ appliedAvatarStyleRolloutId: null });
  useEyesWidgetStore.getState().reset();
});

describe('avatar preference campaigns', () => {
  it('retains the current choice and marker when browser storage rejects the campaign write', () => {
    useEyesWidgetStore.getState().setStyle('cozmo');
    const saved = localStorage.getItem(EYES_WIDGET_PREFS_KEY);
    const storage = vi.spyOn(Storage.prototype, 'setItem').mockImplementation(() => {
      throw new DOMException('Storage is full', 'QuotaExceededError');
    });
    try {
      expect(() =>
        useEyesWidgetStore.getState().applyAvatarStyleRollout('production-bip-v3')
      ).not.toThrow();
      expect(useEyesWidgetStore.getState()).toMatchObject({
        style: 'cozmo',
        appliedAvatarStyleRolloutId: null,
      });
      expect(localStorage.getItem(EYES_WIDGET_PREFS_KEY)).toBe(saved);
    } finally {
      storage.mockRestore();
    }
  });

  it('applies one explicit campaign while preserving all other display preferences', () => {
    const store = useEyesWidgetStore.getState();
    store.setStyle('cozmo');
    store.setVisible(false);
    store.setSize('auto');
    store.setPosition({ xPct: 20, yPct: 30 });
    store.setLandingPosition({ xPct: 40, yPct: 50 });
    store.applyAvatarStyleRollout('production-bip-v3');
    expect(useEyesWidgetStore.getState()).toMatchObject({
      style: 'bip',
      appliedAvatarStyleRolloutId: 'production-bip-v3',
      visible: false,
      size: 'auto',
      position: { xPct: 20, yPct: 30 },
      landingPosition: { xPct: 40, yPct: 50 },
    });
    store.setStyle('billes');
    const chosen = useEyesWidgetStore.getState();
    store.applyAvatarStyleRollout('production-bip-v3');
    expect(useEyesWidgetStore.getState()).toBe(chosen);
    store.applyAvatarStyleRollout('production-bip-v4');
    expect(useEyesWidgetStore.getState().style).toBe('bip');
  });

  it.each(['', ' ', 'https://invalid.example', 'x'.repeat(81)])(
    'ignores invalid campaign %j without writing a preference',
    id => {
      useEyesWidgetStore.getState().setStyle('cozmo');
      const before = localStorage.getItem(EYES_WIDGET_PREFS_KEY);
      useEyesWidgetStore.getState().applyAvatarStyleRollout(id);
      expect(localStorage.getItem(EYES_WIDGET_PREFS_KEY)).toBe(before);
      expect(useEyesWidgetStore.getState().style).toBe('cozmo');
    }
  );

  it('a manual display reset does not forget the applied campaign', () => {
    useEyesWidgetStore.getState().applyAvatarStyleRollout('production-bip-v3');
    useEyesWidgetStore.getState().reset();
    useEyesWidgetStore.getState().setStyle('cozmo');
    useEyesWidgetStore.getState().applyAvatarStyleRollout('production-bip-v3');
    expect(useEyesWidgetStore.getState().style).toBe('cozmo');
  });

  it('reads legacy unversioned preferences without resetting them or needing a migration', async () => {
    localStorage.setItem(
      EYES_WIDGET_PREFS_KEY,
      JSON.stringify({ state: { style: 'cozmo', visible: false, size: 'sm' } })
    );
    await useEyesWidgetStore.persist.rehydrate();
    expect(useEyesWidgetStore.getState()).toMatchObject({
      style: 'cozmo',
      visible: false,
      size: 'sm',
      appliedAvatarStyleRolloutId: null,
    });
  });

  it('keeps the applied campaign when the person subsequently chooses another character', async () => {
    localStorage.setItem(
      EYES_WIDGET_PREFS_KEY,
      JSON.stringify({
        state: {
          visible: false,
          size: 'sm',
          style: 'bip',
          position: { xPct: 20, yPct: 30 },
          landingPosition: { xPct: 40, yPct: 50 },
          appliedAvatarStyleRolloutId: 'production-bip-v3',
        },
        version: 0,
      })
    );
    await useEyesWidgetStore.persist.rehydrate();
    useEyesWidgetStore.getState().setStyle('cozmo');
    expect(JSON.parse(localStorage.getItem(EYES_WIDGET_PREFS_KEY) ?? '{}')).toMatchObject({
      state: { style: 'cozmo', appliedAvatarStyleRolloutId: 'production-bip-v3' },
    });
  });
});
