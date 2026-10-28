/** Room inventories carry public semantic bindings, never private account content. */
import { associateTables, furnish, type Furnishing } from './house-authoring';
import { HOUSE_ZONES, HOUSE_WALLS } from './house-layout';
import { mountWallArt } from './wall-mounts';
import type { ZoneId, WorldProp } from './types';

const ROOMS: Record<ZoneId, Furnishing[]> = {
  garden: [],
  terrace: [],
  arrival: [
    ['table', 13, 20, 2, 2, 0.8, 'cream', 'atrium-table'],
    ['smartphone', 13.65, 20.6, 0.6, 0.45, 1.7, 'teal', 'sms-stand', 1, 'sms', 'table:36:38'],
    ['chair', 13.5, 18, 1, 1, 1.2, 'teal', 'atrium-n', 1],
    ['chair', 13.5, 23, 1, 1, 1.2, 'teal', 'atrium-s', 3],
    ['fountain', 7, 7, 3, 3, 1.1, 'teal'],
    ['bench', 7, 3, 3, 1, 1.1, 'teal', 'hall-north', 1],
    ['bench', 7, 12, 3, 1, 1.1, 'teal', 'hall-south', 3],
    ['bench', 3, 7, 1, 3, 1.1, 'teal', 'hall-west', 0],
    ['bench', 13, 7, 1, 3, 1.1, 'teal', 'hall-east', 2],
    ['plant', 2, 2, 1, 1, 1.8, 'sage'],
    ['plant', 15, 2, 1, 1, 1.8, 'sage'],
    ['plant', 2, 16, 1, 1, 1.8, 'sage'],
    ['plant', 15, 28, 1, 1, 1.8, 'sage'],
    ['lamp', 5, 3, 0.4, 0.4, 2.2, 'amber'],
    ['lamp', 12, 12, 0.4, 0.4, 2.2, 'amber'],
    ['noticeboard', 2, 17, 2, 1, 2.2, 'teal', 'peers'],
  ],
  meeting: [
    ['meetingtable', 5, 3, 3, 6, 1.1, 'teal', 'meetings', 0, 'meetings'],
    ['chair', 6, 10, 1, 1, 1.3, 'teal', 'meeting-boss', 3, 'meetings'],
    ['display', 5, 0.35, 3, 0.25, 2.8, 'teal', undefined, 1],
    ['plant', 1, 1, 1, 1, 1.8, 'sage'],
    ['plant', 1, 12, 1, 1, 1.8, 'sage'],
    ['lamp', 1, 9, 0.4, 0.4, 2.2, 'amber'],
    ['sofa', 2, 14.5, 4, 1, 1.25, 'teal', 'meeting-lounge', 3],
    ['table', 7.5, 14.5, 2, 1.5, 0.8, 'cream', 'meeting-lounge-table', 1, 'news'],
    ['plant', 12, 15.5, 1, 1, 1.6, 'sage'],
    ['rug', 1, 13, 10, 4.5, 0.05, 'teal'],
  ],
  multimedia: [
    ['billiards', 7, 4, 5, 3, 1.1, 'sage'],
    ['arcade', 10, 1, 1.5, 1.5, 2.6, 'violet', 'arcade-tic-tac-toe'],
    ['arcade', 12, 1, 1.5, 1.5, 2.6, 'teal', 'arcade-four-in-row'],
    ['arcade', 14, 1, 1.5, 1.5, 2.6, 'clay', 'arcade-reversi'],
    ['poster', 1, 0.4, 2, 0.12, 2.7, 'violet'],
    ['poster', 7, 0.4, 2, 0.12, 2.7, 'clay'],
    ['plant', 16, 1, 1, 1, 1.7, 'sage'],
    ['plant', 16, 14, 1, 1, 1.7, 'sage'],
    ['sofa', 12, 8, 4, 1, 1.25, 'clay', 'media-sofa-n', 1],
    ['sofa', 12, 13, 4, 1, 1.25, 'violet', 'media-sofa-s', 3],
    ['table', 13, 10, 2, 1.5, 0.8, 'violet', 'media-lounge-table'],
    ['rug', 11, 7, 6, 8, 0.06, 'violet'],
    ['drawingtable', 6, 11, 4, 2, 1.1, 'cream', 'generate-image', 1, 'generate-image'],
    ['chair', 7, 9, 1, 1, 1.2, 'clay', 'draw-n', 1, 'generate-image'],
    ['chair', 7, 14, 1, 1, 1.2, 'clay', 'draw-s', 3, 'generate-image'],
    ['lamp', 16, 10, 0.4, 0.4, 2.2, 'amber'],
  ],
  phone: [
    ['wallphone', 3.3, 0.35, 1, 0.45, 2.5, 'teal', 'phone', 1, 'phone'],
    ['chair', 3.3, 2, 1, 1, 1.2, 'teal', 'phone-seat', 3, 'phone'],
    ['callbook', 1.05, 3.2, 1, 1.6, 1, 'amber', 'recent-calls', 0, 'recent-calls'],
    ['plant', 6, 1, 1, 1, 1.6, 'sage'],
    ['poster', 4.3, 0.3, 1.4, 0.12, 2.4, 'teal'],
  ],
  memory: [
    ['archive', 1, 1, 4, 1, 2.6, 'amber', 'archive-0', 1, 'memories'],
    ['archive', 6, 1, 4, 1, 2.6, 'amber', 'archive-1', 1, 'memories'],
    ['archive', 11, 1, 4, 1, 2.6, 'amber', 'archive-2', 1, 'memories'],
    ['plant', 16, 1, 1, 1, 1.8, 'sage'],
    ['lamp', 16, 9, 0.4, 0.4, 2.2, 'amber'],
  ],
  cafeteria: [
    ['bar', 15, 2, 1.5, 8, 1.3, 'clay', undefined, 2],
    ['bottles', 17.5, 3, 0.35, 6, 2.8, 'clay', undefined, 2],
    ['jukebox', 8, 1.05, 1.5, 1, 2.5, 'clay', 'radio', 1, 'radio'],
    ['plant', 16, 1, 1, 1, 1.8, 'sage'],
    ['plant', 16, 10, 1, 1, 1.8, 'sage'],
    ['poster', 17.6, 9.5, 0.15, 2, 2.5, 'clay', undefined, 2],
    ['sofa', 3, 5, 3, 1, 1.25, 'clay', 'booth-a-n', 1],
    ['sofa', 3, 10, 3, 1, 1.25, 'clay', 'booth-a-s', 3],
    ['table', 3, 7, 3, 1.5, 0.8, 'cream', 'booth-table-a'],
    ['sofa', 10, 5, 3, 1, 1.25, 'clay', 'booth-b-n', 1],
    ['sofa', 10, 10, 3, 1, 1.25, 'clay', 'booth-b-s', 3],
    ['table', 10, 7, 3, 1.5, 0.8, 'cream', 'booth-table-b'],
  ],
  engineering: [
    ['machine', 1, 1, 2, 2, 2.7, 'teal'],
    ['machine', 8, 1, 2, 2, 2.7, 'violet'],
    ['machine', 15, 1, 2, 2, 2.7, 'amber'],
    ['plant', 16, 9, 1, 1, 1.8, 'sage'],
    ['poster', 2.3, 0.35, 1.4, 0.12, 2.5, 'teal'],
  ],
  gym: [
    ['noticeboard', 20, 3, 1.5, 1, 2.2, 'teal', 'habits', 1, 'habits'],
    ['mirror', 0.25, 2.2, 0.12, 5, 2.8, 'teal', undefined, 0],
    ['mirror', 0.25, 8, 0.12, 4, 2.8, 'teal', undefined, 0],
    ['weightbench', 2, 3, 2, 4, 1.4, 'teal', 'workout-1', 3],
    ['weightbench', 8, 3, 2, 4, 1.4, 'clay', 'workout-2', 3],
    ['dumbbells', 1, 9, 4, 1, 1.2, 'teal'],
    ['dumbbells', 7, 9, 3, 1, 1.2, 'teal'],
    ['plant', 20, 1, 1, 1, 1.8, 'sage'],
    ['plant', 20, 5, 1, 1, 1.8, 'sage'],
    ['weightbench', 16, 3, 2, 4, 1.4, 'amber', 'health', 1, 'health'],
    ['rug', 15, 8, 4, 2, 0.05, 'teal'],
  ],
  divination: [
    ['telescope', 1.15, 1.1, 2, 2, 2.1, 'amber', 'weather', 1, 'weather'],
    ['rug', 1.5, 3, 5, 6, 0.06, 'violet'],
    ['crystal', 3, 5, 2, 2, 2.1, 'violet', 'routines', 1, 'routines'],
    ['chair', 3.5, 3, 1, 1, 1.2, 'violet', 'oracle-n', 1, 'routines'],
    ['chair', 3.5, 8, 1, 1, 1.2, 'violet', 'oracle-s', 3, 'routines'],
    ['chair', 1, 5.5, 1, 1, 1.2, 'violet', 'oracle-w', 0, 'routines'],
    ['chair', 6, 5.5, 1, 1, 1.2, 'violet', 'oracle-e', 2, 'routines'],
    ['plant', 6, 18, 1, 1, 1.5, 'sage'],
    ['lamp', 1, 10, 0.4, 0.4, 2.2, 'amber'],
    ['poster', 0.25, 15, 0.12, 2, 2.6, 'violet', undefined, 0],
    ['rug', 1, 11.5, 6, 8, 0.05, 'violet'],
    ['sofa', 1.4, 12.5, 4.5, 1, 1.25, 'violet', 'oracle-lounge', 1],
    ['table', 2.5, 15, 2, 1.5, 0.8, 'violet', 'oracle-lounge-table'],
    ['lamp', 6, 16, 0.4, 0.4, 2.2, 'amber'],
    ['plant', 1, 20, 1, 1, 1.5, 'sage'],
    ['planter', 4, 20, 3, 0.7, 0.6, 'violet'],
  ],
  library: [
    ['shelf', 1, 1, 3, 1, 2.4, 'sage', 'books-0', 1, 'knowledge'],
    ['shelf', 4.5, 1, 3, 1, 2.4, 'amber', 'books-1', 1, 'knowledge'],
    ['shelf', 8, 1, 3, 1, 2.4, 'sage', 'books-2', 1, 'knowledge'],
    ['plant', 13, 4, 1, 1, 1.8, 'sage'],
    ['lamp', 5, 9, 0.4, 0.4, 2.2, 'amber'],
  ],
  restroom: [
    ['sink', 4, 1, 1.2, 1, 1.15, 'cream'],
    ['rug', 2, 3, 1.4, 1, 0.04, 'teal'],
    ['toilet', 1.5, 1, 1, 1.25, 1.2, 'cream', 'wc-seat', 1, 'sms'],
    ['mirror', 3, 0.2, 1, 0.12, 2.5, 'cream'],
    ['plant', 1, 4, 1, 1, 1.3, 'sage'],
    ['poster', 2.5, 0.3, 0.5, 0.1, 2, 'teal'],
  ],
  home: [
    ['mirror', 0.35, 6.4, 0.16, 1.25, 2.5, 'amber', 'appearance', 0, 'appearance'],
    ['bed', 2, 2, 3, 4, 0.8, 'clay', 'home-bed', 3],
    ['nightstand', 6, 2, 1.4, 1.2, 0.8, 'amber'],
    ['alarm', 6.15, 2.2, 0.8, 0.6, 1.15, 'teal', 'reminders', 1, 'reminders', 'nightstand:52:64'],
    ['desk', 10, 2, 3, 1, 1.7, 'teal', 'relations', 1, 'relations'],
    ['chair', 11, 4, 1, 1, 1.2, 'teal', 'home-desk-seat', 3, 'relations'],
    ['writingdesk', 10, 8, 3, 1.5, 1.7, 'amber', 'workboard', 1, 'workboard'],
    ['chair', 11, 11, 1, 1, 1.2, 'amber', 'home-secretary-seat', 3, 'workboard'],
    ['promiseboard', 0.35, 8, 0.15, 2, 2.3, 'amber', 'open-loops', 0, 'open-loops'],
    ['display', 0.35, 2, 0.2, 4, 2.9, 'violet', undefined, 0],
    ['poster', 5.3, 0.35, 1.4, 0.12, 2.6, 'teal'],
    ['poster', 9.3, 0.35, 1.4, 0.12, 2.6, 'clay'],
    ['plant', 14, 10, 1, 1, 1.8, 'sage'],
    ['sofa', 2, 10, 3, 1, 1.25, 'violet', 'home-lounge', 3],
    ['rug', 1.5, 8, 5, 4, 0.06, 'violet'],
    ['plant', 1, 11, 1, 1, 1.7, 'sage'],
  ],
};
for (const y of [3.5, 5.5, 7.5]) {
  ROOMS.meeting.push(['chair', 3, y, 1, 1, 1.2, 'teal', 'meeting-w-' + y, 0, 'meetings']);
  ROOMS.meeting.push(['chair', 9, y, 1, 1, 1.2, 'teal', 'meeting-e-' + y, 2, 'meetings']);
}
for (const [i, activity] of (
  ['asset-images', 'asset-documents', 'asset-screenshots', 'asset-bookmarks'] as const
).entries()) {
  const y = 1 + i * 3;
  ROOMS.multimedia.push(['easel', 1, y, 1, 1.3, 2.2, 'violet', 'gallery-' + i, 0, activity]);
  ROOMS.multimedia.push([
    'chair',
    3,
    y + 0.15,
    1,
    1,
    1.2,
    'violet',
    'gallery-seat-' + i,
    2,
    activity,
  ]);
}

