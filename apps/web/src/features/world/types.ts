/** Local world contracts. No application data or renderer object belongs here. */
import type { ActivityKey } from './activity-catalogue';
import type { SceneTarget } from './scene-interactions';
import type { Facing } from './art/actor-direction';
import type { PoseSlot } from './pose-slots';
export interface Point {
  x: number;
  y: number;
}
export interface Size {
  width: number;
  height: number;
}
export interface Rect extends Point, Size {}
export type ZoneId =
  | 'garden'
  | 'arrival'
  | 'library'
  | 'home'
  | 'meeting'
  | 'multimedia'
  | 'phone'
  | 'memory'
  | 'cafeteria'
  | 'engineering'
  | 'gym'
  | 'divination'
  | 'restroom'
  | 'terrace';
export type Tone = 'sage' | 'teal' | 'clay' | 'violet' | 'amber' | 'cream';
export type Ground =
  | 'grass'
  | 'path'
  | 'wood'
  | 'tile'
  | 'deck'
  | 'water'
  | 'marble'
  | 'violet-carpet'
  | 'carpet'
  | 'checker'
  | 'slate';
export type PropKind =
  | 'pond'
  | 'sidetable'
  | 'waterlily'
  | 'sink'
  | 'tablelamp'
  | 'rock'
  | 'reeds'
  | 'cat'
  | 'bench'
  | 'display'
  | 'billiards'
  | 'arcade'
  | 'poster'
  | 'drawingtable'
  | 'wallphone'
  | 'callbook'
  | 'archive'
  | 'readingdesk'
  | 'bar'
  | 'bottles'
  | 'jukebox'
  | 'labtable'
  | 'machine'
  | 'weightbench'
  | 'dumbbells'
  | 'mirror'
  | 'crystal'
  | 'toilet'
  | 'lounger'
  | 'vegetable'
  | 'nightstand'
  | 'alarm'
  | 'promiseboard'
  | 'partition'
  | 'parasol'
  | 'wallCorner'
  | 'wall'
  | 'sideWall'
  | 'window'
  | 'sideWindow'
  | 'desk'
  | 'chair'
  | 'shelf'
  | 'plant'
  | 'tree'
  | 'sofa'
  | 'table'
  | 'lamp'
  | 'planter'
  | 'fountain'
  | 'sign'
  | 'telescope'
  | 'easel'
  | 'bed'
  | 'flowers'
  | 'mosaic'
  | 'rug'
  | 'beam'
  | 'noticeboard'
  | 'mailbox'
  | 'telephone'
  | 'calendar'
  | 'clock'
  | 'herbarium'
  | 'writingdesk'
  | 'meetingtable'
  | 'radio'
  | 'counter'
  | 'parcels';
export type WallFinish = 'plaster' | 'oak' | 'brick' | 'glass' | 'acoustic' | 'slate';
export interface WorldProp extends Point {
  /** Public bounded architectural family, never account content. */
  support?: string;
  wallFinish?: WallFinish;
  wallConnections?: number;
  wallWindow?: boolean;
  /** Stable authored identity for interactions; independent of placement. */
  key?: string;
  /** Optional linked activity, including a chair whose confirmed pose opens it. */
  activity?: ActivityKey;
  facing?: Facing;
  id: string;
  kind: PropKind;
  width: number;
  depth: number;
  height: number;
  tone: Tone;
  blocking: boolean;
}
export interface GroundPatch extends Rect {
  kind: Ground;
}
export interface WorldZone extends Rect {
  /** Cosmetic shelter is authored independently of flooring or wall material. */
  covered?: boolean;
  id: ZoneId;
  tone: Tone;
  arrival: Point;
}
export interface WorldDefinition extends Size {
  movement?: { readonly walk: number; readonly run: number };
  id: string;
  version: number;
  spawn: Point;
  bipSpawn: Point;
  patrol: readonly Point[];
  zones: readonly WorldZone[];
  grounds: readonly GroundPatch[];
  props: readonly WorldProp[];
}
export interface Actor {
  publicId?: string;
  appearance?: import('./avatar-catalogue').AvatarAppearance;
  label?: string;
  running?: boolean;
  pose?: PoseSlot | null;
  /** Local visual heading, derived from motion; never private or authoritative state. */
  heading?: number;
  position: Point;
  facing: number;
  walking: boolean;
  phase: number;
  path: Point[];
}
export interface Visitor extends Actor {
  id: string;
  label: string;
  from: Point;
  target: Point;
  blend: number;
}
export interface Camera extends Size {
  center: Point;
  zoom: number;
  following: boolean;
}
export type Quality = 'low' | 'balanced' | 'high';
export interface WorldMetrics {
  fps: number;
  frameP95: number;
  renderP95: number;
  sprites: number;
  textureBytes: number;
}
export interface WorldSnapshot {
  hover?: import('./scene-pointer').SceneHover | null;
  nearby?: SceneTarget | null;
  player: Point;
  bip: Point;
  zone: ZoneId;
  zoom: number;
  following: boolean;
  bipFollowing: boolean;
  metrics: WorldMetrics;
}
