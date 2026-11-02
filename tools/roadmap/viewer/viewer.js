(() => {
'use strict';
const D = JSON.parse(document.getElementById('data').textContent);
const issues = new Map(D.issues.map(i => [i.id, i]));
const epics = new Map(D.epics.map(e => [e.id, e]));
const msById = new Map(D.milestones.map(m => [m.id, m]));
const stageById = new Map(D.stages.map(s => [s.id, s]));
const NS = 'http://www.w3.org/2000/svg';
const THEMES = ['platform','assess','verify','agents','trust','integrations','ops','packs','layers','scale','rollout','meta'];

// ---------------------------------------------------------------- helpers
function el(ns, tag, props, kids) {
  const n = ns ? document.createElementNS(NS, tag) : document.createElement(tag);
  for (const [k, v] of Object.entries(props || {})) {
    if (v == null || v === false) continue;
    if (k === 'text') n.textContent = v;
    else if (k === 'html') n.innerHTML = v;
    else if (k.startsWith('on')) n.addEventListener(k.slice(2), v);
    else n.setAttribute(k, v === true ? '' : v);
  }
  for (const c of kids.flat(2)) if (c != null && c !== false) n.append(c.nodeType ? c : document.createTextNode(String(c)));
  return n;
}
const h = (t, p, ...k) => el(false, t, p, k);
const put = (parent, ...kids) => { parent.append(...kids.flat(2).filter(c => c != null && c !== false)); return parent; };
const sv = (t, p, ...k) => el(true, t, p, k);
const trunc = (s, n) => (s.length > n ? s.slice(0, n - 1) + '…' : s);
const epicOf = id => epics.get(id.length > 3 ? id.slice(0, 3) : id);
const themeOf = id => (epicOf(id) || {}).theme || 'meta';
const tc = theme => `--tc: var(--c-${theme})`;
const points = list => list.reduce((a, i) => a + D.sizeWeight[i.size], 0);
const remaining = list => list.reduce((a, i) => a + (i.status === 'done' ? 0 : D.sizeWeight[i.size]), 0);
const pct = (a, b) => (b ? Math.round((100 * a) / b) : 0);
const msName = id => (msById.get(id) || {}).name || id;
const safe = fn => { try { return fn(); } catch (e) { return null; } };

const state = { drawer: null, route: '/overview', graph: { scope: 'epics', ms: new Set(), q: '', crit: false, hideDone: false }, viewApi: null };

// ---------------------------------------------------------------- routing
// Only a plain "#view" name is written to the URL; everything else (scope,
// filters, selected doc, open item) lives in memory, so links stay valid when
// the page is embedded.
function parseRoute(str) {
  const raw = str.replace(/^#?\/?/, '');
  const [path, qs = ''] = raw.split('?');
  return { seg: path.split('/').filter(Boolean).map(decodeURIComponent), q: new URLSearchParams(qs) };
}
const parseHash = () => parseRoute(state.route);

function setUrl(view) { try { history.replaceState(null, '', `#${view}`); } catch (e) { /* embedded frames may refuse */ } }

function go(route) {
  const { seg } = parseRoute(route);
  if ((seg[0] === 'issue' || seg[0] === 'epic') && seg[1]) {
    state.drawer = { kind: seg[0], id: seg[1] };
    if (!document.getElementById('app').childElementCount) renderView();
    renderDrawer();
    if (state.viewApi && state.viewApi.select) state.viewApi.select(seg[1]);
    return;
  }
  state.route = route.startsWith('/') ? route : `/${route}`;
  setUrl(VIEWS.some(v => v[0] === seg[0]) ? seg[0] : 'overview');
  renderView();
}

function routeFromLocation() {
  const raw = location.hash.replace(/^#\/?/, '').split('?')[0].split('/')[0];
  return VIEWS.some(v => v[0] === raw) ? `/${raw}` : '/overview';
}

const VIEWS = [['overview', 'Overview'], ['roadmap', 'Roadmap'], ['graph', 'Dependency graph'], ['ladder', 'Adoption ladder'], ['docs', 'Docs']];

function renderTabs(active) {
  const nav = document.getElementById('tabs');
  nav.replaceChildren(...VIEWS.map(([id, label]) => h('a', { href: `#/${id}`, 'aria-current': id === active ? 'page' : null, text: label })));
}

function renderView() {
  const { seg, q } = parseHash();
  const view = VIEWS.some(v => v[0] === seg[0]) ? seg[0] : 'overview';
  renderTabs(view);
  const app = document.getElementById('app');
  state.viewApi = null;
  app.replaceChildren();
  app.scrollTop = 0;
  document.title = `${VIEWS.find(v => v[0] === view)[1]} · Val Roadmap`;
  ({ overview: viewOverview, roadmap: viewRoadmap, graph: viewGraph, ladder: viewLadder, docs: viewDocs })[view](app, seg, q);
  if (state.drawer) renderDrawer();
}

// ---------------------------------------------------------------- shared bits
function statusDot(st) { return h('span', { class: `dot ${st}`, title: st }); }
function msChip(id) { return h('span', { class: 'chip ms', title: msName(id), text: id }); }
function themeChip(epicId) {
  const e = epics.get(epicId);
  return h('span', { class: 'chip theme', style: tc(e.theme), text: `${e.id} ${trunc(e.title, 26)}` });
}
function issueRow(i, extra) {
  return h('div', { class: 'row', role: 'link', tabindex: '0', onclick: () => open('issue', i.id), onkeydown: e => { if (e.key === 'Enter') open('issue', i.id); } },
    statusDot(i.status), h('span', { class: 'id', text: i.id }),
    h('span', { class: 't' }, i.title, extra ? h('small', { text: extra }) : null),
    msChip(i.milestone), h('span', { class: 'chip', text: i.size }));
}
function open(kind, id) { go(`/${kind}/${id}`); }

// ---------------------------------------------------------------- overview
function viewOverview(app) {
  const all = D.issues;
  const total = points(all), left = remaining(all);
  const s3 = stageById.get('S3');
  const crit = (s3 && s3.critical.length ? s3.critical : D.critical).map(id => issues.get(id));
  const stats = [
    [D.epics.length, 'epics'], [all.length, 'issues'], [D.milestones.length - 1, 'milestones + layer track'],
    [D.stages.length, 'adoption stages'], [`${pct(total - left, total)}%`, `of ${total} effort points done`],
    [points(crit.filter(i => i.status !== 'done')), 'points on the critical chain to S3'],
  ];
  app.append(h('div', { class: 'page' },
    h('h1', { text: 'Val: roadmap and rollout' }),
    h('p', { class: 'lede', text: 'Val verifies tests before it writes them. This roadmap is a dependency graph: build the deterministic verifier first, adopt it repo by repo, then add agents behind it.' }),
    h('div', { class: 'grid stats' }, stats.map(([n, l]) => h('div', { class: 'card stat' }, h('b', { text: String(n) }), h('span', { text: l })))),
    h('div', { class: 'grid cols2' },
      h('section', {}, h('h2', { text: 'Ready to start' }),
        h('p', { class: 'muted', text: 'Every dependency is done. Ordered by milestone, then by how much work it unblocks.' }),
        h('div', { class: 'card' }, D.ready.slice(0, 12).map(id => issueRow(issues.get(id))))),
      h('section', {}, h('h2', { text: 'Critical chain to first agent PRs (S3)' }),
        h('p', { class: 'muted', text: 'Longest sequential chain of remaining work. A lower bound on effort; real time is dominated by pilot soak and review capacity.' }),
        h('div', { class: 'card' }, crit.filter(i => i.status !== 'done').map(i => issueRow(i))))),
    h('h2', { text: 'Milestones' }),
    h('div', { class: 'card' }, D.milestoneOrder.map(mid => {
      const m = msById.get(mid), mine = all.filter(i => i.milestone === mid), t = points(mine);
      const st = D.stages.find(s => s.requires[s.requires.length - 1] === mid);
      return h('div', { class: 'row', onclick: () => go(`/graph?scope=issues&ms=${mid}`) },
        h('span', { class: 'id', text: mid }), h('span', { class: 't' }, m.name, h('small', { text: m.goal })),
        st ? h('span', { class: 'chip', text: `unlocks ${st.id} ${st.name}` }) : h('span', { class: 'chip', text: 'optional track' }),
        h('span', { class: 'chip', text: `${mine.length} issues · ${t} pts` }));
    })),
    h('p', { class: 'muted', text: `Effort points are relative (S=1, M=2, L=4), not calendar time. Generated ${D.generated}.` })));
}

// ---------------------------------------------------------------- roadmap board
function viewRoadmap(app) {
  const board = h('div', { class: 'board' });
  for (const mid of D.milestoneOrder) {
    const m = msById.get(mid), mine = D.issues.filter(i => i.milestone === mid);
    const st = D.stages.find(s => s.requires[s.requires.length - 1] === mid);
    const byEpic = new Map();
    mine.forEach(i => byEpic.set(i.epic, [...(byEpic.get(i.epic) || []), i]));
    board.append(h('section', { class: 'col' },
      h('h3', {}, h('span', { text: `${mid} · ${m.name}` }), h('span', { class: 'muted', text: `${mine.length}` })),
      h('p', { class: 'goal', text: m.goal }),
      st ? h('p', { class: 'goal' }, h('span', { class: 'chip', text: `unlocks ${st.id} ${st.name}` })) : null,
      [...byEpic.entries()].map(([eid, list]) => {
        const e = epics.get(eid), done = list.filter(i => i.status === 'done').length;
        return h('div', { class: 'epic-card', style: tc(e.theme), role: 'link', tabindex: '0',
          onclick: () => open('epic', eid), onkeydown: ev => { if (ev.key === 'Enter') open('epic', eid); } },
          h('b', { text: `${eid} ${e.title}` }),
          h('small', { text: `${list.length} issue${list.length > 1 ? 's' : ''} · ${points(list)} pts${done ? ` · ${done} done` : ''}` }),
          h('div', { class: 'bar' }, h('i', { style: `width:${pct(done, list.length)}%` })));
      })));
  }
  app.append(board);
}

// ---------------------------------------------------------------- ladder
function viewLadder(app) {
  const page = h('div', { class: 'page' },
    h('h1', { text: 'Adoption ladder' }),
    h('p', { class: 'lede', text: 'Each repo climbs one rung at a time. A rung is available once its milestones are built, and a repo only moves up after meeting the exit criteria. The first two rungs use no LLM at all.' }));
  const ladder = h('div', { class: 'ladder' });
  D.stages.forEach((s, n) => {
    const done = s.effort - s.remaining;
    const packs = s.requires.includes('M4') ? 'Layer packs (smoke, integration, performance, E2E, data, delivery, resilience, security) can be adopted per repo from here.' : null;
    ladder.append(h('article', { class: 'card stage', 'data-n': String(n) },
      h('h3', { text: `${s.id} · ${s.name}` }),
      h('p', { text: s.summary }),
      h('p', { class: 'kv' }, h('b', { text: 'Risk: ' }), s.risk),
      h('div', { class: 'two' },
        h('div', {}, h('b', { text: 'You get' }), h('ul', {}, s.you_get.map(x => h('li', { text: x })))),
        h('div', {}, h('b', { text: 'Entry' }), h('ul', {}, s.entry.map(x => h('li', { text: x }))), h('b', { text: 'Exit' }), h('ul', {}, s.exit.map(x => h('li', { text: x }))))),
      h('p', { class: 'kv' }, h('b', { text: 'Rollback: ' }), s.rollback, ' ', h('b', { text: 'Approver: ' }), s.approver),
      packs ? h('p', { class: 'kv', text: packs }) : null,
      h('p', { class: 'kv' }, h('b', { text: 'To build this rung: ' }), `${s.issue_ids.length} issues · ${s.effort} points (${s.remaining} remaining) · milestones ${s.requires.join(', ')}`),
      h('div', { class: 'bar' }, h('i', { style: `width:${pct(done, s.effort)}%` })),
      h('p', {}, h('a', { class: 'btn', href: `#/graph?scope=stage:${s.id}&crit=1`, text: 'Show what must be built' }))));
  });
  page.append(ladder);
  app.append(page);
}

// ---------------------------------------------------------------- docs
function viewDocs(app, seg) {
  const id = seg.slice(1).join('/') || D.docs[0].id;
  const doc = D.docs.find(d => d.id === id) || D.docs[0];
  const groups = [['overview', 'Start'], ['plan', 'Plans'], ['design', 'Design'], ['spec', 'Source']];
  const nav = h('nav', { class: 'docnav', 'aria-label': 'Documents' });
  const known = new Set();
  for (const [g, label] of groups) {
    const list = D.docs.filter(d => d.group === g);
    if (!list.length) continue;
    nav.append(h('h4', { text: label }));
    list.forEach(d => { known.add(d.id); nav.append(h('a', { href: `#/docs/${d.id}`, 'aria-current': d.id === doc.id ? 'page' : null, text: d.title.replace(/^Val\s*[:—-]\s*/, '') })); });
  }
  D.docs.filter(d => !known.has(d.id)).forEach(d => nav.append(h('a', { href: `#/docs/${d.id}`, 'aria-current': d.id === doc.id ? 'page' : null, text: d.title })));
  const body = h('article', { class: 'doc', html: doc.html });
  body.addEventListener('click', e => {
    const a = e.target.closest('a[href^="#"]');
    if (!a || a.getAttribute('href').startsWith('#/')) return;
    e.preventDefault();
    const t = document.getElementById(a.getAttribute('href').slice(1));
    if (t) t.scrollIntoView();
  });
  app.append(h('div', { class: 'docs' }, nav, body));
  document.title = `${doc.title} · Val Roadmap`;
}

// ---------------------------------------------------------------- graph model
function graphParams(q) {
  const g = state.graph;
  g.scope = q.get('scope') || 'epics';
  g.ms = new Set((q.get('ms') || '').split(',').filter(Boolean));
  g.q = q.get('q') || '';
  g.crit = q.get('crit') === '1';
  g.hideDone = q.get('done') === '0';
  return g;
}
function graphHash(g) {
  const p = new URLSearchParams();
  p.set('scope', g.scope);
  if (g.ms.size) p.set('ms', [...g.ms].join(','));
  if (g.q) p.set('q', g.q);
  if (g.crit) p.set('crit', '1');
  if (g.hideDone) p.set('done', '0');
  return `#/graph?${p}`;
}

function buildModel(g) {
  const nodes = [], edges = [];
  if (g.scope === 'epics') {
    D.epics.forEach(e => {
      const mine = D.issues.filter(i => i.epic === e.id);
      nodes.push({ id: e.id, kind: 'epic', theme: e.theme, title: e.title, sub: `${mine.length} issues · ${e.milestones.join(' ')}`,
        done: mine.every(i => i.status === 'done'), w: 226, h: 58, layer: D.milestoneOrder.indexOf(e.milestones[0]),
        text: `${e.id} ${e.title}`.toLowerCase() });
    });
    const cnt = new Map();
    D.issues.forEach(i => i.deps.forEach(d => { const a = issues.get(d).epic; if (a !== i.epic) cnt.set(`${a}>${i.epic}`, (cnt.get(`${a}>${i.epic}`) || 0) + 1); }));
    cnt.forEach((n, k) => { const [a, b] = k.split('>'); edges.push({ a, b, n }); });
    return { nodes, edges, crit: new Set() };
  }
  let set, ghost = new Set(), crit = new Set(D.critical);
  if (g.scope === 'issues') set = new Set(D.issues.map(i => i.id));
  else if (g.scope.startsWith('epic:')) {
    const eid = g.scope.slice(5);
    set = new Set(D.issues.filter(i => i.epic === eid).map(i => i.id));
    set.forEach(id => { const i = issues.get(id); [...i.deps, ...i.dependents].forEach(n => { if (!set.has(n)) ghost.add(n); }); });
  } else if (g.scope.startsWith('stage:')) {
    const st = stageById.get(g.scope.slice(6));
    set = new Set(st ? st.issue_ids : []);
    crit = new Set(st ? st.critical : []);
  } else set = new Set();
  const visible = id => {
    const i = issues.get(id);
    if (g.hideDone && i.status === 'done') return false;
    return ghost.has(id) || !g.ms.size || g.ms.has(i.milestone);
  };
  const ids = [...set, ...ghost].filter(visible);
  const idset = new Set(ids);
  const q = g.q.trim().toLowerCase();
  ids.forEach(id => {
    const i = issues.get(id);
    nodes.push({ id, kind: 'issue', theme: themeOf(id), title: i.title, sub: '', done: i.status === 'done', ghost: ghost.has(id),
      crit: g.crit && crit.has(id), w: 214, h: 44, hit: !q || `${id} ${i.title}`.toLowerCase().includes(q) });
  });
  ids.forEach(id => issues.get(id).deps.forEach(d => { if (idset.has(d) && !(ghost.has(d) && ghost.has(id))) edges.push({ a: d, b: id, crit: g.crit && crit.has(d) && crit.has(id) }); }));
  return { nodes, edges, crit };
}

function layout(nodes, edges, gx, gy) {
  const out = new Map(nodes.map(n => [n.id, []])), inn = new Map(nodes.map(n => [n.id, []]));
  edges.forEach(e => { out.get(e.a).push(e.b); inn.get(e.b).push(e.a); });
  const indeg = new Map(nodes.map(n => [n.id, inn.get(n.id).length]));
  const layer = new Map();
  const fixed = nodes.every(n => n.layer != null);
  const queue = fixed ? [] : nodes.filter(n => indeg.get(n.id) === 0).map(n => n.id);
  if (fixed) nodes.forEach(n => layer.set(n.id, n.layer)); else queue.forEach(id => layer.set(id, 0));
  while (queue.length) {
    const id = queue.shift();
    for (const m of out.get(id)) {
      layer.set(m, Math.max(layer.get(m) || 0, layer.get(id) + 1));
      indeg.set(m, indeg.get(m) - 1);
      if (indeg.get(m) === 0) queue.push(m);
    }
  }
  const L = [];
  nodes.forEach(n => { const l = layer.get(n.id) || 0; (L[l] = L[l] || []).push(n.id); });
  for (let i = 0; i < L.length; i++) L[i] = L[i] || [];
  L.forEach(l => l.sort());
  const pos = new Map();
  const reindex = () => L.forEach(l => l.forEach((id, i) => pos.set(id, i)));
  reindex();
  for (let it = 0; it < 8; it++) {
    const down = it % 2 === 0;
    const idxs = L.map((_, i) => i);
    const order = down ? idxs.slice(1) : idxs.slice(0, -1).reverse();
    for (const li of order) {
      const nb = down ? inn : out;
      const bc = new Map(L[li].map(id => { const ns = nb.get(id); return [id, ns.length ? ns.reduce((a, n) => a + pos.get(n), 0) / ns.length : pos.get(id)]; }));
      L[li].sort((a, b) => bc.get(a) - bc.get(b) || (a < b ? -1 : 1));
      L[li].forEach((id, i) => pos.set(id, i));
    }
  }
  const maxN = Math.max(1, ...L.map(l => l.length));
  const nw = Math.max(...nodes.map(n => n.w), 0), nh = Math.max(...nodes.map(n => n.h), 0);
  const at = new Map();
  L.forEach((l, li) => l.forEach((id, i) => at.set(id, { x: li * (nw + gx), y: (i + (maxN - l.length) / 2) * (nh + gy) })));
  return { at, width: L.length * (nw + gx) - gx, height: maxN * (nh + gy) - gy };
}

// ---------------------------------------------------------------- graph view
function viewGraph(app, _seg, q) {
  const g = graphParams(q);
  const wrap = h('div', { class: 'graphwrap' });
  const canvas = h('div', { class: 'canvas' });
  const svg = sv('svg', { role: 'img', 'aria-label': 'Dependency graph' });
  const vp = sv('g', {});
  svg.append(vp);
  canvas.append(svg);

  // toolbar
  const scopeSel = h('select', { 'aria-label': 'Scope' });
  const scopes = [['epics', 'Epics overview'], ['issues', 'All issues']];
  D.epics.forEach(e => scopes.push([`epic:${e.id}`, `Epic ${e.id} · ${e.title}`]));
  D.stages.forEach(s => scopes.push([`stage:${s.id}`, `Path to ${s.id} ${s.name}`]));
  scopes.forEach(([v, l]) => scopeSel.append(h('option', { value: v, text: l, selected: v === g.scope })));
  const search = h('input', { type: 'search', placeholder: 'Find id or title', 'aria-label': 'Find', value: g.q });
  const msChips = h('span', { class: 'chips', role: 'group', 'aria-label': 'Filter by milestone' });
  const critBtn = h('button', { class: 'toggle', type: 'button', 'aria-pressed': String(g.crit), text: 'Critical chain' });
  const doneBtn = h('button', { class: 'toggle', type: 'button', 'aria-pressed': String(g.hideDone), text: 'Hide done' });
  const note = h('span', { class: 'muted', id: 'gcount' });
  const sync = () => { state.route = graphHash(g).slice(1); setUrl('graph'); };
  const redraw = fit => { sync(); refreshToolbar(); draw(fit); };
  const refreshToolbar = () => {
    msChips.replaceChildren(...D.milestoneOrder.map(m => h('button', { class: 'toggle', type: 'button', title: msName(m),
      'aria-pressed': String(g.ms.has(m)), text: m, onclick: () => { g.ms.has(m) ? g.ms.delete(m) : g.ms.add(m); redraw(true); } })));
    critBtn.setAttribute('aria-pressed', String(g.crit));
    doneBtn.setAttribute('aria-pressed', String(g.hideDone));
  };
  scopeSel.addEventListener('change', () => { g.scope = scopeSel.value; redraw(true); });
  let timer = 0;
  search.addEventListener('input', () => { clearTimeout(timer); timer = setTimeout(() => { g.q = search.value; redraw(false); }, 150); });
  critBtn.addEventListener('click', () => { g.crit = !g.crit; redraw(false); });
  doneBtn.addEventListener('click', () => { g.hideDone = !g.hideDone; redraw(true); });
  const toolbar = h('div', { class: 'toolbar' }, h('label', {}, 'Scope', scopeSel), search, msChips, critBtn, doneBtn, note);

  // zoom controls
  let tx = 0, ty = 0, k = 1;
  const apply = () => vp.setAttribute('transform', `translate(${tx} ${ty}) scale(${k})`);
  const zoomAt = (cx, cy, f) => { const nk = Math.min(3, Math.max(0.04, k * f)); tx = cx - ((cx - tx) / k) * nk; ty = cy - ((cy - ty) / k) * nk; k = nk; apply(); };
  const center = () => { const r = canvas.getBoundingClientRect(); return [r.width / 2, r.height / 2]; };
  const zoom = h('div', { class: 'zoom' },
    h('button', { class: 'btn', type: 'button', 'aria-label': 'Zoom in', text: '+', onclick: () => zoomAt(...center(), 1.25) }),
    h('button', { class: 'btn', type: 'button', 'aria-label': 'Zoom out', text: '−', onclick: () => zoomAt(...center(), 0.8) }),
    h('button', { class: 'btn', type: 'button', 'aria-label': 'Fit to screen', text: 'Fit', onclick: () => fit() }));
  const legend = h('div', { class: 'legend' });
  canvas.append(zoom, legend);

  let dims = { width: 0, height: 0 };
  const fit = () => {
    const r = canvas.getBoundingClientRect();
    if (!r.width || !dims.width) return;
    k = Math.min(1.1, Math.max(0.04, Math.min((r.width - 40) / dims.width, (r.height - 40) / dims.height)));
    tx = (r.width - dims.width * k) / 2; ty = Math.max(20, (r.height - dims.height * k) / 2); apply();
  };

  // pan + wheel
  let pan = null;
  canvas.addEventListener('pointerdown', e => {
    if (e.target.closest('.node, .zoom, .legend')) return;
    pan = { x: e.clientX, y: e.clientY, tx, ty }; canvas.classList.add('panning'); canvas.setPointerCapture(e.pointerId);
  });
  canvas.addEventListener('pointermove', e => { if (pan) { tx = pan.tx + e.clientX - pan.x; ty = pan.ty + e.clientY - pan.y; apply(); } });
  const endPan = () => { pan = null; canvas.classList.remove('panning'); };
  canvas.addEventListener('pointerup', endPan); canvas.addEventListener('pointercancel', endPan);
  canvas.addEventListener('wheel', e => {
    e.preventDefault();
    const r = canvas.getBoundingClientRect();
    zoomAt(e.clientX - r.left, e.clientY - r.top, e.deltaY < 0 ? 1.12 : 1 / 1.12);
  }, { passive: false });

  const nodeEls = new Map();
  let model = null;

  function draw(doFit) {
    model = buildModel(g);
    vp.replaceChildren(); nodeEls.clear();
    const { nodes, edges } = model;
    const isEpics = g.scope === 'epics';
    const lay = layout(nodes, edges, isEpics ? 70 : 56, isEpics ? 16 : 12);
    const oy = isEpics ? 34 : 0;
    dims = { width: lay.width, height: lay.height + oy };
    canvas.classList.toggle('sparse', isEpics);
    const adj = { out: new Map(nodes.map(n => [n.id, []])), inn: new Map(nodes.map(n => [n.id, []])) };
    edges.forEach(e => { adj.out.get(e.a).push(e.b); adj.inn.get(e.b).push(e.a); });
    const edgeEls = [];
    const eg = sv('g', {}), ng = sv('g', {});
    vp.append(eg, ng);
    if (isEpics) {
      const colW = 226 + 70;
      D.milestoneOrder.forEach((m, i) => vp.append(sv('text', { x: i * colW, y: 16, class: 'colhead' }, `${m} · ${msName(m)}`)));
    }
    edges.forEach(e => {
      const a = lay.at.get(e.a), b = lay.at.get(e.b), na = nodes.find(n => n.id === e.a), nb = nodes.find(n => n.id === e.b);
      const x1 = a.x + na.w, y1 = a.y + oy + na.h / 2, x2 = b.x, y2 = b.y + oy + nb.h / 2;
      const dx = x2 > x1 + 8 ? Math.max(30, (x2 - x1) / 2) : 60;
      const p = sv('path', { class: `edge${e.crit ? ' crit' : ''}`, d: `M${x1} ${y1} C${x1 + dx} ${y1} ${x2 - dx} ${y2} ${x2} ${y2}`,
        'stroke-width': g.scope === 'epics' ? String(Math.min(5, 1 + e.n * 0.25)) : null });
      eg.append(p); edgeEls.push({ e, p });
    });
    nodes.forEach(n => {
      const p = lay.at.get(n.id);
      const cls = ['node', n.ghost && 'ghost', n.done && 'done', n.crit && 'crit', n.hit === false && 'dim'].filter(Boolean).join(' ');
      const t1 = n.kind === 'epic' ? trunc(n.title, 32) : trunc(n.title, 31);
      const grp = sv('g', { class: cls, style: tc(n.theme), transform: `translate(${p.x} ${p.y + oy})`, tabindex: '0', role: 'link',
        'aria-label': `${n.id} ${n.title}` },
        sv('title', {}, `${n.id} · ${n.title}`),
        sv('rect', { width: n.w, height: n.h, rx: 8 }),
        sv('text', { class: 'nid', x: 10, y: 16 }, n.kind === 'epic' ? n.id : n.id + (n.done ? ' ✓' : '')),
        sv('text', { x: 10, y: n.kind === 'epic' ? 34 : 33 }, t1),
        n.kind === 'epic' ? sv('text', { class: 'nid', x: 10, y: 51 }, n.sub) : null);
      grp.addEventListener('click', () => open(n.kind, n.id));
      grp.addEventListener('keydown', ev => { if (ev.key === 'Enter') open(n.kind, n.id); });
      grp.addEventListener('mouseenter', () => highlight(n.id));
      grp.addEventListener('mouseleave', () => highlight(null));
      ng.append(grp); nodeEls.set(n.id, grp);
    });
    function highlight(id) {
      if (!id) { nodeEls.forEach((el2, nid) => el2.classList.toggle('dim', model.nodes.find(n => n.id === nid).hit === false)); edgeEls.forEach(({ p }) => p.classList.remove('dim', 'hi')); return; }
      const keep = new Set([id]);
      const walk = (start, map) => { const st = [start]; while (st.length) { const c = st.pop(); for (const nx of map.get(c) || []) if (!keep.has(nx)) { keep.add(nx); st.push(nx); } } };
      walk(id, adj.inn); walk(id, adj.out);
      nodeEls.forEach((el2, nid) => el2.classList.toggle('dim', !keep.has(nid)));
      edgeEls.forEach(({ e, p }) => { const on = keep.has(e.a) && keep.has(e.b); p.classList.toggle('dim', !on); p.classList.toggle('hi', on); });
    }
    // legend
    const present = [...new Set(nodes.map(n => n.theme))];
    legend.replaceChildren(...THEMES.filter(t => present.includes(t)).map(t => h('span', { style: tc(t) }, h('i'), t)));
    note.textContent = `${nodes.length} nodes · ${edges.length} edges · ` + (isEpics ? 'columns are each epic\u2019s first milestone; hover an epic to trace its dependencies' : 'drag to pan, scroll to zoom');
    canvas.querySelectorAll('.empty').forEach(x => x.remove());
    if (!nodes.length) canvas.append(h('div', { class: 'empty', text: 'Nothing matches these filters.' }));
    if (doFit) requestAnimationFrame(fit); else apply();
    if (state.drawer) markSelected(state.drawer.id);
  }
  function markSelected(id) { nodeEls.forEach((el2, nid) => el2.classList.toggle('sel', nid === id)); }
  state.viewApi = { select: markSelected };

  wrap.append(toolbar, canvas);
  app.append(wrap);
  refreshToolbar();
  draw(true);
}

// ---------------------------------------------------------------- drawer
function closeDrawer() { state.drawer = null; const d = document.getElementById('drawer'); d.hidden = true; d.replaceChildren(); if (state.viewApi && state.viewApi.select) state.viewApi.select(null); }
function renderDrawer() {
  const d = document.getElementById('drawer');
  const cur = state.drawer;
  if (!cur) return closeDrawer();
  const close = h('button', { class: 'btn close', type: 'button', 'aria-label': 'Close details', text: 'Close', onclick: closeDrawer });
  d.replaceChildren();
  if (cur.kind === 'issue' && issues.has(cur.id)) {
    const i = issues.get(cur.id), e = epics.get(i.epic);
    const link = id => { const x = issues.get(id); return h('a', { class: 'depchip', href: `#/issue/${id}` }, statusDot(x.status), h('span', { class: 'id', text: id }), h('span', { text: x.title })); };
    put(d, close, h('div', { class: 'id', text: i.id }), h('h2', { text: i.title }),
      h('p', {}, themeChip(i.epic), ' ', msChip(i.milestone), ' ',
        h('span', { class: 'chip', text: `${i.type} · ${i.size}` }), ' ',
        h('span', { class: `chip status-${i.status}`, text: i.status }), ' ',
        ...i.lang.map(l => h('span', { class: 'chip', text: l }))),
      h('p', { text: i.summary }),
      h('h4', { text: 'Acceptance criteria' }), h('ul', {}, i.acceptance.map(a => h('li', { text: a }))),
      h('h4', { text: `Depends on (${i.deps.length})` }), i.deps.length ? i.deps.map(link) : h('p', { class: 'muted', text: 'Nothing. Can start now.' }),
      h('h4', { text: `Unblocks (${i.dependents.length})` }), i.dependents.length ? i.dependents.map(link) : h('p', { class: 'muted', text: 'Nothing downstream.' }),
      h('h4', { text: 'Adoption' }),
      h('p', { class: 'muted', text: i.stage ? `Needed from stage ${i.stage} (${(stageById.get(i.stage) || {}).name}) onward.` : 'Optional track; not required by a stage.' }),
      h('p', {}, h('a', { class: 'btn', href: `#/graph?scope=epic:${e.id}`, text: 'Open epic in graph' })));
  } else if (cur.kind === 'epic' && epics.has(cur.id)) {
    const e = epics.get(cur.id), list = D.issues.filter(i => i.epic === e.id);
    put(d, close, h('div', { class: 'id', text: e.id }), h('h2', { text: e.title }),
      h('p', {}, h('span', { class: 'chip theme', style: tc(e.theme), text: e.theme }), ' ', ...e.milestones.map(m => [msChip(m), ' '])),
      h('p', { text: e.goal }),
      h('p', { class: 'muted', text: `${list.length} issues · ${points(list)} points · ${list.filter(i => i.status === 'done').length} done` }),
      h('p', {}, h('a', { class: 'btn primary', href: `#/graph?scope=epic:${e.id}`, text: 'Open in graph' })),
      h('h4', { text: 'Issues' }), list.map(i => issueRow(i)));
  } else {
    put(d, close, h('p', { class: 'muted', text: `Unknown item ${cur.id}.` }));
  }
  d.hidden = false;
  d.scrollTop = 0;
}

// ---------------------------------------------------------------- chrome
document.addEventListener('keydown', e => { if (e.key === 'Escape' && state.drawer) closeDrawer(); });
document.addEventListener('click', e => {
  const a = e.target.closest && e.target.closest('a[href^="#/"]');
  if (!a) return;
  e.preventDefault();
  go(a.getAttribute('href').slice(1));
});
window.addEventListener('hashchange', () => {
  const next = routeFromLocation();
  if (parseRoute(next).seg[0] !== parseRoute(state.route).seg[0]) go(next);
});
go(routeFromLocation());
})();
