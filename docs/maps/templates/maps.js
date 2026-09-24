/* LIA living maps — one script for the three pages (docs/maps).
   The page embeds its data (#map-data); this script draws it. No dependency:
   icons are Lucide's own geometry, vendored in the data by the generator. */
(() => {
  'use strict';

  const D = JSON.parse(document.getElementById('map-data').textContent);
  const PAGE = D.page;
  const REDUCED = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
  const main = document.getElementById('main');

  // ---------------------------------------------------------------- helpers
  const ESC = { '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' };
  const esc = (s) => String(s).replace(/[&<>"']/g, (c) => ESC[c]);
  const norm = (s) => String(s).normalize('NFD').replace(/[̀-ͯ]/g, '').toLowerCase();
  const rad = (deg) => (deg * Math.PI) / 180;
  const round = (n) => Math.round(n * 10) / 10;
  const plural = (n, one, many) => `${n.toLocaleString('fr-FR')} ${n > 1 ? many : one}`;

  function icon(name, size = 18, cls = '') {
    const nodes = D.icons[name];
    if (!nodes) return '';
    const inner = nodes
      .map(([tag, attrs]) => `<${tag} ${Object.entries(attrs).map(([k, v]) => `${k}="${esc(v)}"`).join(' ')}/>`)
      .join('');
    return `<svg class="ic ${cls}" width="${size}" height="${size}" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${inner}</svg>`;
  }

  const DAY = new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'long', year: 'numeric', timeZone: 'UTC' });
  const DAY_SHORT = new Intl.DateTimeFormat('fr-FR', { day: 'numeric', month: 'short', year: 'numeric', timeZone: 'UTC' });
  const MONTH = new Intl.DateTimeFormat('fr-FR', { month: 'long', year: 'numeric', timeZone: 'UTC' });
  const MONTH_SHORT = new Intl.DateTimeFormat('fr-FR', { month: 'short', timeZone: 'UTC' });
  const asDate = (iso) => {
    const [y, m, d] = iso.split('-').map(Number);
    return new Date(Date.UTC(y, m - 1, d || 1));
  };
  const fmtDay = (iso) => DAY.format(asDate(iso));
  const fmtDayShort = (iso) => DAY_SHORT.format(asDate(iso));

  // ---------------------------------------------------------------- indexes
  const F = D.functional;
  const T = D.technical;
  const H = D.history;
  const fById = new Map(F.bricks.map((b) => [b.id, b]));
  const tById = new Map(T.bricks.map((b) => [b.id, b]));
  const groupById = new Map(F.groups.map((g) => [g.id, g]));
  const layerById = new Map(T.layers.map((l) => [l.id, l]));
  const themeById = new Map(H.themes.map((t) => [t.id, t]));
  const brickOf = (id) => fById.get(id) || tById.get(id);
  const isFunctional = (id) => id.startsWith('f.');
  const familyOf = (b) => (b.group ? groupById.get(b.group) : layerById.get(b.layer));
  const toneOf = (id) => {
    const b = brickOf(id);
    return b ? familyOf(b).tone : 'slate';
  };
  const hrefOfBrick = (id) => {
    const target = isFunctional(id) ? 'functional' : 'technical';
    return `${target === PAGE ? '' : D.pages[target].href}#${id}`;
  };
  const hrefOfAdr = (n) => `${PAGE === 'history' ? '' : D.pages.history.href}#adr-${n}`;
  const adrUrl = (n) => {
    const file = D.adrFiles[String(n)];
    return file ? `${D.repo}docs/architecture/${file}` : `${D.repo}docs/architecture/ADR_INDEX.md#adr-${String(n).padStart(3, '0')}`;
  };

  const adrsByBrick = new Map();
  for (const e of H.entries) {
    for (const id of [...e.functional, ...e.technical]) {
      if (!adrsByBrick.has(id)) adrsByBrick.set(id, []);
      adrsByBrick.get(id).push(e);
    }
  }
  for (const list of adrsByBrick.values()) list.sort((a, b) => b.adr - a.adr);

  function reverseDeps(bricks) {
    const out = new Map(bricks.map((b) => [b.id, []]));
    for (const b of bricks) for (const d of b.deps) if (out.has(d)) out.get(d).push(b.id);
    return out;
  }
  const usedBy = new Map([...reverseDeps(F.bricks), ...reverseDeps(T.bricks)]);

  function related(id) {
    // Bricks of the OTHER map that the same decisions shaped, most shared first.
    const other = isFunctional(id) ? 'technical' : 'functional';
    const counts = new Map();
    for (const e of adrsByBrick.get(id) || []) for (const o of e[other]) counts.set(o, (counts.get(o) || 0) + 1);
    return [...counts.entries()].sort((a, b) => b[1] - a[1] || a[0].localeCompare(b[0])).slice(0, 6).map(([o]) => o);
  }

  // ---------------------------------------------------------------- chrome
  function renderNav() {
    const nav = document.querySelector('.pages');
    nav.innerHTML = ['functional', 'technical', 'history']
      .map((key) => {
        const p = D.pages[key];
        const current = key === PAGE ? ' aria-current="page"' : '';
        return `<a href="${esc(p.href)}"${current} title="${esc(p.label)}">${icon(p.icon, 16)}<span>${esc(p.label)}</span></a>`;
      })
      .join('');
    document.querySelector('.foot-stamp').textContent = `Données de la version ${D.facts.version} (${fmtDay(D.facts.releaseDate)}).`;
  }

  function initTheme() {
    const btn = document.getElementById('theme-toggle');
    const root = document.documentElement;
    const initial = root.getAttribute('data-theme'); // a host may stamp it; never erase it unasked
    const order = ['system', 'light', 'dark'];
    const labels = { system: 'Thème : celui du système', light: 'Thème : clair', dark: 'Thème : sombre' };
    const glyphs = { system: 'monitor', light: 'sun', dark: 'moon' };
    let mode = null;
    try {
      mode = localStorage.getItem('lia-maps-theme');
    } catch (err) {
      mode = null;
    }
    const apply = (m) => {
      if (m === 'light' || m === 'dark') root.setAttribute('data-theme', m);
      else if (initial) root.setAttribute('data-theme', initial);
      else root.removeAttribute('data-theme');
      btn.innerHTML = icon(glyphs[m], 18);
      btn.setAttribute('aria-label', labels[m]);
      btn.title = labels[m];
    };
    const current = order.includes(mode) ? mode : 'system';
    if (order.includes(mode)) apply(current);
    else {
      btn.innerHTML = icon('monitor', 18);
      btn.setAttribute('aria-label', labels.system);
      btn.title = labels.system;
    }
    let m = current;
    btn.addEventListener('click', () => {
      m = order[(order.indexOf(m) + 1) % order.length];
      apply(m);
      try {
        localStorage.setItem('lia-maps-theme', m);
      } catch (err) {
        /* storage refused: the choice lasts for this view only */
      }
    });
  }

  // ---------------------------------------------------------------- tooltip
  const tip = document.querySelector('.tip');
  function showTip(html, x, y) {
    tip.innerHTML = html;
    tip.hidden = false;
    const w = tip.offsetWidth;
    const h = tip.offsetHeight;
    const left = Math.min(Math.max(8, x + 14), window.innerWidth - w - 8);
    const top = y + h + 20 > window.innerHeight ? y - h - 12 : y + 16;
    tip.style.left = `${left}px`;
    tip.style.top = `${Math.max(8, top)}px`;
  }
  const hideTip = () => {
    tip.hidden = true;
  };

  // ---------------------------------------------------------------- drawer
  const drawer = document.getElementById('drawer');
  const scrim = document.querySelector('.drawer-scrim');
  const drawerTitle = document.getElementById('drawer-title');
  const drawerBody = document.getElementById('drawer-body');
  const drawerClose = document.getElementById('drawer-close');
  drawerClose.innerHTML = icon('x', 18);
  let lastFocus = null;
  let onDrawerClose = null;

  function openDrawer(titleHtml, bodyHtml, onClose) {
    if (drawer.hidden) lastFocus = document.activeElement;
    drawerTitle.innerHTML = titleHtml;
    drawerBody.innerHTML = bodyHtml;
    drawerBody.scrollTop = 0;
    drawer.hidden = false;
    scrim.hidden = false;
    onDrawerClose = onClose || null;
    drawerClose.focus({ preventScroll: true });
  }
  function closeDrawer() {
    if (drawer.hidden) return;
    drawer.hidden = true;
    scrim.hidden = true;
    const cb = onDrawerClose;
    onDrawerClose = null;
    if (cb) cb();
    if (lastFocus && document.contains(lastFocus)) lastFocus.focus({ preventScroll: true });
  }
  drawerClose.addEventListener('click', closeDrawer);
  scrim.addEventListener('click', closeDrawer);
  document.addEventListener('keydown', (ev) => {
    if (ev.key === 'Escape') closeDrawer();
    if (ev.key === 'Tab' && !drawer.hidden) {
      const items = [...drawer.querySelectorAll('a[href], button:not([disabled])')];
      if (!items.length) return;
      const first = items[0];
      const last = items[items.length - 1];
      if (ev.shiftKey && document.activeElement === first) {
        last.focus();
        ev.preventDefault();
      } else if (!ev.shiftKey && document.activeElement === last) {
        first.focus();
        ev.preventDefault();
      }
    }
  });

  // ---------------------------------------------------------------- shared markup
  function brickChip(id, extra = '') {
    const b = brickOf(id);
    if (!b) return '';
    const cls = isFunctional(id) ? 'chip' : 'chip tech';
    return `<a class="${cls} ${extra}" data-tone="${toneOf(id)}" data-brick="${esc(id)}" href="${esc(hrefOfBrick(id))}">${icon(b.icon, 14)}${esc(b.name)}</a>`;
  }
  function chipsOrEmpty(ids, empty) {
    return ids.length ? `<div class="chips">${ids.map((i) => brickChip(i)).join('')}</div>` : `<p class="empty">${esc(empty)}</p>`;
  }
  function stat(value, label) {
    return `<div class="stat"><b>${esc(value)}</b><span>${esc(label)}</span></div>`;
  }
  function hero(eyebrow, titleHtml, lede, stats) {
    return `<section class="hero">
      <p class="eyebrow"><span class="pulse" aria-hidden="true"></span>${esc(eyebrow)}</p>
      <h1>${titleHtml}</h1>
      <p class="lede">${esc(lede)}</p>
      <div class="stats">${stats.join('')}</div>
      <p class="stamp">${icon('git-commit-horizontal', 16)}Version ${esc(D.facts.version)}<span class="dot"></span>${esc(fmtDay(D.facts.releaseDate))}<span class="dot"></span>régénérée à chaque commit depuis les données du dépôt</p>
    </section>`;
  }

  function brickDrawer(id, playFlow) {
    const b = brickOf(id);
    const fam = familyOf(b);
    const tone = fam.tone;
    const title = `<span class="badge-ic" data-tone="${tone}">${icon(b.icon, 20)}</span><div><h2>${esc(b.name)}</h2><p class="meta">${esc(isFunctional(id) ? 'Famille' : 'Couche')} · ${esc(fam.name)}</p></div>`;
    const parts = [];
    parts.push(`<div class="dsec"><h4>${icon('info', 14)}Rôle</h4><p>${esc(b.role)}</p></div>`);
    if (b.goal) parts.push(`<div class="dsec"><p class="goal">${esc(b.goal)}</p></div>`);
    if (b.stack) {
      parts.push(`<div class="dsec"><h4>${icon('layers', 14)}Technologies</h4><div class="chips">${b.stack.map((s) => `<span class="chip plain">${esc(s)}</span>`).join('')}</div></div>`);
    }
    parts.push(`<div class="dsec"><h4>${icon('arrow-right', 14)}S'appuie sur</h4>${chipsOrEmpty(b.deps, 'Aucune autre brique : elle est un socle.')}</div>`);
    parts.push(`<div class="dsec"><h4>${icon('corner-down-right', 14)}Utilisée par</h4>${chipsOrEmpty(usedBy.get(id) || [], 'Aucune brique ne dépend d’elle directement.')}</div>`);
    const flows = (isFunctional(id) ? F.flows : T.flows).filter((f) => f.steps.some((s) => s.brick === id));
    if (flows.length) {
      parts.push(`<div class="dsec"><h4>${icon('route', 14)}Parcours</h4><div class="chips">${flows
        .map((f) => `<button type="button" class="chip" data-play="${esc(f.id)}">${icon('play', 14)}${esc(f.name)}</button>`)
        .join('')}</div></div>`);
    }
    if (b.domains) {
      parts.push(`<div class="dsec"><h4>${icon('boxes', 14)}Domaines backend</h4><div class="chips">${b.domains
        .map((d) => `<a class="chip mono" href="${esc(`${D.repo}apps/api/src/domains/${d}`)}" target="_blank" rel="noopener">${esc(d)}</a>`)
        .join('')}</div></div>`);
    }
    if (b.surfaces && b.surfaces.length) {
      parts.push(`<div class="dsec"><h4>${icon('monitor', 14)}Écrans</h4><div class="chips">${b.surfaces
        .map((s) => `<span class="chip mono plain">${esc(s)}</span>`)
        .join('')}</div></div>`);
    }
    if (b.paths) {
      parts.push(`<div class="dsec"><h4>${icon('file-code', 14)}Dans le dépôt</h4><div class="chips">${b.paths
        .map((p) => `<a class="chip mono" href="${esc(D.repo + p)}" target="_blank" rel="noopener">${esc(p)}</a>`)
        .join('')}</div></div>`);
    }
    const rel = related(id);
    if (rel.length) {
      parts.push(`<div class="dsec"><h4>${icon('share-2', 14)}${isFunctional(id) ? 'Côté technique' : 'Côté fonctionnel'}</h4><div class="chips">${rel
        .map((r) => brickChip(r))
        .join('')}</div></div>`);
    }
    const adrs = adrsByBrick.get(id) || [];
    const shown = adrs.slice(0, 10);
    parts.push(`<div class="dsec"><h4>${icon('scroll-text', 14)}Décisions qui l'ont façonnée (${adrs.length})</h4>${
      adrs.length
        ? `<ul class="adr-list">${shown
            .map((e) => `<li><a href="${esc(hrefOfAdr(e.adr))}" data-tone="${themeById.get(e.theme).tone}"><span class="no">ADR-${String(e.adr).padStart(3, '0')}</span><span class="tt">${esc(e.title)}</span><span class="dt">${esc(fmtDayShort(e.date))}</span></a></li>`)
            .join('')}</ul>${adrs.length > shown.length ? `<p style="margin-top:8px"><a href="${esc(`${D.pages.history.href}#${id}`)}">Voir les ${adrs.length} décisions dans l'historique</a></p>` : ''}`
        : '<p class="empty">Aucune décision ne la cite encore.</p>'
    }</div>`);
    openDrawer(title, parts.join(''));
    drawerBody.querySelectorAll('[data-play]').forEach((btn) => {
      btn.addEventListener('click', () => {
        closeDrawer();
        playFlow(btn.dataset.play);
      });
    });
  }

  // Clicking a chip of the page's own map selects it instead of navigating away.
  function wireLocalChips(root, select) {
    root.addEventListener('click', (ev) => {
      const a = ev.target.closest('a[data-brick]');
      if (!a) return;
      const id = a.dataset.brick;
      const local = (PAGE === 'functional' && isFunctional(id)) || (PAGE === 'technical' && !isFunctional(id));
      if (!local) return;
      ev.preventDefault();
      select(id);
    });
  }

  // ---------------------------------------------------------------- flow player (both maps)
  function makePlayer(flows, host, painter) {
    let flowIdx = -1;
    let stepIdx = 0;
    let timer = null;
    host.innerHTML = `<h3>${icon('route', 18)}Parcours</h3><p class="sub">Choisis un scénario : ses étapes s'allument une à une sur la carte.</p>
      <div class="flow-list">${flows
        .map((f, i) => `<button type="button" class="flow-btn" data-flow="${i}" aria-pressed="false">${icon(f.icon, 16)}<span>${esc(f.name)}</span></button>`)
        .join('')}</div>`;
    host.querySelector('.sub').insertAdjacentHTML('afterend', '<div class="player" hidden></div>');
    const player = host.querySelector('.player');
    const buttons = [...host.querySelectorAll('.flow-btn')];

    function stop() {
      if (timer) clearInterval(timer);
      timer = null;
      const pb = player.querySelector('[data-act="play"]');
      if (pb) {
        pb.innerHTML = icon('play', 16);
        pb.setAttribute('aria-label', 'Lire le parcours');
      }
    }
    function setStep(i) {
      const flow = flows[flowIdx];
      stepIdx = Math.max(0, Math.min(i, flow.steps.length - 1));
      player.querySelectorAll('.step').forEach((li, k) => {
        li.classList.toggle('is-current', k === stepIdx);
        li.classList.toggle('is-done', k < stepIdx);
        li.setAttribute('aria-current', k === stepIdx ? 'step' : 'false');
      });
      player.querySelector('.count').textContent = `Étape ${stepIdx + 1} / ${flow.steps.length}`;
      painter.step(flow, stepIdx);
    }
    function play() {
      stop();
      const flow = flows[flowIdx];
      if (stepIdx >= flow.steps.length - 1) setStep(0);
      const pb = player.querySelector('[data-act="play"]');
      pb.innerHTML = icon('pause', 16);
      pb.setAttribute('aria-label', 'Mettre en pause');
      timer = setInterval(() => {
        if (stepIdx >= flows[flowIdx].steps.length - 1) stop();
        else setStep(stepIdx + 1);
      }, 2400);
    }
    function select(i, autoplay) {
      stop();
      flowIdx = i;
      buttons.forEach((b, k) => b.setAttribute('aria-pressed', String(k === i)));
      const flow = flows[i];
      player.hidden = false;
      player.innerHTML = `<p class="sub">${esc(flow.summary)}</p>
        <div class="player-controls" style="margin-top:10px">
          <button type="button" class="icon-btn" data-act="prev" aria-label="Étape précédente">${icon('step-back', 16)}</button>
          <button type="button" class="icon-btn" data-act="play" aria-label="Lire le parcours">${icon('play', 16)}</button>
          <button type="button" class="icon-btn" data-act="next" aria-label="Étape suivante">${icon('step-forward', 16)}</button>
          <button type="button" class="icon-btn" data-act="quit" aria-label="Quitter le parcours">${icon('x', 16)}</button>
          <span class="count" aria-live="polite"></span>
        </div>
        <ol class="steps">${flow.steps
          .map((s, k) => {
            const b = brickOf(s.brick);
            return `<li class="step" data-step="${k}" tabindex="0"><span class="num">${k + 1}</span><div><b>${esc(b.name)}</b><span>${esc(s.text)}</span></div></li>`;
          })
          .join('')}</ol>`;
      player.querySelector('[data-act="prev"]').addEventListener('click', () => {
        stop();
        setStep(stepIdx - 1);
      });
      player.querySelector('[data-act="next"]').addEventListener('click', () => {
        stop();
        setStep(stepIdx + 1);
      });
      player.querySelector('[data-act="play"]').addEventListener('click', () => (timer ? stop() : play()));
      player.querySelector('[data-act="quit"]').addEventListener('click', clear);
      player.querySelectorAll('.step').forEach((li) => {
        const go = () => {
          stop();
          setStep(Number(li.dataset.step));
        };
        li.addEventListener('click', go);
        li.addEventListener('keydown', (ev) => {
          if (ev.key === 'Enter' || ev.key === ' ') {
            ev.preventDefault();
            go();
          }
        });
      });
      painter.start(flow);
      setStep(0);
      if (autoplay && !REDUCED) play();
    }
    function clear() {
      stop();
      flowIdx = -1;
      buttons.forEach((b) => b.setAttribute('aria-pressed', 'false'));
      player.hidden = true;
      player.innerHTML = '';
      painter.clear();
    }
    buttons.forEach((b, i) => b.addEventListener('click', () => (flowIdx === i ? clear() : select(i, true))));
    return {
      playById(id) {
        const i = flows.findIndex((f) => f.id === id);
        if (i >= 0) {
          select(i, true);
          host.scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'nearest' });
        }
      },
      active: () => flowIdx >= 0,
      clear,
    };
  }

  function flowCards(flows, onReplay) {
    return `<div class="flows-grid">${flows
      .map(
        (f) => `<article class="flow-card"><h3><span class="badge-ic" data-tone="blue">${icon(f.icon, 18)}</span>${esc(f.name)}</h3><p>${esc(f.summary)}</p>
        <ol>${f.steps
          .map((s, k) => `<li><span class="num">${k + 1}</span><div>${brickChip(s.brick)}<div>${esc(s.text)}</div></div></li>`)
          .join('')}</ol>
        <button type="button" class="linkish" data-replay="${esc(f.id)}">${icon('play', 14)}Rejouer sur la carte</button></article>`
      )
      .join('')}</div>`;
  }

  // ================================================================ FUNCTIONAL
  function functionalPage() {
    const bricks = F.bricks;
    main.insertAdjacentHTML(
      'beforeend',
      hero('Documentation vivante · carte fonctionnelle', `Ce que <span class="grad-text">LIA</span> sait faire, et comment tout s'enchaîne`, F.lede, [
        stat(String(bricks.length), 'briques fonctionnelles'),
        stat(String(F.groups.length), 'familles'),
        stat(String(F.flows.length), 'parcours commentés'),
        stat(String(D.facts.domains), 'domaines métier dans le code'),
        stat(String(D.facts.adrFiles), 'décisions reliées'),
      ])
    );
    main.insertAdjacentHTML(
      'beforeend',
      `<section class="section" aria-labelledby="ov-title">
        <div class="section-head"><div><p class="kicker">Vue d'ensemble</p><h2 id="ov-title">La constellation des briques</h2>
        <p>Chaque point est une brique, colorée par famille. Un trait relie une brique à celles dont elle a besoin. Survole pour voir ses liens, clique pour tout savoir.</p></div></div>
        <div class="overview">
          <div class="stage">
            <div class="stage-toolbar">
              <label class="search">${icon('search', 16)}<span class="sr">Chercher une brique</span><input id="q" type="search" placeholder="Chercher une brique, un domaine, un mot…" autocomplete="off"></label>
              <span class="hint">${icon('arrow-right', 14)}<span style="color:var(--accent)">s'appuie sur</span> · <span style="color:var(--t-rose)">utilisée par</span></span>
            </div>
            <div class="scroll-x" id="graph"></div>
          </div>
          <div class="side">
            <div class="card" id="flows"></div>
            <div class="card" id="legend"></div>
          </div>
        </div>
      </section>`
    );
    main.insertAdjacentHTML(
      'beforeend',
      `<section class="section" aria-labelledby="fam-title"><div class="section-head"><div><p class="kicker">Les familles</p><h2 id="fam-title">Toutes les briques, par famille</h2>
      <p>Le rôle en une ligne ; le détail, les dépendances et les décisions en un clic.</p></div></div><div class="families" id="families"></div></section>`
    );
    main.insertAdjacentHTML(
      'beforeend',
      `<section class="section" aria-labelledby="flows-title"><div class="section-head"><div><p class="kicker">Les parcours</p><h2 id="flows-title">Ce qui se passe quand…</h2>
      <p>Des scénarios réels, étape par étape, à travers les briques qu'ils traversent.</p></div></div>${flowCards(F.flows)}</section>`
    );

    // --- constellation geometry
    const W = 1200;
    const C = W / 2;
    const R = 300;
    const gap = 5;
    const step = (360 - F.groups.length * gap) / bricks.length;
    const pos = new Map();
    const arcs = [];
    let a = -90 + gap / 2;
    for (const g of F.groups) {
      const start = a;
      for (const b of bricks.filter((x) => x.group === g.id)) {
        const ang = a + step / 2;
        pos.set(b.id, { ang, x: C + R * Math.cos(rad(ang)), y: C + R * Math.sin(rad(ang)) });
        a += step;
      }
      arcs.push({ g, start, end: a });
      a += gap;
    }
    const arcPath = (r, s, e) => {
      const p1 = [C + r * Math.cos(rad(s)), C + r * Math.sin(rad(s))];
      const p2 = [C + r * Math.cos(rad(e)), C + r * Math.sin(rad(e))];
      return `M${round(p1[0])} ${round(p1[1])} A${r} ${r} 0 ${e - s > 180 ? 1 : 0} 1 ${round(p2[0])} ${round(p2[1])}`;
    };
    const curve = (from, to, k) => {
      const p = pos.get(from);
      const q = pos.get(to);
      const cx = C + ((p.x + q.x) / 2 - C) * k;
      const cy = C + ((p.y + q.y) / 2 - C) * k;
      return { p, q, c: [round(cx), round(cy)] };
    };
    const edges = [];
    for (const b of bricks) for (const d of b.deps) edges.push([b.id, d]);
    const nodeMarkup = bricks
      .map((b) => {
        const { ang, x, y } = pos.get(b.id);
        const left = ang > 90 && ang < 270;
        const rot = round(left ? ang - 180 : ang);
        const g = groupById.get(b.group);
        return `<g class="node" data-id="${b.id}" data-tone="${g.tone}" tabindex="0" role="button" aria-label="${esc(`${b.name} — ${g.name}`)}" transform="translate(${round(x)} ${round(y)})">
          <circle r="7" style="transform-box:fill-box;transform-origin:center"/><text x="${left ? -16 : 16}" text-anchor="${left ? 'end' : 'start'}" transform="rotate(${rot})">${esc(b.name)}</text></g>`;
      })
      .join('');
    document.getElementById('graph').innerHTML = `<svg class="constellation" id="cst" viewBox="0 0 ${W} ${W}" role="group" aria-label="Constellation des briques fonctionnelles">
      <defs><linearGradient id="flowgrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4f8dfd"/><stop offset="0.55" stop-color="#8b5cf6"/><stop offset="1" stop-color="#38d4f5"/></linearGradient></defs>
      <g>${arcs.map(({ g, start, end }) => `<path class="arc" data-tone="${g.tone}" data-group="${g.id}" d="${arcPath(R - 24, start + 0.6, end - 0.6)}"/>`).join('')}</g>
      <g id="edges">${edges
        .map(([f, t]) => {
          const { p, q, c } = curve(f, t, 0.22);
          return `<path class="edge" data-from="${f}" data-to="${t}" d="M${round(p.x)} ${round(p.y)} Q${c[0]} ${c[1]} ${round(q.x)} ${round(q.y)}"/>`;
        })
        .join('')}</g>
      <g id="flowpath"></g>
      <g class="core" aria-hidden="true"><text class="big" x="${C}" y="${C - 6}">LIA</text><text x="${C}" y="${C + 30}">${bricks.length} briques · ${F.groups.length} familles</text></g>
      <g id="nodes">${nodeMarkup}</g>
      <g id="badges"></g>
    </svg>`;

    const svg = document.getElementById('cst');
    const nodeEl = new Map([...svg.querySelectorAll('.node')].map((n) => [n.dataset.id, n]));
    const edgeEls = [...svg.querySelectorAll('.edge')];
    let selected = null;
    let groupFocus = null;
    let query = '';

    function reset() {
      svg.classList.remove('is-focus');
      nodeEl.forEach((n) => n.classList.remove('on', 'near'));
      edgeEls.forEach((e) => e.classList.remove('out', 'in'));
    }
    function focusBrick(id) {
      reset();
      svg.classList.add('is-focus');
      nodeEl.get(id).classList.add('on');
      for (const e of edgeEls) {
        if (e.dataset.from === id) {
          e.classList.add('out');
          nodeEl.get(e.dataset.to).classList.add('near');
        } else if (e.dataset.to === id) {
          e.classList.add('in');
          nodeEl.get(e.dataset.from).classList.add('near');
        }
      }
    }
    function focusSet(ids) {
      reset();
      svg.classList.add('is-focus');
      ids.forEach((id) => nodeEl.get(id).classList.add('on'));
    }
    function restore() {
      if (player.active()) return;
      if (selected) focusBrick(selected);
      else if (groupFocus) focusSet(bricks.filter((b) => b.group === groupFocus).map((b) => b.id));
      else if (query) focusSet(matches(query));
      else reset();
    }
    function matches(q) {
      const n = norm(q);
      return bricks
        .filter((b) => norm([b.name, b.role, b.goal, groupById.get(b.group).name, ...(b.domains || []), ...(b.surfaces || [])].join(' ')).includes(n))
        .map((b) => b.id);
    }
    function select(id) {
      if (player.active()) player.clear();
      selected = id;
      focusBrick(id);
      history.replaceState(null, '', `#${id}`);
      brickDrawer(id, (fid) => player.playById(fid));
      onDrawerClose = () => {
        selected = null;
        history.replaceState(null, '', location.pathname + location.search);
        restore();
      };
    }

    nodeEl.forEach((n, id) => {
      n.addEventListener('mouseenter', () => {
        if (!player.active()) focusBrick(id);
      });
      n.addEventListener('mouseleave', restore);
      n.addEventListener('focus', () => {
        if (!player.active()) focusBrick(id);
      });
      n.addEventListener('blur', restore);
      n.addEventListener('click', () => select(id));
      n.addEventListener('keydown', (ev) => {
        if (ev.key === 'Enter' || ev.key === ' ') {
          ev.preventDefault();
          select(id);
        }
      });
    });

    // --- legend (families)
    const legend = document.getElementById('legend');
    legend.innerHTML = `<h3>${icon('layout-grid', 18)}Familles</h3><p class="sub">Clique une famille pour l'isoler sur la carte.</p><div class="legend">${F.groups
      .map((g) => `<button type="button" data-group="${g.id}" data-tone="${g.tone}" aria-pressed="false"><span class="sw"></span>${esc(g.name)}<span class="n">${bricks.filter((b) => b.group === g.id).length}</span></button>`)
      .join('')}</div>`;
    legend.querySelectorAll('button').forEach((btn) => {
      btn.addEventListener('click', () => {
        const gid = btn.dataset.group;
        groupFocus = groupFocus === gid ? null : gid;
        legend.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.group === groupFocus)));
        if (player.active()) player.clear();
        restore();
      });
    });

    // --- flow painter
    const flowLayer = svg.querySelector('#flowpath');
    const badgeLayer = svg.querySelector('#badges');
    const painter = {
      start(flow) {
        selected = null;
        const ids = flow.steps.map((s) => s.brick);
        const segs = [];
        for (let i = 1; i < ids.length; i += 1) {
          if (ids[i] === ids[i - 1]) continue;
          const { p, q, c } = curve(ids[i - 1], ids[i], 0.42);
          segs.push(`${segs.length ? '' : `M${round(p.x)} ${round(p.y)} `}Q${c[0]} ${c[1]} ${round(q.x)} ${round(q.y)}`);
        }
        flowLayer.innerHTML = segs.length ? `<path class="flowpath${REDUCED ? '' : ' animate'}" d="${segs.join(' ')}"/>` : '';
        const byBrick = new Map();
        ids.forEach((id, k) => byBrick.set(id, [...(byBrick.get(id) || []), k + 1]));
        badgeLayer.innerHTML = [...byBrick.entries()]
          .map(([id, nums]) => {
            const p = pos.get(id);
            const bx = C + (R - 52) * Math.cos(rad(p.ang));
            const by = C + (R - 52) * Math.sin(rad(p.ang));
            return `<g class="badge" data-id="${id}" transform="translate(${round(bx)} ${round(by)})"><circle r="13"/><text>${nums.join('·')}</text></g>`;
          })
          .join('');
      },
      step(flow, i) {
        const ids = [...new Set(flow.steps.map((s) => s.brick))];
        focusSet(ids);
        const cur = flow.steps[i].brick;
        nodeEl.forEach((n, id) => n.classList.toggle('near', ids.includes(id) && id !== cur));
        nodeEl.get(cur).classList.add('on');
        ids.filter((id) => id !== cur).forEach((id) => nodeEl.get(id).classList.remove('on'));
        badgeLayer.querySelectorAll('.badge').forEach((b) => b.classList.toggle('current', b.dataset.id === cur));
      },
      clear() {
        flowLayer.innerHTML = '';
        badgeLayer.innerHTML = '';
        restore();
      },
    };
    const player = makePlayer(F.flows, document.getElementById('flows'), painter);

    // --- families grid
    const fam = document.getElementById('families');
    fam.innerHTML = F.groups
      .map((g) => {
        const list = bricks.filter((b) => b.group === g.id);
        return `<article class="family" data-tone="${g.tone}"><div class="family-head"><span class="badge-ic">${icon(g.icon, 20)}</span><div><h3>${esc(g.name)}</h3><p>${esc(g.summary)}</p></div></div>
        <ul class="brick-list">${list
          .map((b) => `<li><button type="button" class="brick-row" data-id="${b.id}">${icon(b.icon, 18)}<b>${esc(b.name)}</b><small>${esc(b.goal)}</small></button></li>`)
          .join('')}</ul></article>`;
      })
      .join('');
    fam.querySelectorAll('.brick-row').forEach((row) => row.addEventListener('click', () => select(row.dataset.id)));

    // --- search
    const q = document.getElementById('q');
    q.addEventListener('input', () => {
      query = q.value.trim();
      const hit = query ? new Set(matches(query)) : null;
      fam.querySelectorAll('.brick-row').forEach((row) => {
        row.parentElement.hidden = Boolean(hit) && !hit.has(row.dataset.id);
      });
      fam.querySelectorAll('.family').forEach((f) => {
        f.hidden = [...f.querySelectorAll('li')].every((li) => li.hidden);
      });
      if (player.active()) player.clear();
      restore();
    });
    q.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' && query) {
        const first = matches(query)[0];
        if (first) select(first);
      }
    });

    // --- replay buttons + local chips
    main.querySelectorAll('[data-replay]').forEach((btn) => btn.addEventListener('click', () => player.playById(btn.dataset.replay)));
    wireLocalChips(main, select);
    wireLocalChips(drawerBody, select);

    // --- deep link
    const hash = decodeURIComponent(location.hash.slice(1));
    if (fById.has(hash)) {
      select(hash);
      nodeEl.get(hash).scrollIntoView({ block: 'center' });
    }
  }

  // ================================================================ TECHNICAL
  function technicalPage() {
    const bricks = T.bricks;
    main.insertAdjacentHTML(
      'beforeend',
      hero('Documentation vivante · carte technique', `Comment <span class="grad-text">LIA</span> est construite, couche par couche`, T.lede, [
        stat(String(bricks.length), 'briques techniques'),
        stat(String(T.layers.length), 'couches'),
        stat(String(T.flows.length), 'parcours commentés'),
        stat(String(D.facts.infra), 'modules d’infrastructure'),
        stat(String(D.facts.domains), 'domaines métier servis'),
      ])
    );
    main.insertAdjacentHTML(
      'beforeend',
      `<section class="section" aria-labelledby="ov-title">
        <div class="section-head"><div><p class="kicker">Vue d'ensemble</p><h2 id="ov-title">Les couches du système</h2>
        <p>De l'écran à la base de données. Survole une brique pour tracer ses liens, clique pour ses technologies, ses fichiers et ses décisions.</p></div></div>
        <div class="overview">
          <div class="stage">
            <div class="stage-toolbar">
              <label class="search">${icon('search', 16)}<span class="sr">Chercher une brique</span><input id="q" type="search" placeholder="Chercher une brique, une technologie, un chemin…" autocomplete="off"></label>
              <span class="hint">${icon('arrow-right', 14)}<span style="color:var(--accent)">s'appuie sur</span> · <span style="color:var(--t-rose)">utilisée par</span></span>
            </div>
            <div class="layers" id="layers"></div>
          </div>
          <div class="side">
            <div class="card" id="flows"></div>
            <div class="card" id="legend"></div>
          </div>
        </div>
      </section>`
    );
    main.insertAdjacentHTML(
      'beforeend',
      `<section class="section" aria-labelledby="flows-title"><div class="section-head"><div><p class="kicker">Les parcours</p><h2 id="flows-title">Le chemin d'une requête, d'un appel, d'une livraison</h2>
      <p>Chaque étape nomme la brique qui agit et ce qu'elle garantit.</p></div></div>${flowCards(T.flows)}</section>`
    );

    const host = document.getElementById('layers');
    host.innerHTML = `<svg class="links-layer" aria-hidden="true"><defs><linearGradient id="tflowgrad" x1="0" y1="0" x2="1" y2="1"><stop offset="0" stop-color="#4f8dfd"/><stop offset="0.55" stop-color="#8b5cf6"/><stop offset="1" stop-color="#38d4f5"/></linearGradient></defs><g id="links"></g></svg>${T.layers
      .map(
        (l) => `<section class="layer" data-tone="${l.tone}" aria-label="${esc(l.name)}"><div class="layer-head"><span class="badge-ic">${icon(l.icon, 18)}</span><div><h3>${esc(l.name)}</h3><p>${esc(l.summary)}</p></div></div>
        <div class="layer-bricks">${bricks
          .filter((b) => b.layer === l.id)
          .map((b) => `<button type="button" class="tbrick" data-id="${b.id}" data-tone="${l.tone}">${icon(b.icon, 16)}<span>${esc(b.name)}</span></button>`)
          .join('')}</div></section>`
      )
      .join('')}`;
    const links = host.querySelector('#links');
    const btnEl = new Map([...host.querySelectorAll('.tbrick')].map((b) => [b.dataset.id, b]));
    let selected = null;
    let layerFocus = null;
    let query = '';
    let flowState = null;

    function rectOf(id) {
      const r = btnEl.get(id).getBoundingClientRect();
      const c = host.getBoundingClientRect();
      return { x: r.left - c.left, y: r.top - c.top, w: r.width, h: r.height };
    }
    function connector(a, b) {
      const p = rectOf(a);
      const q = rectOf(b);
      const pc = { x: p.x + p.w / 2, y: p.y + p.h / 2 };
      const qc = { x: q.x + q.w / 2, y: q.y + q.h / 2 };
      if (Math.abs(pc.y - qc.y) < p.h) {
        const dir = qc.x > pc.x ? 1 : -1;
        const x1 = dir > 0 ? p.x + p.w : p.x;
        const x2 = dir > 0 ? q.x : q.x + q.w;
        const lift = 28;
        return `M${round(x1)} ${round(pc.y)} C${round(x1 + dir * 30)} ${round(pc.y - lift)} ${round(x2 - dir * 30)} ${round(qc.y - lift)} ${round(x2)} ${round(qc.y)}`;
      }
      const down = qc.y > pc.y;
      const y1 = down ? p.y + p.h : p.y;
      const y2 = down ? q.y : q.y + q.h;
      const mid = (y1 + y2) / 2;
      return `M${round(pc.x)} ${round(y1)} C${round(pc.x)} ${round(mid)} ${round(qc.x)} ${round(mid)} ${round(qc.x)} ${round(y2)}`;
    }
    function reset() {
      host.classList.remove('is-focus');
      btnEl.forEach((b) => b.classList.remove('on', 'near'));
      links.innerHTML = '';
    }
    function focusBrick(id) {
      reset();
      host.classList.add('is-focus');
      btnEl.get(id).classList.add('on');
      const b = tById.get(id);
      const paths = [];
      for (const d of b.deps) {
        btnEl.get(d).classList.add('near');
        paths.push(`<path class="out" d="${connector(id, d)}"/>`);
      }
      for (const u of usedBy.get(id) || []) {
        btnEl.get(u).classList.add('near');
        paths.push(`<path class="in" d="${connector(u, id)}"/>`);
      }
      links.innerHTML = paths.join('');
    }
    function focusSet(ids) {
      reset();
      host.classList.add('is-focus');
      ids.forEach((id) => btnEl.get(id).classList.add('on'));
    }
    function matches(q) {
      const n = norm(q);
      return bricks
        .filter((b) => norm([b.name, b.role, layerById.get(b.layer).name, ...(b.stack || []), ...(b.paths || [])].join(' ')).includes(n))
        .map((b) => b.id);
    }
    function restore() {
      if (flowState) {
        painter.step(flowState.flow, flowState.i);
        return;
      }
      if (selected) focusBrick(selected);
      else if (layerFocus) focusSet(bricks.filter((b) => b.layer === layerFocus).map((b) => b.id));
      else if (query) focusSet(matches(query));
      else reset();
    }
    function select(id) {
      if (player.active()) player.clear();
      selected = id;
      focusBrick(id);
      history.replaceState(null, '', `#${id}`);
      brickDrawer(id, (fid) => player.playById(fid));
      onDrawerClose = () => {
        selected = null;
        history.replaceState(null, '', location.pathname + location.search);
        restore();
      };
    }
    btnEl.forEach((b, id) => {
      b.addEventListener('mouseenter', () => {
        if (!flowState) focusBrick(id);
      });
      b.addEventListener('mouseleave', restore);
      b.addEventListener('focus', () => {
        if (!flowState) focusBrick(id);
      });
      b.addEventListener('blur', restore);
      b.addEventListener('click', () => select(id));
    });

    const legend = document.getElementById('legend');
    legend.innerHTML = `<h3>${icon('rows-3', 18)}Couches</h3><p class="sub">Clique une couche pour l'isoler.</p><div class="legend">${T.layers
      .map((l) => `<button type="button" data-layer="${l.id}" data-tone="${l.tone}" aria-pressed="false"><span class="sw"></span>${esc(l.name)}<span class="n">${bricks.filter((b) => b.layer === l.id).length}</span></button>`)
      .join('')}</div>`;
    legend.querySelectorAll('button').forEach((btn) => {
      btn.addEventListener('click', () => {
        const lid = btn.dataset.layer;
        layerFocus = layerFocus === lid ? null : lid;
        legend.querySelectorAll('button').forEach((b) => b.setAttribute('aria-pressed', String(b.dataset.layer === layerFocus)));
        if (player.active()) player.clear();
        restore();
      });
    });

    const painter = {
      start(flow) {
        selected = null;
        flowState = { flow, i: 0 };
      },
      step(flow, i) {
        flowState = { flow, i };
        const ids = flow.steps.map((s) => s.brick);
        const unique = [...new Set(ids)];
        focusSet(unique);
        const cur = ids[i];
        btnEl.forEach((b, id) => {
          b.classList.toggle('near', unique.includes(id) && id !== cur);
          b.classList.toggle('on', id === cur);
          const old = b.querySelector('.stepbadge');
          if (old) old.remove();
        });
        const byBrick = new Map();
        ids.forEach((id, k) => byBrick.set(id, [...(byBrick.get(id) || []), k + 1]));
        byBrick.forEach((nums, id) => {
          btnEl.get(id).insertAdjacentHTML('beforeend', `<span class="stepbadge${id === cur ? ' current' : ''}">${nums.join('·')}</span>`);
        });
        const segs = [];
        for (let k = 1; k <= i; k += 1) if (ids[k] !== ids[k - 1]) segs.push(connector(ids[k - 1], ids[k]));
        links.innerHTML = segs.map((d) => `<path class="flow${REDUCED ? '' : ' animate'}" d="${d}"/>`).join('');
      },
      clear() {
        flowState = null;
        btnEl.forEach((b) => {
          const old = b.querySelector('.stepbadge');
          if (old) old.remove();
        });
        restore();
      },
    };
    const player = makePlayer(T.flows, document.getElementById('flows'), painter);

    const q = document.getElementById('q');
    q.addEventListener('input', () => {
      query = q.value.trim();
      if (player.active()) player.clear();
      restore();
    });
    q.addEventListener('keydown', (ev) => {
      if (ev.key === 'Enter' && query) {
        const first = matches(query)[0];
        if (first) select(first);
      }
    });
    if ('ResizeObserver' in window) new ResizeObserver(() => restore()).observe(host);
    main.querySelectorAll('[data-replay]').forEach((btn) => btn.addEventListener('click', () => player.playById(btn.dataset.replay)));
    wireLocalChips(main, select);
    wireLocalChips(drawerBody, select);

    const hash = decodeURIComponent(location.hash.slice(1));
    if (tById.has(hash)) {
      btnEl.get(hash).scrollIntoView({ block: 'center' });
      select(hash);
    }
  }

  // ================================================================ HISTORY
  function historyPage() {
    const entries = H.entries;
    const months = [];
    {
      const first = entries.reduce((m, e) => (e.date < m ? e.date : m), '9999');
      const last = entries.reduce((m, e) => (e.date > m ? e.date : m), '0000');
      let [y, m] = first.split('-').map(Number);
      const [ly, lm] = last.split('-').map(Number);
      while (y < ly || (y === ly && m <= lm)) {
        months.push(`${y}-${String(m).padStart(2, '0')}`);
        m += 1;
        if (m > 12) {
          m = 1;
          y += 1;
        }
      }
    }
    const span = `${MONTH.format(asDate(`${months[0]}-01`))} → ${MONTH.format(asDate(`${months[months.length - 1]}-01`))}`;
    main.insertAdjacentHTML(
      'beforeend',
      hero('Documentation vivante · historique des décisions', `L'histoire de <span class="grad-text">LIA</span>, décision après décision`, H.lede, [
        stat(String(entries.length), 'décisions d’architecture'),
        stat(String(H.themes.length), 'thèmes'),
        stat(String(D.facts.releases), 'versions publiées'),
        stat(String(H.eras.length), 'chapitres'),
        stat(`${months.length} mois`, span),
      ])
    );
    main.insertAdjacentHTML(
      'beforeend',
      `<section class="section" aria-labelledby="chart-title"><div class="section-head"><div><p class="kicker">Vue d'ensemble</p><h2 id="chart-title">Décisions par mois et par thème</h2>
      <p>Chaque barre empile les décisions d'un mois, colorées par thème. Clique une barre pour y aller.</p></div></div>
      <div class="card chart-card"><div class="scroll-x" id="chart"></div></div></section>
      <section class="section" aria-labelledby="tl-title"><div class="section-head"><div><p class="kicker">Chronologie</p><h2 id="tl-title">Toutes les décisions</h2>
      <p>Chaque décision en quelques phrases, avec les briques qu'elle a façonnées. Filtre par thème, cherche un mot, ou suis une brique.</p></div></div>
      <div class="filters">
        <div class="filter-row" id="themes"></div>
        <div class="filter-row">
          <label class="search" style="max-width:420px">${icon('search', 16)}<span class="sr">Chercher une décision</span><input id="q" type="search" placeholder="Chercher : mot, numéro d'ADR…" autocomplete="off"></label>
          <label class="toggle"><input type="checkbox" id="rel" checked> Afficher les versions</label>
          <label class="toggle"><input type="checkbox" id="desc"> Plus récentes d'abord</label>
          <button type="button" class="btn" id="reset">${icon('rotate-ccw', 15)}Réinitialiser</button>
          <span class="result-count" id="count" aria-live="polite"></span>
        </div>
        <div id="brickfilter"></div>
      </div>
      <div class="timeline" id="timeline"></div></section>`
    );

    const state = { themes: new Set(), q: '', brick: null, releases: true, desc: false };

    // --- chart
    const counts = months.map((m) => {
      const c = new Map();
      for (const e of entries) if (e.date.startsWith(m)) c.set(e.theme, (c.get(e.theme) || 0) + 1);
      return c;
    });
    const totals = counts.map((c) => [...c.values()].reduce((s, v) => s + v, 0));
    const maxTotal = Math.max(...totals);
    const stepTick = [5, 10, 20, 25, 50, 100].find((s) => maxTotal / s <= 5) || 100;
    const top = Math.ceil(maxTotal / stepTick) * stepTick;
    const W = 1100;
    const Hh = 320;
    const m = { l: 44, r: 12, t: 22, b: 46 };
    const plotW = W - m.l - m.r;
    const plotH = Hh - m.t - m.b;
    const slot = plotW / months.length;
    const bw = Math.min(56, slot * 0.64);
    const y = (v) => m.t + plotH - (v / top) * plotH;
    let bars = '';
    months.forEach((mo, i) => {
      let acc = 0;
      const x = m.l + i * slot + (slot - bw) / 2;
      for (const t of H.themes) {
        const v = counts[i].get(t.id) || 0;
        if (!v) continue;
        const y0 = y(acc);
        const y1 = y(acc + v);
        bars += `<rect class="bar" data-month="${mo}" data-theme="${t.id}" data-tone="${t.tone}" x="${round(x)}" y="${round(y1)}" width="${round(bw)}" height="${round(Math.max(0.8, y0 - y1 - 1))}" rx="2" fill="var(--tone)"/>`;
        acc += v;
      }
      if (totals[i]) bars += `<text class="total" x="${round(x + bw / 2)}" y="${round(y(totals[i]) - 7)}">${totals[i]}</text>`;
    });
    let ticks = '';
    for (let v = 0; v <= top; v += stepTick) {
      ticks += `<line x1="${m.l}" x2="${W - m.r}" y1="${round(y(v))}" y2="${round(y(v))}"/><text x="${m.l - 8}" y="${round(y(v) + 4)}" text-anchor="end">${v}</text>`;
    }
    const xlabels = months
      .map((mo, i) => {
        const d = asDate(`${mo}-01`);
        const label = `${MONTH_SHORT.format(d).replace('.', '')} ${String(d.getUTCFullYear()).slice(2)}`;
        return `<text x="${round(m.l + i * slot + slot / 2)}" y="${Hh - m.b + 22}" text-anchor="middle">${esc(label)}</text>`;
      })
      .join('');
    const chartEl = document.getElementById('chart');
    chartEl.innerHTML = `<svg class="chart" id="chartsvg" viewBox="0 0 ${W} ${Hh}" role="img" aria-label="${esc(`Décisions par mois, de ${span}`)}"><g class="axis">${ticks}${xlabels}</g><g>${bars}</g></svg>`;
    const chartSvg = document.getElementById('chartsvg');
    chartSvg.querySelectorAll('.bar').forEach((r) => {
      r.addEventListener('mousemove', (ev) => {
        const i = months.indexOf(r.dataset.month);
        const lines = H.themes
          .filter((t) => counts[i].get(t.id))
          .map((t) => `${esc(t.name)} : ${counts[i].get(t.id)}`)
          .join('<br>');
        showTip(`<b>${esc(MONTH.format(asDate(`${r.dataset.month}-01`)))} · ${totals[i]}</b>${lines}`, ev.clientX, ev.clientY);
      });
      r.addEventListener('mouseleave', hideTip);
      r.addEventListener('click', () => {
        const target = document.getElementById(`m-${r.dataset.month}`);
        if (target) target.scrollIntoView({ behavior: REDUCED ? 'auto' : 'smooth', block: 'start' });
      });
    });

    // --- theme filters
    const themesEl = document.getElementById('themes');
    themesEl.innerHTML = H.themes
      .map((t) => {
        const n = entries.filter((e) => e.theme === t.id).length;
        return `<button type="button" class="theme-chip" data-theme="${t.id}" data-tone="${t.tone}" aria-pressed="false" title="${esc(t.summary)}">${icon(t.icon, 15)}${esc(t.name)}<span class="n">${n}</span></button>`;
      })
      .join('');
    themesEl.querySelectorAll('.theme-chip').forEach((b) => {
      b.addEventListener('click', () => {
        const id = b.dataset.theme;
        if (state.themes.has(id)) state.themes.delete(id);
        else state.themes.add(id);
        b.setAttribute('aria-pressed', String(state.themes.has(id)));
        render();
      });
    });

    const qEl = document.getElementById('q');
    qEl.addEventListener('input', () => {
      state.q = qEl.value.trim();
      render();
    });
    document.getElementById('rel').addEventListener('change', (ev) => {
      state.releases = ev.target.checked;
      render();
    });
    document.getElementById('desc').addEventListener('change', (ev) => {
      state.desc = ev.target.checked;
      render();
    });
    document.getElementById('reset').addEventListener('click', () => {
      resetFilters();
      render();
    });
    function resetFilters() {
      state.themes.clear();
      state.q = '';
      state.brick = null;
      qEl.value = '';
      themesEl.querySelectorAll('.theme-chip').forEach((b) => b.setAttribute('aria-pressed', 'false'));
      history.replaceState(null, '', location.pathname + location.search);
    }

    function eraOf(date) {
      return H.eras.find((er) => date >= er.from && (!er.to || date <= er.to));
    }
    function match(e) {
      if (state.themes.size && !state.themes.has(e.theme)) return false;
      if (state.brick && !e.functional.includes(state.brick) && !e.technical.includes(state.brick)) return false;
      if (state.q) {
        const n = norm(state.q);
        const num = n.replace(/^adr-?0*/, '');
        const hay = norm(`${e.title} ${e.summary} ${themeById.get(e.theme).name} adr-${String(e.adr).padStart(3, '0')}`);
        if (!hay.includes(n) && String(e.adr) !== num) return false;
      }
      return true;
    }

    const timeline = document.getElementById('timeline');
    function card(e) {
      const t = themeById.get(e.theme);
      const no = String(e.adr).padStart(3, '0');
      const chips = [...e.functional, ...e.technical].map((id) => brickChip(id)).join('');
      return `<li><span class="pin" data-tone="${t.tone}" aria-hidden="true">${icon(t.icon, 15)}</span>
        <article class="adr-card" id="adr-${e.adr}" data-tone="${t.tone}">
          <header><span class="no">ADR-${no}</span><time datetime="${e.date}">${esc(fmtDay(e.date))}</time><span class="chip theme plain" data-tone="${t.tone}">${icon(t.icon, 13)}${esc(t.name)}</span></header>
          <h4>${esc(e.title)}</h4>
          <p>${esc(e.summary)}</p>
          <div class="foot-row">${chips}<a class="read" href="${esc(adrUrl(e.adr))}" target="_blank" rel="noopener">${e.nofile ? 'Dans l’index des ADR' : 'Lire la décision'}${icon('arrow-up-right', 14)}</a></div>
        </article></li>`;
    }
    function releaseItem(r) {
      const anchor = `${r.version.replace(/\./g, '')}---${r.date}`;
      return `<li class="rel"><span class="release-pin" aria-hidden="true"></span><a class="release" href="${esc(`${D.repo}CHANGELOG.md#${anchor}`)}" target="_blank" rel="noopener">${icon('tag', 14)}Version ${esc(r.version)} · ${esc(fmtDayShort(r.date))}</a></li>`;
    }

    function render() {
      const list = entries.filter(match).sort((a, b) => (a.date === b.date ? a.adr - b.adr : a.date < b.date ? -1 : 1));
      if (state.desc) list.reverse();
      chartSvg.classList.toggle('is-filtered', state.themes.size > 0);
      chartSvg.querySelectorAll('.bar').forEach((r) => r.classList.toggle('off', state.themes.size > 0 && !state.themes.has(r.dataset.theme)));
      document.getElementById('count').textContent = plural(list.length, 'décision affichée', 'décisions affichées');
      const bf = document.getElementById('brickfilter');
      if (state.brick) {
        bf.innerHTML = `<div class="filter-row"><span class="hint">${icon('filter', 14)}Décisions qui ont façonné</span>${brickChip(state.brick)}<button type="button" class="linkish" id="clearbrick">${icon('x', 14)}Retirer ce filtre</button></div>`;
        document.getElementById('clearbrick').addEventListener('click', () => {
          state.brick = null;
          history.replaceState(null, '', location.pathname + location.search);
          render();
        });
      } else bf.innerHTML = '';
      if (!list.length) {
        timeline.innerHTML = `<div class="no-results"><p>Aucune décision ne correspond à ces filtres.</p><p style="margin-top:10px"><button type="button" class="btn" id="reset2">${icon('rotate-ccw', 15)}Réinitialiser les filtres</button></p></div>`;
        document.getElementById('reset2').addEventListener('click', () => {
          resetFilters();
          render();
        });
        return;
      }
      const filtered = state.themes.size || state.q || state.brick;
      const first = list[0].date;
      const last = list[list.length - 1].date;
      const lo = first < last ? first : last;
      const hi = first < last ? last : first;
      const rels = state.releases && !filtered ? D.facts.milestones.filter((r) => r.date >= lo && r.date <= hi) : [];
      const items = [...list.map((e) => ({ kind: 'adr', date: e.date, e })), ...rels.map((r) => ({ kind: 'rel', date: r.date, r }))];
      items.sort((a, b) => {
        if (a.date !== b.date) return (a.date < b.date ? -1 : 1) * (state.desc ? -1 : 1);
        if (a.kind !== b.kind) return (a.kind === 'rel' ? 1 : -1) * (state.desc ? -1 : 1);
        return (a.kind === 'adr' ? a.e.adr - b.e.adr : 0) * (state.desc ? -1 : 1);
      });
      let html = '';
      let era = null;
      let month = null;
      let open = false;
      for (const it of items) {
        const er = eraOf(it.date);
        if (er !== era) {
          if (open) html += '</ol></div>';
          open = false;
          era = er;
          month = null;
          const inEra = list.filter((e) => eraOf(e.date) === er);
          const themeCounts = new Map();
          inEra.forEach((e) => themeCounts.set(e.theme, (themeCounts.get(e.theme) || 0) + 1));
          const topThemes = [...themeCounts.entries()].sort((a, b) => b[1] - a[1]).slice(0, 4);
          const idx = H.eras.indexOf(er) + 1;
          const range = `${fmtDayShort(er.from)} – ${er.to ? fmtDayShort(er.to) : 'aujourd’hui'}`;
          html += `<section class="era" aria-label="${esc(er.name)}"><p class="kicker">Chapitre ${idx} · ${esc(range)} · ${plural(inEra.length, 'décision', 'décisions')}</p><h2>${esc(er.name)}</h2><p>${esc(er.summary)}</p>
            <div class="chips">${topThemes
              .map(([id, n]) => {
                const t = themeById.get(id);
                return `<span class="chip plain theme" data-tone="${t.tone}">${icon(t.icon, 13)}${esc(t.name)} · ${n}</span>`;
              })
              .join('')}</div></section>`;
        }
        const mo = it.date.slice(0, 7);
        if (mo !== month) {
          if (open) html += '</ol></div>';
          month = mo;
          const n = list.filter((e) => e.date.startsWith(mo)).length;
          html += `<div class="mblock"><div class="month" id="m-${mo}"><h3>${esc(MONTH.format(asDate(`${mo}-01`)))}</h3><span>${plural(n, 'décision', 'décisions')}</span></div><ol class="tl split">`;
          open = true;
        }
        html += it.kind === 'adr' ? card(it.e) : releaseItem(it.r);
      }
      if (open) html += '</ol></div>';
      timeline.innerHTML = html;
    }

    wireLocalChips(timeline, () => {});
    function applyHash() {
      const hash = decodeURIComponent(location.hash.slice(1));
      const adr = /^adr-(\d+)$/.exec(hash);
      if (adr) {
        const n = Number(adr[1]);
        const e = entries.find((x) => x.adr === n);
        if (e && !match(e)) resetFilters();
        render();
        const el = document.getElementById(`adr-${n}`);
        if (el) {
          el.classList.add('is-target');
          el.scrollIntoView({ block: 'center' });
        }
        return;
      }
      if (fById.has(hash) || tById.has(hash)) {
        state.brick = hash;
        render();
        return;
      }
      render();
    }
    window.addEventListener('hashchange', applyHash);
    applyHash();
  }

  // ---------------------------------------------------------------- boot
  renderNav();
  initTheme();
  if (PAGE === 'functional') functionalPage();
  else if (PAGE === 'technical') technicalPage();
  else historyPage();
})();
