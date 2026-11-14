/**
 * Layout inspector for review renders only (input prop `inspect`).
 *
 * After each frame is laid out it walks every visible text run and reports,
 * through the browser console (collected by `render-promo.mjs inspect`):
 * - `overflow`: text drawn outside the component that holds it,
 * - `tight`: text closer than 4 px to its component's edge,
 * - `edge`: text cut by the frame or closer than 24 px to it,
 * - `overlap`: two visible texts from different components covering each other.
 * Nothing here is drawn; the delivered film never mounts it.
 */
import { useLayoutEffect } from 'react';
import { continueRender, delayRender, useCurrentFrame } from 'remotion';

const CONTAINERS = [
  'btn',
  'pill',
  'bubble-user',
  'bubble-lia',
  'composer-field',
  'notif',
  'card',
  'phone-screen',
  'app',
  'kt',
  'kt-sub',
  'node-label',
  'tile',
  'bento',
];

type Box = { x: number; y: number; w: number; h: number };
type Run = { text: string; box: Box; owner: Element; ownerName: string };

function containerOf(el: Element): { owner: Element; name: string } {
  let e: Element | null = el;
  while (e) {
    for (const c of CONTAINERS) if (e.classList?.contains(c)) return { owner: e, name: c };
    e = e.parentElement;
  }
  return { owner: document.body, name: 'body' };
}

function visible(el: Element): number {
  let opacity = 1;
  let e: Element | null = el;
  while (e && e !== document.body) {
    const cs = getComputedStyle(e);
    if (cs.display === 'none' || cs.visibility === 'hidden') return 0;
    opacity *= parseFloat(cs.opacity || '1');
    e = e.parentElement;
  }
  return opacity;
}

const area = (b: Box) => Math.max(0, b.w) * Math.max(0, b.h);
const intersect = (a: Box, b: Box): Box => {
  const x = Math.max(a.x, b.x);
  const y = Math.max(a.y, b.y);
  return { x, y, w: Math.min(a.x + a.w, b.x + b.w) - x, h: Math.min(a.y + a.h, b.y + b.h) - y };
};

function scan(frame: number) {
  const runs: Run[] = [];
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  for (let node = walker.nextNode(); node; node = walker.nextNode()) {
    const text = (node.textContent ?? '').trim();
    const el = node.parentElement;
    if (!text || !el || el.closest('.sym') || el.closest('svg')) continue;
    if (visible(el) < 0.5) continue;
    const range = document.createRange();
    range.selectNodeContents(node);
    const { owner, name } = containerOf(el);
    for (const r of Array.from(range.getClientRects())) {
      if (r.width < 3 || r.height < 3) continue;
      runs.push({ text: text.slice(0, 48), box: { x: r.left, y: r.top, w: r.width, h: r.height }, owner, ownerName: name });
    }
  }
  const issues: Array<Record<string, unknown>> = [];
  for (const run of runs) {
    const b = run.box;
    if (run.ownerName !== 'body' && run.ownerName !== 'kt' && run.ownerName !== 'kt-sub' && run.ownerName !== 'node-label') {
      const o = run.owner.getBoundingClientRect();
      const out = Math.max(o.left - b.x, b.x + b.w - o.right, o.top - b.y, b.y + b.h - o.bottom);
      if (out > 1.5) issues.push({ kind: 'overflow', text: run.text, in: run.ownerName, by: Math.round(out) });
      else {
        const margin = Math.min(b.x - o.left, o.right - (b.x + b.w));
        if (margin < 4 && run.ownerName !== 'app' && run.ownerName !== 'phone-screen' && run.ownerName !== 'card') {
          issues.push({ kind: 'tight', text: run.text, in: run.ownerName, margin: Math.round(margin) });
        }
      }
    }
    const edge = Math.min(b.x, b.y, 1920 - (b.x + b.w), 1080 - (b.y + b.h));
    if (edge < 24 && b.x < 1920 && b.y < 1080 && b.x + b.w > 0 && b.y + b.h > 0) {
      issues.push({ kind: 'edge', text: run.text, in: run.ownerName, distance: Math.round(edge) });
    }
  }
  for (let i = 0; i < runs.length; i++) {
    for (let j = i + 1; j < runs.length; j++) {
      const a = runs[i];
      const b = runs[j];
      if (a.owner === b.owner || a.owner.contains(b.owner) || b.owner.contains(a.owner)) continue;
      const inter = intersect(a.box, b.box);
      if (inter.w <= 2 || inter.h <= 2) continue;
      const share = area(inter) / Math.min(area(a.box), area(b.box));
      // Stacked headline lines touch by design (line-height 1.04); only a real collision counts.
      const bothHeadlines = a.ownerName === 'kt' && b.ownerName === 'kt';
      if (share > (bothHeadlines ? 0.3 : 0.12)) issues.push({ kind: 'overlap', text: a.text, with: b.text, share: Math.round(share * 100) });
    }
  }
  // eslint-disable-next-line no-console -- the render script collects these lines
  console.log(`INSPECT ${JSON.stringify({ frame, issues })}`);
}

export function Inspector() {
  const frame = useCurrentFrame();
  useLayoutEffect(() => {
    const handle = delayRender(`inspect ${frame}`);
    document.fonts.ready.then(() => {
      requestAnimationFrame(() => {
        scan(frame);
        continueRender(handle);
      });
    });
  }, [frame]);
  return null;
}
