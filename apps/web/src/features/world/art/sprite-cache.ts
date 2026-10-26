/** Byte-bounded LRU for user-selectable actor combinations. Owns every retained surface. */
import type { Sprite } from './painter';
export function freeSprite(sprite: Sprite): void {
  sprite.canvas.width = sprite.canvas.height = 0;
}
export class SpriteCache {
  private values = new Map<string, { sprite: Sprite; bytes: number }>();
  private used = 0;
  constructor(
    private maxBytes: number,
    private maxEntries: number
  ) {}
  get bytes(): number {
    return this.used;
  }
  get(key: string, factory: () => Sprite): Sprite {
    const found = this.values.get(key);
    if (found) {
      this.values.delete(key);
      this.values.set(key, found);
      return found.sprite;
    }
    const sprite = factory();
    const bytes = sprite.canvas.width * sprite.canvas.height * 4;
    if (bytes > this.maxBytes) {
      freeSprite(sprite);
      throw new Error('world_actor_texture_limit');
    }
    this.values.set(key, { sprite, bytes });
    this.used += bytes;
    for (const [oldKey, entry] of this.values) {
      if (this.used <= this.maxBytes && this.values.size <= this.maxEntries) break;
      this.values.delete(oldKey);
      this.used -= entry.bytes;
      freeSprite(entry.sprite);
    }
    return sprite;
  }
  clear(): void {
    for (const entry of this.values.values()) freeSprite(entry.sprite);
    this.values.clear();
    this.used = 0;
  }
}
