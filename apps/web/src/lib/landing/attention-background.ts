/**
 * LIA — animated landing background « Attention + latent space ».
 *
 * One fixed full-viewport `<canvas>` behind the content, driven by the page's
 * scroll. The reference implementation (vanilla JS, supplied and validated by
 * the project owner on 2026-10-02, not vendored) is ported here with TYPE
 * ANNOTATIONS ONLY: every formula, opacity and colour is the reference's, and
 * changes to them are the owner's to make. The motion policy around it is
 * LIA's own: under reduced motion, when the visitor pauses the page (WCAG
 * 2.2.2) or when the device is too slow, ONE still frame is drawn and redrawn
 * only when the theme or the layout changes — never on scroll or pointer.
 *
 *  Layer 1 (below) — latent space: a cloud of embeddings that organises into
 *  clusters as the page scrolls. The pointer (or, failing it, a wandering point)
 *  is a query vector: its k nearest neighbours light up.
 *
 *  Layer 2 (above) — attention heads: a column of tokens in the right margin
 *  stands for the whole page; every real section of the page is a section start.
 *  The « reading line » is the current token, looking at the past through four
 *  heads (local, attention sink on the first token, section starts, semantic).
 *
 * The cost does not depend on the page's length: the canvas is viewport-sized.
 *
 * Integration: the content must paint above the canvas, and section backgrounds
 * must be transparent or translucent where the pattern should show.
 */

export interface LiaBackgroundOptions {
  /** Selector of the page's real sections. */
  sections: string;
  /** 0 disables the layer. */
  intensityAttention: number;
  /** 0 disables the layer. */
  intensityLatent: number;
  /** Small measurements in the bottom corners (desktop only). */
  readout: boolean;
  fps: number;
  maxDpr: number;
  zIndex: number;
  /** Parent element of the canvas (default: `document.body`). */
  mount: HTMLElement | null;
  /** Position of the reading line in the viewport (0 = top). */
  readingLine: number;
  /** Scroll fraction at which the clusters are formed. */
  latentFormedAt: number;
  /** One label per latent cluster (six); none drawn when absent. */
  labels: string[];
  /** One name per attention head (local, sink, section, semantic); none drawn when absent. */
  headNames: string[];
  /** Draw the heads' curves (and their readout); false keeps the token column alone. */
  attentionHeads: boolean;
  isDark: () => boolean;
  /** The music's beat intensity in [0, 1] (0 when nothing plays). */
  beat: () => number;
  /** How much a full beat lifts both layers' intensity (0 = no pulse). */
  beatGain: number;
  /**
   * Median cost, in ms, an animated frame may take on this device. Past it the
   * background stops moving for the session and redraws only when the theme or
   * the layout changes, exactly as under reduced motion. Infinity = never
   * measured.
   */
  frameBudgetMs: number;
  /** Whether the page asked its motion to stop (read at every frame). */
  paused: () => boolean;
}

export interface LiaBackgroundHandle {
  /**
   * Updates options on the running canvas. `zIndex` and `mount` only apply at
   * mount, `maxDpr` from the next resize; everything else from the next frame.
   */
  set(opts: Partial<LiaBackgroundOptions>): void;
  /** Re-read the sections after a major content change. */
  refresh(): void;
  /** Unmount (SPA navigation, HMR). */
  destroy(): void;
}

type Rgb = string;
interface Palette {
  b: Rgb;
  v: Rgb;
  t: Rgb;
  m: Rgb;
}
interface AttentionLink {
  w: number;
  h: number;
  j: number;
}
interface LatentPoint {
  c: number;
  ox: number;
  oy: number;
  rx: number;
  ry: number;
  ph: number;
  x: number;
  y: number;
}

