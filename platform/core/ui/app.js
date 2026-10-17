/* Console shell: hash router and the small helpers the screens share. Data comes only from /api/console/* (read-only). */
(() => {
  'use strict';
  const {el, $, getJSON} = Console;
  let timers = [], serial = 0;

  // Run fn now and then every `ms` while this screen is open (paused while the tab is hidden).
  Console.every = (fn, ms) => { fn(); timers.push(setInterval(() => { if (!document.hidden) fn(); }, ms)); };
  Console.display = name => name.split('-').map(w => w[0].toUpperCase() + w.slice(1)).join(' ');
  // Health chip from agents[].health: RUNNING / NOT READY / ABSENT; nothing at all when health is null (the source cannot say).
  Console.healthChip = health => {
    if (!health) return null;
    const map = {running: ['allowed', 'Running'], not_ready: ['denied', 'Not ready'], absent: ['muted', 'Absent']}[health.state];
    return map ? el('span', {class: 'chip ' + map[0]}, map[1]) : null;
  };
  Console.countsText = c => c ? c.verified + ' verified · ' + c.declared + ' declared' + (c.failing ? ' · ' + c.failing + ' failing' : '') : 'checks unavailable';

  // Everything the Map, Agents and Onboard screens need about the agents, from the console API only.
  Console.loadAgents = async () => {
    const [agents, topology] = await Promise.all([getJSON('/api/console/agents'), getJSON('/api/console/topology')]);
    if (!agents.ok) return null;
    const list = agents.data.agents;
    Console.setDegraded(!agents.data.live_available);
    const onboarding = await Promise.all(list.map(a => getJSON('/api/console/onboarding/' + encodeURIComponent(a.name))));
    return {agents: list, onboarding: Object.fromEntries(list.map((a, i) => [a.name, onboarding[i].ok ? onboarding[i].data : null])),
            topology: topology.ok ? topology.data : null, liveAvailable: agents.data.live_available};
  };

  const screens = ['map', 'agents', 'onboard', 'ops', 'break'];
  const titles = {map: 'Map', agents: 'Agents', onboard: 'Onboard', ops: 'Ops', break: 'Break it'};
  function route() {
    Console.close();
    timers.forEach(clearInterval); timers = [];
    const [first, arg] = location.hash.replace(/^#\/?/, '').split('/');
    const name = screens.includes(first) ? first : 'map';
    const mine = ++serial;
    document.querySelectorAll('nav.tabs a').forEach(a => { if (a.dataset.tab === name) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    document.title = titles[name] + ' · Agent Platform';
    const view = $('view');
    view.replaceChildren();
    Console.screens[name](view, arg ? decodeURIComponent(arg) : null, () => mine === serial);
  }
  window.addEventListener('hashchange', route);
  route();
})();
