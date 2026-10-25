/* Console core: DOM helper, JSON fetch, and the Explain drawer. Shared byte-for-byte with the Financial Agent UI (a test enforces it).
   Every node is built with el() (no HTML parsing), so no data is ever treated as markup. */
(() => {
  'use strict';
  const SVG = new Set(['svg', 'g', 'path', 'rect', 'circle', 'text', 'line', 'defs', 'pattern', 'use', 'animateMotion', 'title', 'tspan']);
  function el(tag, attrs, ...kids) {
    const node = SVG.has(tag) ? document.createElementNS('http://www.w3.org/2000/svg', tag) : document.createElement(tag);
    for (const [key, value] of Object.entries(attrs || {})) {
      if (value === null || value === undefined || value === false) continue;
      if (key === 'text') node.textContent = value;
      else if (key.startsWith('on')) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? '' : String(value));
    }
    const add = kid => {
      if (Array.isArray(kid)) kid.forEach(add);
      else if (kid !== null && kid !== undefined && kid !== false) node.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    };
    kids.forEach(add);
    return node;
  }
  const $ = id => document.getElementById(id);
  const reduced = () => window.matchMedia('(prefers-reduced-motion: reduce)').matches;

  // "Live" means data arrived in the last minute AND its live sources answered; "Not live" means the API answered but the ops
  // agent did not (only declared values are shown); "Offline" means nothing answered.
  let liveTimer = null, reachable = false, degraded = false;
  function paintLive() {
    const badge = $('live');
    if (!badge) return;
    const on = reachable && !degraded;
    badge.classList.toggle('on', on);
    badge.textContent = on ? 'Live' : reachable ? 'Not live' : 'Offline';
  }
  function setLive(ok) {
    reachable = ok;
    clearTimeout(liveTimer);
    if (ok) liveTimer = setTimeout(() => setLive(false), 60000);
    paintLive();
  }
  function setDegraded(value) { degraded = value; paintLive(); }
  async function getJSON(path) {
    try {
      const response = await fetch(path, {credentials: 'same-origin', headers: {Accept: 'application/json'}});
      captureSource(response);
      const data = await response.json();
      if (path.startsWith('/api/console/')) setLive(response.ok);
      return {ok: response.ok, status: response.status, data};
    } catch (e) {
      if (path.startsWith('/api/console/')) setLive(false);
      return {ok: false, status: 0, data: null};
    }
  }
  const pad = n => String(n).padStart(2, '0');
  const clock = seconds => { const d = new Date(seconds * 1000); return pad(d.getHours()) + ':' + pad(d.getMinutes()); };
  function ago(seconds) {
    const s = Math.max(0, Math.round(Date.now() / 1000 - seconds));
    return s < 90 ? s + ' s ago' : s < 5400 ? Math.round(s / 60) + ' min ago' : s < 129600 ? Math.round(s / 3600) + ' h ago' : Math.round(s / 86400) + ' d ago';
  }
  const shortDigest = d => (typeof d === 'string' && /^sha256:[0-9a-f]{64}$/.test(d)) ? 'sha256:' + d.slice(7, 11) + '…' + d.slice(-4) : null;

  // Proof text: a live value rendered as short readable lines (never a fixed string standing in for a value).
  function lines(value, depth, out) {
    const space = '  '.repeat(depth);
    const scalar = v => v === null || ['string', 'number', 'boolean'].includes(typeof v);
    const brief = item => {
      if (scalar(item)) return String(item);
      const counts = Object.entries(item).filter(([, v]) => Array.isArray(v)).map(([k, v]) => k + ':' + v.length);
      const plain = Object.entries(item).filter(([k, v]) => k !== 'name' && scalar(v)).slice(0, 3).map(([k, v]) => k + '=' + v);
      return [item.name, ...plain, ...counts].filter(Boolean).join(' ');
    };
    for (const [key, v] of Object.entries(value)) {
      if (typeof v === 'number' && key.endsWith('_at')) out.push(space + key + ': ' + new Date(v * 1000).toLocaleTimeString() + ' (' + ago(v) + ')');
      else if (scalar(v)) out.push(space + key + ': ' + (v === null ? '—' : v));
      else if (Array.isArray(v)) {
        if (!v.length) out.push(space + key + ': none');
        else if (v.every(scalar)) out.push(space + key + ': ' + v.join(', '));
        else { out.push(space + key + ':'); v.forEach(item => out.push(space + '  - ' + brief(item))); }
      } else if (depth < 3) { out.push(space + key + ':'); lines(v, depth + 1, out); }
    }
    return out;
  }
  // Only the namespaces the clicked part is about (focus), when the proof is a per-namespace list.
  function narrow(proof, focus) {
    if (!focus || !focus.length) return proof;
    const keep = obj => Object.fromEntries(Object.entries(obj).filter(([ns]) => focus.includes(ns)));
    const out = {...proof};
    if (proof.namespaces) {
      out.namespaces = keep(proof.namespaces);
      if (!Object.keys(out.namespaces).length) out.namespaces = 'none of ' + focus.join(', ') + ' could be read live just now';
    }
    if (proof.default_deny) out.default_deny = keep(proof.default_deny);
    if (Array.isArray(proof.egress_to_addresses)) out.egress_to_addresses = proof.egress_to_addresses.filter(x => focus.includes(x.namespace));
    if (Array.isArray(proof.unreadable)) out.unreadable = proof.unreadable.filter(ns => focus.includes(ns));
    return out;
  }
  const SHORT = 6;
  function proofBox(proof, focus) {
    if (proof === null || proof === undefined) return el('p', {class: 'muted'}, 'No live proof available');
    const all = lines(narrow(proof, focus), 0, []).slice(0, 80);
    const box = el('pre', {class: 'code'}, all.slice(0, SHORT).join('\n'));
    if (all.length <= SHORT) return box;
    let open = false;
    const toggle = el('button', {type: 'button', class: 'btn link', 'aria-expanded': 'false', onclick: () => {
      open = !open;
      box.textContent = (open ? all : all.slice(0, SHORT)).join('\n');
      toggle.textContent = open ? 'Show less' : 'Show full proof (' + all.length + ' lines)';
      toggle.setAttribute('aria-expanded', String(open));
    }}, 'Show full proof (' + all.length + ' lines)');
    return el('div', {}, box, toggle);
  }
  let sourceRef = null;
  function captureSource(response) {
    const ref = response.headers.get('X-Platform-Source-Commit');
    sourceRef = typeof ref === 'string' && /^[0-9a-f]{40}$/.test(ref) ? ref : null;
  }
  const codeURL = file => sourceRef ? 'https://github.com/lamanasser56/secure-financial-ai-infrastructure/blob/' + sourceRef + '/' + file : null;
  // A long id shown as first 4 … last 4, with a button that copies the full value.
  function copyable(label, value) {
    const short = value.length > 12 ? value.slice(0, 4) + '…' + value.slice(-4) : value;
    const button = el('button', {type: 'button', class: 'btn link', 'aria-label': 'Copy the full ' + label, onclick: async () => {
      try { await navigator.clipboard.writeText(value); button.textContent = 'Copied'; } catch (e) { button.textContent = 'Copy failed'; }
      setTimeout(() => { button.textContent = 'Copy'; }, 1500);
    }}, 'Copy');
    return el('div', {class: 'sub-id mono muted'}, label + ' ', el('span', {title: value}, short), ' ', button);
  }

  // Explain drawer: closed by default; Esc, the close button or a click outside closes it; focus returns to the opener.
  // A screen can instead host Explain in its own layout (the Map shows it in its right column, nothing dimmed):
  // setDock({show(nodes, spec, from), hide() -> element to focus or null}), and setDock(null) when the screen goes.
  let opener = null, dock = null, docked = false;
  const setDock = d => { dock = d; docked = false; };
  function close() {
    if (dock && docked) {
      docked = false;
      const back = dock.hide();
      const to = opener && document.contains(opener) ? opener : back;
      if (to) to.focus();
      opener = null;
      return;
    }
    const drawer = $('explain');
    if (!drawer || drawer.hidden) return;
    drawer.hidden = true; $('scrim').hidden = true; drawer.replaceChildren();
    if (opener && document.contains(opener)) opener.focus();
    opener = null;
  }
  // spec: {eyebrow, live, title, sub, copy: {label, value}, blocks: [{label, text | node, cls}], file}
  function explain(spec, from) {
    const drawer = $('explain');
    opener = from || document.activeElement;
    const nodes = [
      el('button', {class: 'btn link close', type: 'button', 'aria-label': 'Close', onclick: close}, 'Close ✕'),
      el('div', {class: 'eyebrow' + (spec.live ? ' live-proof' : '')}, spec.eyebrow),
      el('h2', {id: 'ex-title'}, spec.title),
      spec.sub ? el('div', {class: 'sub-id mono muted'}, spec.sub) : null,
      spec.copy ? copyable(spec.copy.label, spec.copy.value) : null,
      ...spec.blocks.map(b => el('div', {class: 'block ' + (b.cls || '')}, el('div', {class: 'label'}, b.label), b.node || el('p', {}, b.text))),
      spec.file ? el('div', {class: 'file'}, el('div', {class: 'path mono muted'}, spec.file),
        codeURL(spec.file) ? el('a', {class: 'btn link', href: codeURL(spec.file), target: '_blank', rel: 'noopener', title: spec.file}, 'View code →')
          : el('span', {class: 'muted'}, 'Source version unavailable')) : null].filter(Boolean);
    if (dock) {
      docked = true;
      dock.show(nodes, spec, opener);
      nodes[0].focus();
      return;
    }
    drawer.replaceChildren(...nodes);
    drawer.classList.toggle('proof-live', !!spec.live);
    drawer.classList.toggle('slide', !reduced());
    drawer.hidden = false; $('scrim').hidden = false;
    drawer.querySelector('.close').focus();
  }
  document.addEventListener('keydown', e => { if (e.key === 'Escape') close(); });
  document.addEventListener('click', e => { if (e.target.id === 'scrim') close(); });

  // The layer each platform topic rests on (fixed wording, like the title; the infrastructure files say so:
  // ADVANCED_DATAPATH, private_endpoints.tf, no Cloud NAT, the redactor's Sensitive Data Protection adapter, LiteLLM).
  const LAYER = {network: 'Kubernetes NetworkPolicy · GKE Dataplane V2', 'private-link': 'Private Service Connect · FQDNNetworkPolicy',
                 internet: 'default-deny egress · no Cloud NAT', redactor: 'Sensitive Data Protection · fails closed',
                 gateway: 'LiteLLM · one scoped key per agent', audit: 'one JSON line per request · no content'};
  // The six platform topics: wording and proof both come from /api/console/explain (proof is live or null).
  async function explainTopic(topic, from, focus) {
    const r = await getJSON('/api/console/explain/' + encodeURIComponent(topic));
    if (!r.ok) {
      explain({eyebrow: 'EXPLAIN · NOT SEEN LIVE', title: topic, blocks: [{label: 'Proof', node: proofBox(null)}]}, from);
      return;
    }
    const d = r.data;
    // "Verified live" only if the part clicked has live proof of its own (a focused list with no readable namespace has none).
    const seen = !!d.proof && typeof narrow(d.proof, focus).namespaces !== 'string';
    explain({eyebrow: seen ? 'EXPLAIN · VERIFIED LIVE' : 'EXPLAIN · NOT SEEN LIVE', live: seen, title: d.title, sub: LAYER[topic],
             blocks: [{label: 'In plain words', text: d.plain}, {label: 'How it works', text: d.how},
                      {label: 'Proof' + (d.proof && d.proof.source ? ' · ' + d.proof.source : ''), node: proofBox(d.proof, focus)},
                      {label: 'Without it', text: d.without, cls: 'without'}], file: d.file}, from);
  }
  const head = (title, sub, action) => el('div', {class: 'head'}, el('div', {}, el('h1', {}, title), sub ? el('p', {class: 'sub'}, sub) : null), action || null);
  const empty = (title, text) => el('div', {class: 'panel empty'}, el('strong', {}, title), text);
  window.Console = {captureSource, codeURL, head, empty, el, $, reduced, setLive, setDegraded, getJSON, clock, ago, shortDigest, proofBox, explain, explainTopic, close, setDock, screens: {}};
})();
