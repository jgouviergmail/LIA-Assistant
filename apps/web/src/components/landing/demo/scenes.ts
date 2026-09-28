import { BellRing, CalendarCheck2, FileSearch, Handshake, PhoneCall, Radio } from 'lucide-react';

/** One scene catalogue for the live demo and the chapter illustrations. */
const SCENE_DEFINITIONS = [
  { id: 'decision', icon: CalendarCheck2, sources: ['space', 'mail', 'meeting'] },
  { id: 'day', icon: Radio, sources: ['calendar', 'commitment', 'news'] },
  { id: 'watch', icon: BellRing, sources: ['routine', 'mail', 'project'] },
  { id: 'call', icon: PhoneCall, sources: ['calendar', 'preferences', 'approval'] },
  { id: 'research', icon: FileSearch, sources: ['web', 'space', 'comparison'] },
  { id: 'relay', icon: Handshake, sources: ['peer', 'scope', 'calendar'] },
] as const;

export type ProductSceneId = (typeof SCENE_DEFINITIONS)[number]['id'];
export type ProductScenePhase = 0 | 1 | 2;
export const PRODUCT_DEMO_KEY = 'landing.product_demo';
export const PRODUCT_SCENES = SCENE_DEFINITIONS.map(scene => ({
  ...scene,
  titleKey: `${PRODUCT_DEMO_KEY}.scenes.${scene.id}.title`,
  summaryKey: `${PRODUCT_DEMO_KEY}.scenes.${scene.id}.summary`,
  outcomeKey: `${PRODUCT_DEMO_KEY}.scenes.${scene.id}.result_title`,
}));

export function productScene(id: ProductSceneId) {
  return PRODUCT_SCENES.find(scene => scene.id === id) ?? PRODUCT_SCENES[0];
}
