/** Absolute-time beats, bounded per owner runtime. No particles, physics or timers. */
import type { CosmeticTarget } from './cosmetic-interactions';
import type { Quality } from './types';
export interface CosmeticFrame extends CosmeticTarget {
  readonly phase: number;
}
interface Beat {
  target: CosmeticTarget;
  started: number;
}
export function cosmeticDuration(action: CosmeticTarget['action']): number {
  if (action === 'pond') return 7600;
  if (action === 'workout') return 5200;
  if (action === 'machine') return 3600;
  return action === 'fountain' ? 2400 : 1600;
}
const limit = (quality: Quality) => (quality === 'low' ? 3 : 8);
const COOLDOWNS_RETAINED = 128;
export class CosmeticEffects {
  private beats: Beat[] = [];
  private cooldowns = new Map<string, number>();
  /** Per-object cooldowns still held; never more than the bounded history. */
  get remembered(): number {
    return this.cooldowns.size;
  }
  activate(target: CosmeticTarget, now: number, visible: boolean, quality: Quality): boolean {
    if (!visible || !Number.isFinite(now + target.point.x + target.point.y + target.elevation))
      return false;
    this.prune(now, quality);
    if (this.beats.length >= limit(quality) || now < (this.cooldowns.get(target.id) ?? -Infinity))
      return false;
    this.cooldowns.delete(target.id);
    this.cooldowns.set(target.id, now + Math.max(2000, cosmeticDuration(target.action)));
    if (this.cooldowns.size > COOLDOWNS_RETAINED)
      this.cooldowns.delete(this.cooldowns.keys().next().value ?? '');
    this.beats.push({ target: { ...target, point: { ...target.point } }, started: now });
    return true;
  }
  private prune(now: number, quality: Quality): void {
    this.beats = this.beats
      .filter(
        beat => now >= beat.started && now - beat.started < cosmeticDuration(beat.target.action)
      )
      .slice(-limit(quality));
  }
  frames(now: number, quality: Quality): readonly CosmeticFrame[] {
    if (!Number.isFinite(now)) return [];
    this.prune(now, quality);
    return this.beats.map(beat => ({
      ...beat.target,
      phase: (now - beat.started) / cosmeticDuration(beat.target.action),
    }));
  }
  clear(): void {
    this.beats = [];
    this.cooldowns.clear();
  }
  cancel(id: string): void {
    this.beats = this.beats.filter(beat => beat.target.id !== id);
    // An interrupted reaction never happened: choosing the object again must replay it,
    // or a re-chosen bench would lie down and stand straight back up.
    this.cooldowns.delete(id);
  }
}