const DEFAULTS: LiaBackgroundOptions = {
  sections: 'section',
  intensityAttention: 1,
  intensityLatent: 0.5,
  readout: true,
  fps: 30,
  maxDpr: 1.5,
  zIndex: 0,
  mount: null,
  readingLine: 0.35,
  latentFormedAt: 0.45,
  // The caller translates them (AttentionBackdrop): no language is written here.
  labels: [],
  headNames: [],
  attentionHeads: true,
  isDark: () => {
    const h = document.documentElement;
    if (h.classList.contains('dark') || h.dataset.theme === 'dark') return true;
    if (h.classList.contains('light') || h.dataset.theme === 'light') return false;
    return window.matchMedia('(prefers-color-scheme: dark)').matches;
  },
  beat: () => 0,
  beatGain: 0,
  frameBudgetMs: Infinity,
  paused: () => false,
};

/** Animated frames ignored before measuring (JIT warm-up, first layout). */
const BUDGET_WARMUP_FRAMES = 5;
/** Animated frames whose median decides whether the device can afford motion. */
const BUDGET_SAMPLE_FRAMES = 30;

const PALETTE: { light: Palette; dark: Palette } = {
  light: { b: '43,79,201', v: '124,92,246', t: '18,130,140', m: '86,84,224' },
  dark: { b: '150,168,255', v: '184,164,255', t: '120,210,220', m: '165,160,255' },
};

const MONO = 'ui-monospace, "SF Mono", Menlo, Consolas, monospace';
const TAU = Math.PI * 2;
const clamp = (x: number, a: number, b: number): number => Math.max(a, Math.min(b, x));
const smooth = (x: number): number => x * x * (3 - 2 * x);
function rng(seed: number): () => number {
  let s = seed >>> 0;
  return () => {
    s = (s * 1664525 + 1013904223) >>> 0;
    return s / 4294967296;
  };
}
const rgba = (c: Rgb, a: number): string => `rgba(${c},${a})`;

