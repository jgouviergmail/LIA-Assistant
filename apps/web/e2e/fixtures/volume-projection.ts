import { expect, type Locator } from '@playwright/test';

/** Read the real GPU pose and native channels; no synthetic geometry or writes. */
export async function expectVolumeProjection(face: Locator) {
  const view = await face.evaluate(root => {
    const canvas = root.querySelector<HTMLCanvasElement>('[data-volume-canvas]');
    const gl = canvas?.getContext('webgl');
    const program = gl?.getParameter(gl.CURRENT_PROGRAM);
    if (!gl || !program) throw new Error('The active companion must paint its native volume');
    const location = gl.getUniformLocation(program, 'u_pose');
    if (!location) throw new Error('The body must expose its actual painted pose');
    const pose = gl.getUniform(program, location);
    if (!(pose instanceof Float32Array)) throw new Error('The native pose must be a vector');
    const channel = (key: string) =>
      Number.parseFloat((root as HTMLElement).style.getPropertyValue(`--rig-${key}`));
    return {
      character: root.getAttribute('data-volume-character'),
      ready: root.getAttribute('data-volume-ready'),
      yaw: channel('head-yaw'),
      pitch: channel('head-pitch'),
      paintedYaw: pose[0],
      paintedPitch: pose[1],
      width: canvas!.width,
      height: canvas!.height,
    };
  });
  const monitor = view.character === 'monitor';
  expect(view.ready).toBe('true');
  expect(view.width).toBe(view.height);
  expect(view.width).toBeGreaterThan(0);
  expect(view.width).toBeLessThanOrEqual(192);
  expect(view.paintedYaw).toBeCloseTo(
    (Math.max(-1.3, Math.min(1.3, view.yaw)) * (monitor ? 22 : 16) * Math.PI) / 180,
    3
  );
  expect(view.paintedPitch).toBeCloseTo(
    (Math.max(-1.3, Math.min(1.3, view.pitch)) * (monitor ? -14 : -10) * Math.PI) / 180,
    3
  );
}
