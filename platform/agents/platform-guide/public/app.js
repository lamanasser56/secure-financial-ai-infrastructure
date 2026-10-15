'use strict';
const form = document.getElementById('ask');
form.addEventListener('submit', async (event) => {
  event.preventDefault();
  const out = document.getElementById('out');
  const body = { question: document.getElementById('q').value, language: document.getElementById('lang').value };
  const response = await fetch('/api/ask', { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
  const data = await response.json();
  document.getElementById('answer').textContent = data.answer || ('No answer: ' + (data.reason || data.error || 'error'));
  const list = document.getElementById('sources');
  list.textContent = '';
  for (const source of data.sources || []) {
    const item = document.createElement('li');
    item.textContent = source.path + ' — ' + source.heading;
    list.appendChild(item);
  }
  document.getElementById('trace').textContent = JSON.stringify(data.trace || {}, null, 2);
  out.hidden = false;
});
