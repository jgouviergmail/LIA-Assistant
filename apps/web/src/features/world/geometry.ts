import type { Camera, Point, Size } from './types';
export const TILE_WIDTH = 64;
export const TILE_HEIGHT = 32;
export const MIN_ZOOM = 0.55;
export const MAX_ZOOM = 1.8;
export function project(point: Point, height = 0): Point {
  return { x: (point.x - point.y) * 32, y: (point.x + point.y) * 16 - height * 32 };
}
export function unproject(point: Point): Point {
  return { x: point.x / 64 + point.y / 32, y: point.y / 32 - point.x / 64 };
}
export function createCamera(size: Size, target: Point): Camera {
  return { ...size, center: project(target), zoom: 0.95, following: true };
}
export function worldToScreen(point: Point, camera: Camera): Point {
  const p = project(point);
  return {
    x: (p.x - camera.center.x) * camera.zoom + camera.width / 2,
    y: (p.y - camera.center.y) * camera.zoom + camera.height / 2,
  };
}
export function screenToWorld(point: Point, camera: Camera): Point {
  return unproject({
    x: (point.x - camera.width / 2) / camera.zoom + camera.center.x,
    y: (point.y - camera.height / 2) / camera.zoom + camera.center.y,
  });
}
export function zoomCamera(camera: Camera, zoom: number, anchor: Point): void {
  if (!Number.isFinite(zoom) || !Number.isFinite(anchor.x + anchor.y)) return;
  const before = project(screenToWorld(anchor, camera));
  camera.zoom = Math.min(MAX_ZOOM, Math.max(MIN_ZOOM, zoom));
  camera.center = {
    x: before.x - (anchor.x - camera.width / 2) / camera.zoom,
    y: before.y - (anchor.y - camera.height / 2) / camera.zoom,
  };
}
export function panCamera(camera: Camera, delta: Point): void {
  if (!Number.isFinite(delta.x + delta.y)) return;
  camera.following = false;
  camera.center.x -= delta.x / camera.zoom;
  camera.center.y -= delta.y / camera.zoom;
}
