import { project } from '../geometry';
import { ambientLifeAt, type AmbientAgent } from '../world-life';
import type { CosmeticFrame } from '../cosmetic-effects';
import type { Atmosphere } from '../atmosphere';
import type { WorldDefinition, Quality } from '../types';
export function paintAmbientLife(
  c: CanvasRenderingContext2D,
  world: WorldDefinition,
  a: Atmosphere,
  time: number,
  q: Quality,
  reduced: boolean,
  agents: readonly AmbientAgent[] = ambientLifeAt(world, a, time, q, reduced),
  reactions: ReadonlyMap<string, CosmeticFrame> = new Map()
): void {
  c.save();
  c.strokeStyle = '#243744';
  c.lineWidth = 1.5;
  c.lineCap = 'round';
  for (const bird of agents.filter(agent => agent.action === 'bird')) {
    const i = bird.index;
    const at = project(bird.point, bird.elevation);
    const reaction = reactions.get(bird.id);
    if (reaction) at.y -= Math.sin(reaction.phase * Math.PI) * 9;
    const wing = 2 + Math.sin(time * 5 + i) * 3;
    c.beginPath();
    c.moveTo(at.x - 5, at.y - wing);
    c.quadraticCurveTo(at.x - 2, at.y, at.x, at.y);
    c.quadraticCurveTo(at.x + 2, at.y, at.x + 5, at.y - wing);
    c.stroke();
  }
  for (const butterfly of agents.filter(agent => agent.action === 'butterfly')) {
    const i = butterfly.index;
    const at = project(butterfly.point, butterfly.elevation);
    const reaction = reactions.get(butterfly.id);
    if (reaction) {
      at.x += Math.sin(reaction.phase * Math.PI) * 15;
      at.y -= Math.sin(reaction.phase * Math.PI) * 4;
    }
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
