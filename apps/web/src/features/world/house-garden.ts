import { furnish, type Furnishing } from './house-authoring';
import { POND } from './house-layout';
const garden: Furnishing[] = [
  ['pond', POND.x, POND.y, POND.width, POND.height, 0.05, 'teal'],
  ['waterlily', 19.5, 69, 1, 0.8, 0.25, 'clay'],
  ['waterlily', 22, 71, 1, 0.8, 0.25, 'cream'],
  ['table', 2, 51, 2, 1.5, 0.8, 'clay'],
  ['chair', 2.5, 49, 1, 1, 1.2, 'clay', 'terrace-chair-c-n', 1],
  ['chair', 2.5, 54, 1, 1, 1.2, 'clay', 'terrace-chair-c-s', 3],
  ['parasol', 5.3, 50, 3, 3, 3.9, 'teal'],
  ['bar', 10, 50, 7, 1.5, 1.3, 'clay'],
  ['table', 20, 51, 2, 1.5, 0.8, 'teal'],
  ['table', 26, 51, 2, 1.5, 0.8, 'teal'],
  ['chair', 20.5, 49, 1, 1, 1.2, 'teal', 'terrace-chair-a-n', 1],
  ['chair', 20.5, 54, 1, 1, 1.2, 'teal', 'terrace-chair-a-s', 3],
  ['chair', 26.5, 49, 1, 1, 1.2, 'teal', 'terrace-chair-b-n', 1],
  ['chair', 26.5, 54, 1, 1, 1.2, 'teal', 'terrace-chair-b-s', 3],
  ['parasol', 22.5, 49.5, 3, 3, 3.9, 'clay'],
  ['parasol', 35, 49.5, 3, 3, 3.9, 'amber'],
  ['lounger', 39, 50, 1, 3, 0.8, 'teal', 'sun-lounger-a', 1],
  ['lounger', 42, 50, 1, 3, 0.8, 'clay', 'sun-lounger-b', 1],
  ['herbarium', 7, 68, 3, 1.5, 2.3, 'sage', 'interests', 1, 'interests'],
  ['bench', 18, 76, 3, 1, 1.1, 'sage', 'pond-bench', 3],
  ['bench', 28, 68, 1, 3, 1.1, 'sage', 'pond-east', 2],
  ['bench', 38, 58, 3, 1, 1.1, 'teal', 'garden-bench', 1],
  ['planter', 10, 54, 6, 1, 0.6, 'sage'],
  ['planter', 47, 54, 6, 1, 0.6, 'clay'],
  ['planter', 37, 62, 5, 1, 0.6, 'sage'],
];
for (const [x, y] of [
  [6, 58],
  [10, 58],
  [6, 61],
  [10, 61],
  [6, 74],
  [10, 74],
])
  garden.push(['vegetable', x, y, 2.5, 2, 1.2, 'sage']);
for (const [x, y, tone] of [
  [-3, 9, 'sage'],
  [-3, 19, 'clay'],
  [-3, 29, 'sage'],
  [-3, 40, 'sage'],
  [-3, 47, 'clay'],
  [14, 3, 'sage'],
  [28, 3, 'clay'],
  [40, 3, 'sage'],
  [53, 3, 'sage'],
  [64, 10, 'clay'],
  [65, 25, 'sage'],
  [65, 42, 'clay'],
  [65, 56, 'sage'],
  [60, 59, 'clay'],
  [45, 59, 'sage'],
  [35, 60, 'clay'],
  [4, 57, 'sage'],
  [4, 69, 'clay'],
  [15, 58, 'sage'],
  [22, 59, 'clay'],
  [39, 68, 'sage'],
  [4, 80, 'sage'],
  [25, 80, 'clay'],
  [42, 81, 'clay'],
  [62, 80, 'sage'],
  [65, 70, 'clay'],
] as const) {
  garden.push(['tree', x, y, 1, 1, 3.5, tone]);
  garden.push(['flowers', x + 1.1, y + 0.7, 1, 1, 0.4, 'clay']);
}
// Small groves along the grass belts; keep the terrace, doors and garden paths open.
for (const [x, y, tone] of [
  [-3, 4, 'sage'],
  [-3, 14, 'sage'],
  [-3, 24, 'clay'],
  [-3, 35, 'sage'],
  [4, 2, 'sage'],
  [9, 3, 'clay'],
  [20, 2, 'sage'],
  [34, 2, 'sage'],
  [46, 3, 'clay'],
  [59, 2, 'sage'],
  [65, 4, 'sage'],
  [65, 17, 'sage'],
  [65, 33, 'sage'],
  [65, 48, 'sage'],
  [65, 63, 'clay'],
  [65, 76, 'sage'],
  [1, 62, 'sage'],
  [1, 74, 'clay'],
  [16, 80, 'sage'],
  [35, 81, 'sage'],
  [47, 80, 'sage'],
  [58, 82, 'clay'],
] as const)
  garden.push(['tree', x, y, 1, 1, 3.5, tone]);
for (const [x, y] of [
  [0.8, 52.5],
  [17, 49.5],
  [35, 53.5],
  [48, 50.5],
  [57, 52],
  [28.5, 58],
  [33.5, 65],
  [28.5, 72],
  [33.5, 79],
  [40, 75],
  [50, 79],
  [57, 77],
])
  garden.push(['lamp', x, y, 0.4, 0.4, 2.2, 'amber']);
// Discrete stone banks follow the natural stepped water edge, never a path through water.
for (const [dx, dy] of [
  [2, -0.3],
  [4, -0.4],
  [6, -0.25],
  [8, 1],
  [9.5, 3],
  [9, 5],
  [7, 7.5],
  [4, 7.8],
  [1, 6],
  [-0.3, 3],
])
  garden.push(['rock', POND.x + dx, POND.y + dy, 0.7, 0.55, 0.4, 'cream']);
for (const [dx, dy] of [
  [1, 1],
  [8, 2],
  [2, 6],
  [6, 7],
])
  garden.push(['reeds', POND.x + dx, POND.y + dy, 0.8, 0.7, 1.1, 'sage']);
// Low border flowers leave the side grass belts and all entrances walkable.
for (const [x, y] of [
  [-1.5, 14],
  [-1.5, 34],
  [20, 3],
  [47, 3],
  [63, 18],
  [63, 34],
  [13, 64],
  [14, 73],
  [26, 65],
  [26, 75],
  [43, 67],
  [43, 69],
] as const) {
  garden.push(['flowers', x, y, 1, 1, 0.4, 'clay']);
  garden.push(['flowers', x + 1, y + 0.3, 1, 1, 0.4, 'sage']);
}
export const HOUSE_GARDEN = furnish({ x: 0, y: 0 }, garden);
