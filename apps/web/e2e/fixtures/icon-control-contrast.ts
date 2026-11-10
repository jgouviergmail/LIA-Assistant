/** Browser-resolved contrast of the informative lines of selected icon controls. */
import type { Locator, TestInfo } from '@playwright/test';
import { expect } from '@playwright/test';
import { blend, contrast, type Rgb } from '../../src/styles/__tests__/contrast-math';

export async function expectDarkIconControlContrast(
  button: Locator,
  testInfo: TestInfo,
  state: 'active' | 'idle-hover' | 'active-hover' = 'active'
) {
  const paints = await button.evaluate(element => {
    const svg = element.querySelector('svg[data-icon-name]');
    if (!svg) throw new Error('The selected control must contain its real icon');
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = 1;
    const context = canvas.getContext('2d');
    if (!context) throw new Error('A canvas is needed to resolve the browser color space');
    const rgba = (color: string) => {
      context.clearRect(0, 0, 1, 1);
      context.fillStyle = color;
      context.fillRect(0, 0, 1, 1);
      return Array.from(context.getImageData(0, 0, 1, 1).data);
    };
    const strokes = Array.from(svg.querySelectorAll('[stroke^="#"]')).map(node => ({
      color: getComputedStyle(node).stroke,
      opacity: getComputedStyle(node).strokeOpacity,
      rgba: rgba(getComputedStyle(node).stroke),
    }));
    const stops = Array.from(svg.querySelectorAll('linearGradient stop')).map(node => ({
      color: getComputedStyle(node).stopColor,
      opacity: getComputedStyle(node).stopOpacity,
      rgba: rgba(getComputedStyle(node).stopColor),
    }));
    const background = getComputedStyle(element).backgroundColor;
    const ownRgba = rgba(background);
    const ancestors: Element[] = [];
    for (let ancestor: Element | null = element; ancestor; ancestor = ancestor.parentElement) {
      ancestors.unshift(ancestor);
    }
    context.clearRect(0, 0, 1, 1);
    context.fillStyle = 'white';
    context.fillRect(0, 0, 1, 1);
    const layers = ancestors.map(ancestor => getComputedStyle(ancestor).backgroundColor);
    for (const layer of layers) {
      context.fillStyle = layer;
      context.fillRect(0, 0, 1, 1);
    }
    return {
      name: svg.getAttribute('data-icon-name'),
      style: svg.getAttribute('data-icon-style'),
      background,
      ownRgba,
      layers,
      rgba: Array.from(context.getImageData(0, 0, 1, 1).data),
      strokes,
      stops,
    };
  });
  const rgb = (rgba: number[]): Rgb => [rgba[0] / 255, rgba[1] / 255, rgba[2] / 255];
  let informative: Rgb[];
  if (paints.name === 'RefreshCw' && paints.style === 'fluent') {
    expect(paints.stops).toHaveLength(2);
    for (const stop of paints.stops) {
      expect(stop.opacity).toBe('1');
      expect(stop.rgba[3]).toBe(255);
    }
    informative = Array.from({ length: 21 }, (_, index) =>
      blend(rgb(paints.stops[1].rgba), rgb(paints.stops[0].rgba), index / 20)
    );
  } else {
    expect(
      paints.strokes.length,
      'The real icon must expose its informative contours'
    ).toBeGreaterThan(0);
    for (const stroke of paints.strokes) {
      expect(stroke.opacity).toBe('1');
      expect(stroke.rgba[3]).toBe(255);
    }
    informative = paints.strokes.map(stroke => rgb(stroke.rgba));
  }
  const ratios = informative.map(color => contrast(color, rgb(paints.rgba)));
  await testInfo.attach(`${paints.name}-${paints.style}-${state}-contrast.json`, {
    body: JSON.stringify({ ...paints, ratios }, null, 2),
    contentType: 'application/json',
  });
  for (const ratio of ratios)
    expect(ratio, `${paints.name} on its actual active background`).toBeGreaterThanOrEqual(3);
  expect(
    paints.ownRgba[3],
    'The selected dark surface is opaque, independent of its container'
  ).toBe(255);
}
