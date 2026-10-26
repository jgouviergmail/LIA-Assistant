import { project } from '../geometry';
import { lifeBudget } from '../world-life';
import type { Atmosphere } from '../atmosphere';
import type { WorldDefinition, Quality } from '../types';
export function paintAmbientLife(
  c: CanvasRenderingContext2D,
  world: WorldDefinition,
  a: Atmosphere,
  time: number,
  q: Quality,
  reduced: boolean
): void {
  const budget = lifeBudget(a, q, reduced),
    garden = world.zones.find(z => z.id === 'garden');
  if (!garden) return;
  c.save();
  c.strokeStyle = '#243744';
  c.lineWidth = 1.5;
  c.lineCap = 'round';
  for (let i = 0; i < budget.birds; i++) {
    const at = project(
      {
        x: garden.x + garden.width / 2 + Math.sin(time * 0.09 + i) * 8,
        y: garden.y + 12 + Math.cos(time * 0.07 + i) * 6,
      },
      4 + i * 0.4
    );
    const wing = 2 + Math.sin(time * 5 + i) * 3;
    c.beginPath();
    c.moveTo(at.x - 5, at.y - wing);
    c.quadraticCurveTo(at.x - 2, at.y, at.x, at.y);
    c.quadraticCurveTo(at.x + 2, at.y, at.x + 5, at.y - wing);
    c.stroke();
  }
  for (let i = 0; i < budget.butterflies; i++) {
    const at = project(
      {
        x: garden.x + 3 + i * 4 + Math.sin(time * 0.5 + i) * 0.7,
        y: garden.y + 7 + Math.cos(time * 0.4 + i) * 1.3,
      },
      0.8 + Math.sin(time * 0.8 + i) * 0.2
    );
    const wing = 1.4 + Math.abs(Math.sin(time * 7 + i)) * 2;
    c.fillStyle = ['#f5bb43', '#e37db4', '#75cfda', '#b294ef'][i];
    c.beginPath();
    c.ellipse(at.x - wing / 2, at.y, wing, 1.8, -0.5, 0, Math.PI * 2);
    c.fill();
    c.beginPath();
    c.ellipse(at.x + wing / 2, at.y, wing, 1.8, 0.5, 0, Math.PI * 2);
    c.fill();
  }
  c.restore();
}