export function mountLiaBackground(
  userOpts: Partial<LiaBackgroundOptions> = {}
): LiaBackgroundHandle {
  const o: LiaBackgroundOptions = { ...DEFAULTS, ...userOpts };
  const reduced = window.matchMedia('(prefers-reduced-motion: reduce)');

  const cv = document.createElement('canvas');
  cv.setAttribute('aria-hidden', 'true');
  cv.className = 'lia-bg';
  Object.assign(cv.style, {
    position: 'fixed',
    left: '0',
    top: '0',
    // The fallback height, with no viewport unit: anchored top AND bottom, the
    // layer spans the viewport wherever `lvh` is unknown.
    bottom: '0',
    width: '100vw',
    // The LARGE viewport on purpose: a decorative fixed layer keeps a stable
    // height while the mobile URL bar shows/hides (no redraw, no rescale). With
    // top, bottom and height all set, the height wins and `bottom` is ignored.
    height: '100lvh',
    pointerEvents: 'none',
    zIndex: String(o.zIndex),
  });
  const context = cv.getContext('2d');
  if (!context) {
    // No 2D context (exotic environment): nothing to draw, nothing to clean.
    return { set() {}, refresh() {}, destroy() {} };
  }
  const ctx: CanvasRenderingContext2D = context;
  (o.mount || document.body).prepend(cv);

  let W = 0,
    H = 0,
    dpr = 1,
    raf = 0,
    alive = true,
    lastDraw = 0,
    frame = 0;
  let p = 0,
    q = 1,
    mx = -1,
    my = -1,
    dirty = true,
    lastDark: boolean | null = null,
    lastStill: boolean | null = null;
  // attention
  let N = 72,
    starts: number[] = [0],
    isStart = new Set<number>([0]),
    sec: number[] = [],
    E: number[][] = [],
    hash: number[] = [];
  // latent space
  let P: LatentPoint[] = [],
    cen: number[][] = [],
    nb: number[][] = [],
    qx: number | null = null,
    qy: number | null = null;
  // frame budget: once too costly, the background stays still for the session
  let tooCostly = false,
    warmup = BUDGET_WARMUP_FRAMES;
  const costs: number[] = [];

  const spineX = (): number => W - (W < 768 ? 22 : 56);
  const y0 = (): number => Math.min(92, H * 0.1);
  const y1 = (): number => H - 64;
  const tokenY = (j: number): number => y0() + (j / (N - 1)) * (y1() - y0());

  /* ---------- construction ---------- */

  function layout(): void {
    const r = cv.getBoundingClientRect();
    const w = Math.round(r.width),
      h = Math.round(r.height);
    const d = Math.min(window.devicePixelRatio || 1, o.maxDpr);
    if (w === W && h === H && d === dpr) return;
    W = w;
    H = h;
    dpr = d;
    cv.width = Math.round(W * dpr);
    cv.height = Math.round(H * dpr);
    buildLatent();
    measureSections();
    dirty = true;
  }

  function buildLatent(): void {
    const r = rng(23),
      n = W < 768 ? 150 : 300,
      sc = Math.min(W, H) / 900;
    cen = [
      [0.17, 0.26],
      [0.42, 0.77],
      [0.65, 0.23],
      [0.8, 0.48],
      [0.69, 0.84],
      [0.23, 0.62],
    ].map(([x, y]) => [x * W, y * H]);
    P = [];
    for (let i = 0; i < n; i++) {
      const u = Math.max(1e-6, r()),
        a = r() * TAU,
        rad = Math.sqrt(-2 * Math.log(u)) * 46 * sc;
      P.push({
        c: i % 6,
        ox: Math.cos(a) * rad * 1.3,
        oy: Math.sin(a) * rad,
        rx: 40 + r() * Math.max(1, W - 160),
        ry: 40 + r() * Math.max(1, H - 80),
        ph: r() * TAU,
        x: 0,
        y: 0,
      });
    }
    nb = P.map(() => [-1, -1]);
    frame = 0;
  }

  function measureSections(): void {
    const docH = Math.max(document.documentElement.scrollHeight, 1);
    N = clamp(Math.round(docH / 60), 48, 120);
    const s = [0];
    for (const el of document.querySelectorAll(o.sections)) {
      const top = el.getBoundingClientRect().top + window.scrollY;
      const j = Math.round((top / docH) * (N - 1));
      if (j > s[s.length - 1] + 2 && j < N - 1) s.push(j);
    }
    starts = s;
    isStart = new Set(s);
    const r = rng(11),
      D = 8;
    const themes = starts.map(() => Array.from({ length: D }, () => r() * 2 - 1));
    sec = [];
    E = [];
    hash = [];
    for (let j = 0; j < N; j++) {
      let si = 0;
      for (let k = 0; k < starts.length; k++) if (j >= starts[k]) si = k;
      sec.push(si);
      const other = themes[(si + 3) % themes.length];
      const v = themes[si].map(
        (t, d) => t + (r() * 2 - 1) * 0.9 + (j % 11 === 3 ? 1.4 * other[d] : 0)
      );
      const nrm = Math.hypot(...v) || 1;
      E.push(v.map(z => z / nrm));
      hash.push(r());
    }
    q = clamp(q, 1, N - 1);
    dirty = true;
  }

  /* ---------- layer 1: latent space ---------- */

  /** Cluster sums gathered while placing the points, read by the labels. */
  interface ClusterSums {
    sumx: number[];
    sumy: number[];
    cnt: number[];
  }

  function placePoints(t: number, s: number): ClusterSums {
    const sumx = [0, 0, 0, 0, 0, 0],
      sumy = [0, 0, 0, 0, 0, 0],
      cnt = [0, 0, 0, 0, 0, 0];
    for (const pt of P) {
      const cx = cen[pt.c][0] + pt.ox,
        cy = cen[pt.c][1] + pt.oy;
      pt.x = pt.rx + (cx - pt.rx) * s + 6 * Math.sin(t * 0.5 + pt.ph);
      pt.y = pt.ry + (cy - pt.ry) * s + 6 * Math.cos(t * 0.4 + pt.ph * 1.3);
      sumx[pt.c] += pt.x;
      sumy[pt.c] += pt.y;
      cnt[pt.c]++;
    }
    return { sumx, sumy, cnt };
  }

  // k-NN graph (2 neighbours < 80 px)
  function updateNeighbours(): void {
    const n = P.length;
    for (let i = 0; i < n; i++) {
      const a = P[i];
      let b1 = -1,
        b2 = -1,
        d1 = 6400,
        d2 = 6400;
      for (let j = 0; j < n; j++) {
        if (j === i) continue;
        const dx = P[j].x - a.x,
          dy = P[j].y - a.y,
          d = dx * dx + dy * dy;
        if (d < d1) {
          d2 = d1;
          b2 = b1;
          d1 = d;
          b1 = j;
        } else if (d < d2) {
          d2 = d;
          b2 = j;
        }
      }
      nb[i][0] = b1;
      nb[i][1] = b2;
    }
  }

  function drawCloud(k: number, C: Palette, s: number): void {
    const n = P.length;
    ctx.beginPath();
    for (let i = 0; i < n; i++) {
      for (const b of nb[i])
        if (b >= 0) {
          ctx.moveTo(P[i].x, P[i].y);
          ctx.lineTo(P[b].x, P[b].y);
        }
    }
    ctx.lineWidth = 0.7;
    ctx.strokeStyle = rgba(C.b, (0.035 + 0.05 * s) * k);
    ctx.stroke();

    const pb = new Path2D(),
      pv = new Path2D();
    for (const pt of P) {
      const path = pt.c % 2 ? pv : pb;
      path.moveTo(pt.x + 1.7, pt.y);
      path.arc(pt.x, pt.y, 1.7, 0, TAU);
    }
    ctx.fillStyle = rgba(C.b, 0.26 * k);
    ctx.fill(pb);
    ctx.fillStyle = rgba(C.v, 0.26 * k);
    ctx.fill(pv);
  }

  // query vector: the pointer (outside the attention column), else a wandering
  // point; a still frame never follows the pointer
  function moveQuery(t: number, still: boolean): [number, number] {
    let tx: number, ty: number;
    if (!still && mx >= 0 && mx < spineX() - 90) {
      tx = mx;
      ty = my;
    } else {
      tx = W * (0.46 + 0.36 * Math.sin(t * 0.11));
      ty = H * (0.5 + 0.38 * Math.sin(t * 0.17 + 1.2));
    }
    let x = qx ?? tx,
      y = qy ?? ty;
    if (qx === null || qy === null || still) {
      x = tx;
      y = ty;
    }
    x += (tx - x) * 0.15;
    y += (ty - y) * 0.15;
    qx = x;
    qy = y;
    return [x, y];
  }

  /** Lights the query's k nearest neighbours; returns the sorted distances. */
  function drawNeighbours(k: number, C: Palette, x: number, y: number): [number, number][] {
    const ds = P.map((pt, i): [number, number] => [(pt.x - x) ** 2 + (pt.y - y) ** 2, i]).sort(
      (a, b) => a[0] - b[0]
    );
    const K = Math.min(8, ds.length);
    for (let r = 0; r < K; r++) {
      const pt = P[ds[r][1]];
      ctx.beginPath();
      ctx.moveTo(x, y);
      ctx.lineTo(pt.x, pt.y);
      ctx.lineWidth = 0.9;
      ctx.strokeStyle = rgba(C.v, (0.34 - 0.03 * r) * k);
      ctx.stroke();
      ctx.beginPath();
      ctx.arc(pt.x, pt.y, 2.8, 0, TAU);
      ctx.fillStyle = rgba(C.v, Math.min(0.85, 0.6 * k));
      ctx.fill();
    }
    ctx.setLineDash([2, 5]);
    ctx.beginPath();
    ctx.arc(x, y, Math.sqrt(ds[K - 1][0]), 0, TAU);
    ctx.lineWidth = 0.8;
    ctx.strokeStyle = rgba(C.v, 0.14 * k);
    ctx.stroke();
    ctx.setLineDash([]);
    ctx.beginPath();
    ctx.arc(x, y, 4, 0, TAU);
    ctx.fillStyle = rgba(C.v, Math.min(0.9, 0.75 * k));
    ctx.fill();
    return ds;
  }

  function drawClusterLabels(k: number, C: Palette, s: number, sums: ClusterSums): void {
    if (W < 768) return;
    const { sumx, sumy, cnt } = sums;
    ctx.font = `500 11px ${MONO}`;
    ctx.textAlign = 'center';
    ctx.textBaseline = 'middle';
    ctx.fillStyle = rgba(C.b, 0.32 * s * k);
    for (let c = 0; c < 6; c++)
      if (cnt[c]) ctx.fillText(o.labels[c] || '', sumx[c] / cnt[c], sumy[c] / cnt[c] - 86);
  }

  function drawLatent(t: number, k: number, C: Palette, still: boolean): void {
    const s = smooth(clamp((p - 0.02) / Math.max(0.05, o.latentFormedAt - 0.02), 0, 1));
    const sums = placePoints(t, s);
    // recomputed one frame in three
    if (still || frame % 3 === 0) updateNeighbours();
    frame++;
    drawCloud(k, C, s);
    const [x, y] = moveQuery(t, still);
    const ds = drawNeighbours(k, C, x, y);
    drawClusterLabels(k, C, s, sums);
    const near = P[ds[0][1]],
      cos = Math.max(0, 1 - Math.sqrt(ds[0][0]) / 420);
    readout(
      `q · top-k = 8  ·  cos = ${cos.toFixed(2)}  ·  ${o.labels[near.c] || ''}`,
      k,
      C,
      24,
      'left'
    );
  }

  /* ---------- layer 2: attention heads ---------- */

  function weights(h: number, iq: number): number[] {
    const sc: number[] = [];
    let m = -1e9;
    for (let j = 0; j < iq; j++) {
      let s: number;
      if (h === 0)
        s = -(((iq - j) / 3) ** 2); // local
      else if (h === 1)
        s = j === 0 ? 3.2 : -0.5 + hash[j]; // attention sink
      else if (h === 2)
        s = isStart.has(j) ? 2.4 - 0.04 * (iq - j) : -2.5; // section starts
      else {
        // semantic, outside the current section
        let dot = 0;
        for (let d = 0; d < E[iq].length; d++) dot += E[iq][d] * E[j][d];
        s = dot * 5 - (sec[j] === sec[iq] ? 2.2 : 0);
      }
      sc.push(s);
      if (s > m) m = s;
    }
    let z = 0;
    for (let i = 0; i < sc.length; i++) {
      sc[i] = Math.exp(sc[i] - m);
      z += sc[i];
    }
    for (let i = 0; i < sc.length; i++) sc[i] /= z;
    return sc;
  }

  /**
   * One tick per token. The ticks only differ by two traits — section start
   * (width, length) and already read (opacity) — so they are stroked as four
   * paths instead of one stroke each: the ticks never overlap, so the pixels
   * are the same and ~120 strokes a frame become four.
   */
  function drawTokenTicks(sx: number, k: number, C: Palette): void {
    for (const st of [false, true]) {
      for (const read of [false, true]) {
        ctx.beginPath();
        for (let j = 0; j < N; j++) {
          if (isStart.has(j) !== st || j <= q !== read) continue;
          const y = tokenY(j);
          ctx.moveTo(sx - (st ? 12 : 4), y);
          ctx.lineTo(sx + 4, y);
        }
        ctx.lineWidth = st ? 1.2 : 1;
        ctx.strokeStyle = rgba(C.b, (read ? 0.22 : 0.08) * k);
        ctx.stroke();
      }
    }
  }

  /** The four heads' curves from the reading line; returns the strongest link. */
  function drawHeads(t: number, k: number, C: Palette, sx: number, yq: number): AttentionLink {
    const cap = Math.min(420, W * 0.3);
    const i0 = Math.max(1, Math.floor(q)),
      i1 = Math.min(N - 1, i0 + 1),
      fr = clamp(q - i0, 0, 1);
    const cols = [C.b, C.v, C.t, C.m];
    let best: AttentionLink = { w: 0, h: 0, j: 0 };
    for (let h = 0; h < 4; h++) {
      const w0 = weights(h, i0),
        w1 = weights(h, i1),
        list: [number, number][] = [];
      for (let j = 0; j < i1; j++)
        list.push([(1 - fr) * (j < w0.length ? w0[j] : 0) + fr * w1[j], j]);
      list.sort((a, b) => b[0] - a[0]);
      for (let r = 0; r < Math.min(5, list.length); r++) {
        const [w, jj] = list[r];
        if (w < 0.03) break;
        if (w > best.w) best = { w, h, j: jj };
        const yj = tokenY(jj),
          bulge = Math.min(cap, (34 + 0.42 * Math.abs(yq - yj)) * (0.75 + 0.22 * h));
        ctx.beginPath();
        ctx.moveTo(sx - 6, yj);
        ctx.bezierCurveTo(sx - 6 - bulge, yj, sx - 6 - bulge, yq, sx - 6, yq);
        ctx.setLineDash([]);
        ctx.lineWidth = 0.5 + 2.2 * w;
        ctx.strokeStyle = rgba(cols[h], Math.min(0.5, 0.05 + 0.42 * w) * k);
        ctx.stroke();
        ctx.setLineDash([1.5, 9]);
        ctx.lineDashOffset = -t * 30 * (h % 2 ? 1 : 0.7);
        ctx.lineWidth = 1.6;
        ctx.strokeStyle = rgba(cols[h], Math.min(0.7, 0.1 + 0.6 * w) * k);
        ctx.stroke();
      }
    }
    return best;
  }

  function drawAttention(t: number, k: number, C: Palette): void {
    const sx = spineX(),
      yq = tokenY(q);
    // Round caps for the curves AND the token ticks, curves drawn or not.
    ctx.lineCap = 'round';
    const best = o.attentionHeads ? drawHeads(t, k, C, sx, yq) : null;
    ctx.setLineDash([]);
    drawTokenTicks(sx, k, C);
    ctx.beginPath();
    ctx.moveTo(sx + 10, y0());
    ctx.lineTo(sx + 10, y1());
    ctx.lineWidth = 1;
    ctx.strokeStyle = rgba(C.b, 0.07 * k);
    ctx.stroke();
    if (W >= 768) {
      ctx.font = `500 10px ${MONO}`;
      ctx.textAlign = 'left';
      ctx.textBaseline = 'middle';
      ctx.fillStyle = rgba(C.b, 0.28 * k);
      let lastY = -1e9;
      starts.forEach((j, i) => {
        const y = tokenY(j);
        if (y - lastY < 14) return;
        ctx.fillText(i === 0 ? '⟨s⟩' : `§${i}`, sx + 16, y);
        lastY = y;
      });
    }
    ctx.beginPath();
    ctx.arc(sx, yq, 3.4, 0, TAU);
    ctx.fillStyle = rgba(C.v, Math.min(0.9, 0.7 * k));
    ctx.fill();
    ctx.beginPath();
    ctx.arc(sx, yq, 9, 0, TAU);
    ctx.lineWidth = 1;
    ctx.strokeStyle = rgba(C.v, 0.25 * k);
    ctx.stroke();
    // The readout names the strongest head's link: nothing to name without the curves.
    if (!best) return;
    readout(
      `h${best.h} ${o.headNames[best.h] || ''} → ${best.j === 0 ? '⟨s⟩' : 'tok ' + best.j}  ·  w = ${best.w.toFixed(2)}`,
      k,
      C,
      sx - 24,
      'right'
    );
  }

  function readout(text: string, k: number, C: Palette, x: number, align: CanvasTextAlign): void {
    if (!o.readout || W < 768) return;
    ctx.font = `500 11px ${MONO}`;
    ctx.textAlign = align;
    ctx.textBaseline = 'alphabetic';
    ctx.fillStyle = rgba(C.b, clamp(0.32 * k, 0.2, 0.55));
    ctx.fillText(text, x, H - 22);
  }

  /* ---------- loop ---------- */

  /** The token the reading line points at; the pointer takes over on the column. */
  function readingTarget(sy: number, vh: number, docH: number): number {
    if (mx >= spineX() - 90 && my > y0() - 10 && my < y1() + 10)
      return clamp(((my - y0()) / (y1() - y0())) * (N - 1), 1, N - 1);
    return clamp(((sy + vh * o.readingLine) / docH) * (N - 1), 1, N - 1);
  }

  /**
   * Eases toward the scroll targets. A still background keeps the formation
   * and the reading line where they stand and has something new to draw only
   * when it just became still, or the theme or the layout changed: it never
   * follows the scroll or the pointer, so nothing on the screen moves.
   */
  function advance(still: boolean, dark: boolean): boolean {
    if (dark !== lastDark) {
      lastDark = dark;
      dirty = true;
    }
    if (still !== lastStill) {
      lastStill = still;
      dirty = true;
    }
    if (still) {
      if (!dirty) return false;
      dirty = false;
      return true;
    }
    const docH = Math.max(document.documentElement.scrollHeight, 1),
      sy = window.scrollY,
      vh = window.innerHeight;
    const pT = clamp(sy / Math.max(1, docH - vh), 0, 1);
    const qT = readingTarget(sy, vh, docH);
    p += (pT - p) * 0.12;
    q += (qT - q) * 0.15;
    dirty = false;
    return true;
  }

  function render(now: number, still: boolean, dark: boolean): void {
    // The beat lifts the intensity a little; a still background never pulses.
    const pulse = still ? 1 : 1 + o.beatGain * clamp(o.beat(), 0, 1);
    const t = still ? 0 : now / 1000,
      C = dark ? PALETTE.dark : PALETTE.light,
      boost = (dark ? 1.25 : 1) * pulse;
    ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
    ctx.globalAlpha = 1;
    ctx.setLineDash([]);
    ctx.clearRect(0, 0, W, H);
    if (o.intensityLatent > 0) drawLatent(t, o.intensityLatent * boost, C, still);
    if (o.intensityAttention > 0) drawAttention(t, o.intensityAttention * boost, C);
  }

  /** Records one animated frame's cost; decides once, on the median. */
  function measureCost(ms: number): void {
    if (!Number.isFinite(o.frameBudgetMs) || costs.length >= BUDGET_SAMPLE_FRAMES) return;
    if (warmup > 0) {
      warmup--;
      return;
    }
    costs.push(ms);
    if (costs.length < BUDGET_SAMPLE_FRAMES) return;
    const sorted = [...costs].sort((a, b) => a - b);
    tooCostly = sorted[sorted.length >> 1] > o.frameBudgetMs;
  }

  function tick(now: number): void {
    if (!alive) return;
    raf = requestAnimationFrame(tick);
    if (document.hidden || now - lastDraw < 1000 / o.fps - 1) return;
    lastDraw = now;
    const still = reduced.matches || tooCostly || o.paused();
    const dark = !!o.isDark();
    if (!advance(still, dark)) return;
    const started = performance.now();
    render(now, still, dark);
    if (!still) measureCost(performance.now() - started);
  }

  /* ---------- events ---------- */

  // The pointer only steers an animated frame: a still one is never redrawn for it.
  const onMove = (e: PointerEvent): void => {
    if (e.pointerType !== 'mouse') return;
    mx = e.clientX;
    my = e.clientY;
  };
  const onLeave = (): void => {
    mx = -1;
    my = -1;
  };
  let pending = false;
  const remeasure = (): void => {
    if (pending) return;
    pending = true;
    requestAnimationFrame(() => {
      pending = false;
      if (alive) measureSections();
    });
  };
  const onResize = (): void => {
    layout();
    remeasure();
  };

  window.addEventListener('pointermove', onMove, { passive: true });
  document.documentElement.addEventListener('pointerleave', onLeave);
  window.addEventListener('resize', onResize);
  const ro = typeof ResizeObserver !== 'undefined' ? new ResizeObserver(remeasure) : null;
  if (ro) ro.observe(document.body);

  layout();
  raf = requestAnimationFrame(tick);

  return {
    set(opts) {
      Object.assign(o, opts);
      if ('sections' in opts) measureSections();
      dirty = true;
    },
    refresh() {
      measureSections();
    },
    destroy() {
      alive = false;
      cancelAnimationFrame(raf);
      window.removeEventListener('pointermove', onMove);
      document.documentElement.removeEventListener('pointerleave', onLeave);
      window.removeEventListener('resize', onResize);
      if (ro) ro.disconnect();
      cv.remove();
    },
  };
}
