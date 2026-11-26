const state = { stats: { done: 0, pending: 0, failed: 0 }, queue: [], products: [], running: false, log: '' };
const $ = (id) => document.getElementById(id);
let authenticated = false;

function toast(message) {
  const node = $('toast'); node.textContent = message; node.classList.add('show');
  window.clearTimeout(toast.timer); toast.timer = window.setTimeout(() => node.classList.remove('show'), 2600);
}

function render() {
  $('done-count').textContent = state.stats.done || 0;
  $('pending-count').textContent = state.stats.pending || 0;
  $('failed-count').textContent = state.stats.failed || 0;
  $('field-count').textContent = state.products.length ? `${Math.round(state.products.length * 8.4)}` : '—';
  $('success-rate').textContent = state.stats.done || state.stats.failed ? `${Math.round((state.stats.done / Math.max(1, state.stats.done + state.stats.failed)) * 100)}%` : '—';
  $('hero-status').textContent = state.running ? 'Scrape in progress' : 'Ready for your next run';
  $('last-run').textContent = state.running ? 'Running now' : (state.stats.done ? 'Completed recently' : 'Not started');
  $('queue-list').innerHTML = state.queue.length ? state.queue.map(item => `<div class="queue-item"><span class="queue-url" title="${escapeHtml(item.url)}">${escapeHtml(item.url)}</span><span class="status ${item.status}"><i class="status-dot"></i>${item.status}</span></div>`).join('') : '<div class="empty-state">Your queue is waiting for its first URL.</div>';
  $('product-list').innerHTML = state.products.length ? state.products.slice(0, 5).map(product => `<div class="product-item"><div><div class="product-name">${escapeHtml(product.product_name || 'Untitled product')}</div><div class="product-meta">${escapeHtml(product.brand_name || 'Faire catalog')} · ${escapeHtml(product.sku || 'SKU pending')}</div></div><span class="status done"><i class="status-dot"></i>Captured</span></div>`).join('') : '<div class="empty-state">Completed products will appear here.</div>';
  $('scrape-log').textContent = state.log || 'Waiting for a run…';
}
function escapeHtml(value) { return String(value).replace(/[&<>'"]/g, (char) => ({'&':'&amp;','<':'&lt;','>':'&gt;',"'":'&#39;','"':'&quot;'}[char])); }
async function refresh() {
  if (!authenticated) return;
  try {
    const response = await fetch('/api/state'); if (!response.ok) throw new Error('offline');
    const data = await response.json(); Object.assign(state, data); state.running = Boolean(data.running); render();
    if (data.process_exit && !state.stats.done && !state.stats.failed && state.stats.pending) toast(data.last_error ? `Scraper stopped: ${data.last_error.split('\n').pop()}` : 'The scraper stopped before processing the queue.');
  } catch (_) { render(); }
}
async function checkAuth() {
  const response = await fetch('/api/auth/status');
  const status = await response.json();
  if (status.authenticated) { authenticated = true; $('auth-gate').classList.add('hidden'); render(); refresh(); return; }
  $('auth-title').textContent = status.configured ? 'Sign in to Faire Scraper' : 'Create your app password';
  $('auth-help').textContent = status.configured ? 'This protects the scraper dashboard. Faire credentials are never stored here.' : 'Choose at least 10 characters. This password protects only this scraper app.';
  $('auth-submit').textContent = status.configured ? 'Sign in' : 'Create password';
  $('auth-form').dataset.mode = status.configured ? 'login' : 'setup';
}
async function submitAuth(event) {
  event.preventDefault();
  const mode = $('auth-form').dataset.mode || 'login';
  const response = await fetch(`/api/auth/${mode}`, { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ password: $('auth-password').value }) });
  if (!response.ok) { $('auth-error').textContent = (await response.json()).error || 'Authentication failed'; return; }
  $('auth-password').value = ''; authenticated = true; $('auth-gate').classList.add('hidden'); render(); refresh();
}
async function addUrls() {
  const urls = $('url-input').value.split(/\n+/).map((url) => url.trim()).filter(Boolean);
  if (!urls.length) return toast('Paste at least one product URL first.');
  try { const response = await fetch('/api/queue', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ urls }) }); if (!response.ok) throw new Error(); $('url-input').value = ''; await refresh(); toast(`${urls.length} URL${urls.length === 1 ? '' : 's'} added to the queue.`); }
  catch (_) { urls.forEach(url => state.queue.push({ url, status:'pending' })); state.stats.pending += urls.length; $('url-input').value = ''; render(); toast('Added locally. Start the web server to persist queue changes.'); }
}
function parseCsv(text) {
  const rows = []; let row = []; let cell = ''; let quoted = false;
  for (let index = 0; index < text.length; index += 1) {
    const char = text[index];
    if (char === '"') { if (quoted && text[index + 1] === '"') { cell += '"'; index += 1; } else { quoted = !quoted; } }
    else if (char === ',' && !quoted) { row.push(cell.trim()); cell = ''; }
    else if ((char === '\n' || char === '\r') && !quoted) { if (char === '\r' && text[index + 1] === '\n') index += 1; row.push(cell.trim()); if (row.some(Boolean)) rows.push(row); row = []; cell = ''; }
    else { cell += char; }
  }
  if (cell || row.length) { row.push(cell.trim()); if (row.some(Boolean)) rows.push(row); }
  return rows;
}
async function uploadCsv(event) {
  const file = event.target.files[0]; if (!file) return;
  const rows = parseCsv(await file.text());
  if (!rows.length) return toast('That CSV file is empty.');
  const headerIndex = rows[0].findIndex((value) => /^(url|product.?url|link)$/i.test(value.replace(/\s/g, '')));
  const sourceRows = headerIndex >= 0 ? rows.slice(1).map((row) => row[headerIndex]) : rows.flat();
  const urls = sourceRows.filter((value) => /^https?:\/\/(?:www\.)?faire\.com\/product\//i.test(value));
  if (!urls.length) return toast('No Faire product URLs found in that CSV.');
  try { const response = await fetch('/api/queue', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ urls }) }); if (!response.ok) throw new Error(); await refresh(); toast(`${urls.length} URL${urls.length === 1 ? '' : 's'} imported from CSV.`); }
  catch (_) { urls.forEach((url) => state.queue.push({ url, status:'pending' })); state.stats.pending += urls.length; render(); toast(`${urls.length} URL${urls.length === 1 ? '' : 's'} loaded locally.`); }
  event.target.value = '';
}
async function startScrape() {
  if (state.running) return toast('A scrape is already running.');
  try { const response = await fetch('/api/scrape', { method:'POST' }); if (!response.ok) throw new Error(); state.running = true; render(); toast('Scrape started.'); await refresh(); }
  catch (_) { toast('Scraper controls connect when the local web server is running.'); }
}
async function controlScrape(action) {
  try { const response = await fetch('/api/control', { method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify({ action }) }); if (!response.ok) throw new Error(); toast(`${action[0].toUpperCase()}${action.slice(1)} requested.`); await refresh(); }
  catch (_) { toast('No active scrape process to control.'); }
}
function exportCsv() { window.location.href = '/api/export?format=csv'; }
function exportFile(format) { window.location.href = `/api/export?format=${format}`; }
document.addEventListener('DOMContentLoaded', () => { $('auth-form').addEventListener('submit', submitAuth); checkAuth(); $('refresh').addEventListener('click', refresh); $('add-urls').addEventListener('click', addUrls); $('csv-input').addEventListener('change', uploadCsv); $('start-scrape').addEventListener('click', startScrape); $('pause-scrape').addEventListener('click', () => controlScrape('pause')); $('resume-scrape').addEventListener('click', () => controlScrape('resume')); $('stop-scrape').addEventListener('click', () => controlScrape('stop')); $('export-csv').addEventListener('click', exportCsv); $('export-xlsx').addEventListener('click', () => exportFile('xlsx')); $('export-jsonl').addEventListener('click', () => exportFile('jsonl')); document.querySelectorAll('.nav-item[data-view]').forEach(button => button.addEventListener('click', () => { document.querySelectorAll('.nav-item').forEach(item => item.classList.remove('active')); button.classList.add('active'); toast(`${button.dataset.view[0].toUpperCase()}${button.dataset.view.slice(1)} view selected.`); })); window.setInterval(refresh, 3000); });