for (const row of [0, 1])
  for (const col of [0, 1, 2]) {
    const x = 2 + col * 5,
      y = 4 + row * 4;
    ROOMS.memory.push([
      'readingdesk',
      x,
      y,
      3,
      1,
      1.1,
      'amber',
      'memory-desk-' + row + '-' + col,
      1,
      'memories',
    ]);
    ROOMS.memory.push([
      'chair',
      x + 1,
      y + 2,
      1,
      1,
      1.2,
      'amber',
      'memory-seat-' + row + '-' + col,
      3,
      'memories',
    ]);
  }
for (const [i, activity] of (['skills', 'mcp', 'plugins'] as const).entries()) {
  const x = 2 + i * 5;
  ROOMS.engineering.push([
    'labtable',
    x,
    6,
    3,
    2,
    1.8,
    (['teal', 'violet', 'amber'] as const)[i],
    activity,
    1,
    activity,
  ]);
  ROOMS.engineering.push(['chair', x + 1, 4, 1, 1, 1.2, 'teal', activity + '-n', 1, activity]);
  ROOMS.engineering.push(['chair', x + 1, 9, 1, 1, 1.2, 'teal', activity + '-s', 3, activity]);
}
for (const x of [2, 6, 10]) {
  ROOMS.library.push(['readingdesk', x, 5, 2, 1, 1.1, 'sage', 'reading-' + x, 1, 'knowledge']);
  ROOMS.library.push(['chair', x + 0.5, 7, 1, 1, 1.2, 'sage', 'library-seat-' + x, 3, 'knowledge']);
}
function tableLamp(prop: WorldProp): WorldProp[] {
  if (prop.kind !== 'lamp') return [prop];
  const support = 'sidetable:' + prop.x + ':' + prop.y;
  return [
    { ...prop, id: support, kind: 'sidetable', width: 1, depth: 1, height: 0.85, blocking: true },
    {
      ...prop,
      id: 'tablelamp:' + prop.x + ':' + prop.y,
      kind: 'tablelamp',
      x: prop.x + 0.2,
      y: prop.y + 0.2,
      width: 0.6,
      depth: 0.6,
      height: 1.6,
      support,
      blocking: false,
    },
  ];
}
export const HOUSE_FURNITURE = associateTables(
  HOUSE_ZONES.flatMap(zone => furnish(zone, ROOMS[zone.id]).flatMap(tableLamp))
    .map(prop => mountWallArt(prop, HOUSE_WALLS))
    .filter((prop): prop is WorldProp => prop !== null),
  {
    'atrium-table': ['atrium-n', 'atrium-s'],
    'meeting-lounge-table': ['meeting-lounge'],
    'media-lounge-table': ['media-sofa-n', 'media-sofa-s'],
    'booth-table-a': ['booth-a-n', 'booth-a-s'],
    'booth-table-b': ['booth-b-n', 'booth-b-s'],
    'oracle-lounge-table': ['oracle-lounge'],
  }
);
