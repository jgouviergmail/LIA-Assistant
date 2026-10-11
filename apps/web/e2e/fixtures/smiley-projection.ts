import { expect, type Locator } from '@playwright/test';

/** Read both rendering pipelines; never write channels, matrices or GPU state. */
export async function expectSmileyProjection(face: Locator) {
  const view = await face.evaluate(root => {
    const body = root.querySelector<HTMLElement>('.lia-avatar-body')!;
    const canvas = body.querySelector('canvas')!;
    const gl = canvas.getContext('webgl');
    const program = gl?.getParameter(gl.CURRENT_PROGRAM);
    if (!gl || !program) throw new Error('The visible Smiley must use its actual GPU program');
    const location = gl.getUniformLocation(program, 'u_state');
    if (!location) throw new Error('The actual sphere head uniform is required');
    const state = gl.getUniform(program, location);
    if (!(state instanceof Float32Array))
      throw new Error('The sphere must publish its painted head pose');
    const channel = (name: string) =>
      Number.parseFloat((root as HTMLElement).style.getPropertyValue(`--rig-${name}`));
    const organs = [
      ...root.querySelectorAll<HTMLElement>('.lia-raster-face-mask [data-smiley-surface]'),
    ].map(node => {
      const matrix = new DOMMatrix(getComputedStyle(node).transform);
      return { kind: node.dataset.smileySurface, scaleX: matrix.a, x: matrix.e, y: matrix.f };
    });
    const box = body.getBoundingClientRect();
    return {
      ready: body.dataset.sphereReady,
      diameterX: box.width,
      diameterY: box.height,
      bufferX: canvas.width,
      bufferY: canvas.height,
      nativeYaw: channel('head-yaw'),
      nativePitch: channel('head-pitch'),
      gpuYaw: state[0],
      gpuPitch: state[1],
      organs,
    };
  });
  expect(view.ready).toBe('true');
  expect(Math.abs(view.diameterX - view.diameterY)).toBeLessThan(0.05);
  expect(view.bufferX).toBe(view.bufferY);
  expect(view.gpuYaw).toBeCloseTo(
    (Math.max(-1.3, Math.min(1.3, view.nativeYaw)) * 16 * Math.PI) / 180,
    3
  );
  expect(view.gpuPitch).toBeCloseTo(
    (Math.max(-1.3, Math.min(1.3, view.nativePitch)) * -10 * Math.PI) / 180,
    3
  );
  expect(view.organs.map(organ => organ.kind).sort()).toEqual(['left', 'mouth', 'right']);
  if (Math.abs(view.nativeYaw) > 0.2) {
    const direction = Math.sign(view.nativeYaw);
    const left = view.organs.find(organ => organ.kind === 'left')!;
    const right = view.organs.find(organ => organ.kind === 'right')!;
    // The near eye widens relative to the far eye on a curved surface. A
    // shared flat CSS plane or stationary mouth cannot satisfy these reads.
    expect((left.scaleX - right.scaleX) * direction).toBeGreaterThan(0.015);
    for (const organ of view.organs) expect(organ.x * direction).toBeGreaterThan(0.1);
  }
  return view;
}
