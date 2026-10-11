import { describe, expect, it, vi } from 'vitest';
import { createVolumeSurfaceWriter } from '../volume-writer';
import { restChannelValues } from '../../rig/channels';

function host(character = 'oscar', variant = 'female') {
  const root = document.createElement('span');
  root.dataset.volumeCharacter = character;
  root.dataset.volumeVariant = variant;
  root.dataset.volumeReady = 'true';
  root.style.setProperty('--eye-w', '.385em');
  root.style.setProperty('--eye-gap', '.075em');
  root.style.setProperty('--companion-eye-y', variant === 'female' ? '35.4%' : '33.6%');
  root.style.setProperty('--companion-mouth-y', '50%');
  root.innerHTML =
    '<span data-volume-surface="left"></span><span data-volume-surface="right"></span><span data-volume-surface="mouth"></span>';
  document.body.append(root);
  return root;
}

describe('the same native frame attaches all organs to anatomical depth', () => {
  it.each(['male', 'female'])(
    'keeps Oscar %s eye sockets fixed during extreme eye movements',
    variant => {
      const root = host('oscar', variant);
      const writer = createVolumeSurfaceWriter(root);
      const eyes = [...root.querySelectorAll<HTMLElement>('[data-volume-surface]')].slice(0, 2);
      for (const headYaw of [-1.3, 0, 1.3]) {
        for (const headPitch of [-1.3, 0, 1.3]) {
          const pose = { ...restChannelValues(), headYaw, headPitch };
          writer.write(pose);
          const registered = eyes.map(eye => eye.style.transform);
          const matrices = registered.map(transform =>
            transform
              .match(/matrix\(([^)]+)\)/)![1]
              .split(',')
              .map(Number)
          );
          // Both globes belong to the same skull. A cheek's tangent must not
          // enlarge one eye and squash the other when the head turns.
          expect(matrices[0]).toEqual(matrices[1]);
          expect(Math.hypot(matrices[0][0], matrices[0][1])).toBeLessThanOrEqual(1.0001);
          expect(Math.hypot(matrices[0][2], matrices[0][3])).toBeLessThanOrEqual(1.0001);
          expect(matrices[0][0] * matrices[0][3] - matrices[0][1] * matrices[0][2]).toBeGreaterThan(
            0.9
          );
          for (const direction of [-1.3, 0, 1.3]) {
            writer.write({
              ...pose,
              gazeX: direction,
              gazeY: -direction,
              txL: direction * 0.1,
              txR: -direction * 0.1,
              tyL: direction * 0.1,
              tyR: -direction * 0.1,
            });
            expect(eyes.map(eye => eye.style.transform)).toEqual(registered);
          }
        }
      }
      writer.dispose();
      root.remove();
    }
  );

  it('preserves exact neutral registration, reads current CSS eye geometry, then projects every organ', () => {
    const root = host();
    const writer = createVolumeSurfaceWriter(root);
    const values = restChannelValues();
    writer.write(values);
    const organs = [...root.querySelectorAll<HTMLElement>('[data-volume-surface]')];
    expect(organs.every(organ => organ.style.transform.includes('matrix(1, 0, 0, 1'))).toBe(true);
    const queries = vi.spyOn(root, 'querySelectorAll');
    writer.write({ ...values, headYaw: 1, headPitch: -0.8 });
    expect(organs.every(organ => !organ.style.transform.includes('matrix(1, 0, 0, 1'))).toBe(true);
    expect(organs[0].style.transform).not.toBe(organs[1].style.transform);
    expect(organs[2].style.transformOrigin).toBe('50% 50%');
    expect(queries).not.toHaveBeenCalled();
    writer.dispose();
  });

  it('retains the authored moving surface and expression shifts for non-human companions', () => {
    const root = host('spirit');
    const writer = createVolumeSurfaceWriter(root);
    const pose = { ...restChannelValues(), headYaw: 1.3, headPitch: -1.3 };
    const eyes = [...root.querySelectorAll<HTMLElement>('[data-volume-surface]')].slice(0, 2);
    writer.write(pose);
    const registered = eyes.map(eye => eye.style.transform);
    writer.write({ ...pose, gazeX: 1, gazeY: -1, txL: 0.08, txR: -0.08 });
    expect(eyes.map(eye => eye.style.transform)).not.toEqual(registered);
    writer.dispose();
    root.remove();
  });

  it('clears projection on fallback and reacquires current nodes at a same-skin character switch', () => {
    const root = host();
    const writer = createVolumeSurfaceWriter(root);
    const values = { ...restChannelValues(), headYaw: 1 };
    writer.write(values);
    const old = root.querySelector<HTMLElement>('[data-volume-surface]')!;
    root.dataset.volumeReady = 'false';
    writer.write(values);
    expect(old.style.transform).toBe('');
    root.dataset.volumeCharacter = 'orbit';
    root.dataset.volumeReady = 'true';
    root.innerHTML = '<span data-volume-surface="left"></span>';
    writer.write(values);
    expect(root.firstElementChild?.getAttribute('style')).toContain('matrix');
    writer.dispose();
    expect(root.firstElementChild?.getAttribute('style')).not.toContain('matrix');
  });

  it('projects the monitor screen boundary and its free brows together instead of slipping organs out of the glass', () => {
    const root = host('monitor');
    root.innerHTML =
      '<span class="lia-monitor-screen"><span data-volume-surface="left"/></span><span class="lia-monitor-brows"><span data-volume-surface="left"/></span>';
    root.style.setProperty('--screen-top', '22.2807%');
    root.style.setProperty('--screen-height', '38.5965%');
    const writer = createVolumeSurfaceWriter(root);
    writer.write({ ...restChannelValues(), headYaw: 1 });
    const screen = root.querySelector<HTMLElement>('.lia-monitor-screen')!;
    const brows = root.querySelector<HTMLElement>('.lia-monitor-brows')!;
    expect(screen.style.transform).toContain('matrix');
    expect(screen.style.transform).toBe(brows.style.transform);
    expect(root.querySelector<HTMLElement>('[data-volume-surface]')!.style.transform).toBe('');
    writer.dispose();
  });
});
