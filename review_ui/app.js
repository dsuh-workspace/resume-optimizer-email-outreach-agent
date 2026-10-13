'use strict';
const $ = id => document.getElementById(id);
const token = document.querySelector('meta[name="review-token"]').content;
$('pair-code').onclick = async () => {
  try {const result = await api('/api/extension/pair-code', {extension_id: $('extension-id').value.trim()}); $('pair-status').textContent = `Paste this code into the extension within 5 minutes: ${result.code}`;}
  catch(error) {$('pair-status').textContent = error.message;}
};
$('revoke-extension').onclick = async () => {
  try {await api('/api/extension/revoke', {}); $('pair-status').textContent = 'All extension connections and pending pairing codes have been revoked.';}
  catch(error) {$('pair-status').textContent = error.message;}
};
let packets = [], current = null, busy = false, loading = 0;
const node = (tag, text, className) => {const e = document.createElement(tag); if(text !== undefined) e.textContent = text; if(className) e.className = className; return e;};
const texts = () => [...document.querySelectorAll('.bullet textarea')].map(e => e.value);
const dirty = () => current && texts().some((s, i) => s !== current.bullets[i].text);
function status(text = '', error = false) { $('status').textContent = text; $('status').className = (text ? 'visible' : '') + (error ? ' error' : ''); }
async function api(path, payload) {
  const response = await fetch(path, payload ? {method:'POST', headers:{'Content-Type':'application/json','X-Review-Token':token}, body:JSON.stringify(payload)} : {});
  const data = await response.json(); if(!response.ok) throw new Error(data.error || 'Request failed.'); return data;
}
function renderList() {
  const query = $('search').value.toLowerCase(); $('packets').replaceChildren();
  const visible = packets.filter(p => `${p.company} ${p.role}`.toLowerCase().includes(query));
  if(!visible.length) $('packets').append(node('p', packets.length ? 'No matching applications.' : 'No saved packets yet. Generate a resume to begin.', 'empty'));
  for(const p of visible) {
    const button = node('button', undefined, 'packet' + (current?.id === p.id ? ' active' : '')); button.disabled = busy;
    button.append(node('strong', p.company), node('span', p.role), node('small', (p.edited ? 'Edited version · ' : '') + p.version));
    button.setAttribute('aria-current', current?.id === p.id ? 'true' : 'false'); button.onclick = () => select(p.id); $('packets').append(button);
  }
}
function updateEdits() {
  const values = texts(), count = current ? values.filter((s,i) => s !== current.bullets[i].text).length : 0;
  $('edit-count').textContent = busy ? 'Checking evidence and generating PDF…' : count ? `${count} unsaved bullet ${count === 1 ? 'edit' : 'edits'}` : 'No unsaved changes';
  $('save').disabled = busy || !count || !current?.editable; $('discard').disabled = busy || !count;
  document.querySelectorAll('.bullet').forEach((card,i) => {card.classList.toggle('changed', values[i] !== current.bullets[i].text); card.querySelector('textarea').disabled = busy || !current.editable; card.querySelector('button').disabled = busy || values[i] === current.bullets[i].text;});
}
function renderDetail(detail) {
  current = detail; $('welcome').hidden = true; $('workspace').hidden = false;
  $('company').textContent = detail.company; $('role').textContent = detail.role; $('version').textContent = detail.folder;
  $('state').textContent = detail.editable ? 'Evidence checked' : 'View only'; $('state').className = 'pill' + (detail.editable ? '' : ' warn');
  $('notices').replaceChildren();
  for(const problem of [...detail.problems, ...detail.context.errors]) $('notices').append(node('div', problem, 'notice'));
  if(detail.review_revision) $('notices').append(node('div', 'This is an edited resume. Existing Gmail drafts still contain their original attachments. Review the email claims and replace the attachment in Gmail before sending. The match estimate has not been recalculated.', 'notice'));
  $('pdf').hidden = !detail.pdf_url; $('pdf-link').hidden = !detail.pdf_url; $('no-pdf').hidden = !!detail.pdf_url;
  if(detail.pdf_url) {$('pdf').src = detail.pdf_url + '#toolbar=0&view=FitH'; $('pdf-link').href = detail.pdf_url;} else {$('pdf').removeAttribute('src'); $('pdf-link').removeAttribute('href');}
  $('bullets').replaceChildren();
  detail.bullets.forEach((bullet, i) => {
    const card = node('article', undefined, 'bullet'), heading = node('div', undefined, 'bullet-heading');
    heading.append(node('h3', bullet.company), node('span', `BULLET ${bullet.index + 1}`)); card.append(heading);
    const source = node('div', undefined, 'source'); source.append(node('span', 'Verified original', 'label'));
    if(bullet.original.length) {bullet.original.forEach(text => source.append(node('p', text))); source.append(node('code', bullet.source_refs.join(' · ')));}
    else source.append(node('p', 'Verified source evidence is unavailable for this packet.'));
    card.append(source); const label = node('label', 'Your tailored bullet', 'label'); label.htmlFor = `bullet-${i}`;
    const input = node('textarea'); input.id = `bullet-${i}`; input.value = bullet.text; input.maxLength = 2000; input.disabled = !detail.editable; input.oninput = updateEdits;
    const reset = node('button', 'Reset this bullet', 'quiet reset'); reset.onclick = () => {input.value = bullet.text; updateEdits();};
    card.append(label, input, reset); $('bullets').append(card);
  });
  $('skills').replaceChildren();
  for(const skill of detail.skills) {const el = node('div', undefined, 'skill'); el.append(node('strong', skill.rewritten), node('p', skill.original), node('code', skill.source_ref)); $('skills').append(el);}
  if(!detail.skills.length) $('skills').append(node('p', 'No validated skill evidence is available.'));
  renderOutreach(detail); updateEdits(); renderList();
}
function renderOutreach(detail) {
  $('contacts').replaceChildren(); $('messages').replaceChildren();
  if(!detail.context.contacts.length) $('contacts').append(node('p', 'No structured contact verification is saved for this packet. Check the full review notes below if available.', 'empty'));
  for(const contact of detail.context.contacts) {
    const card = node('article', undefined, 'contact'); card.append(node('span', (contact.kind || 'Contact').replaceAll('_', ' '), 'label'), node('h3', contact.email));
    card.append(node('p', `Source: ${contact.source || 'Unavailable'} · Status: ${contact.status || 'Unavailable'}`), node('p', `Score: ${contact.score ?? 'Not recorded'} · Checked: ${contact.checked_at || 'Not recorded'}`, 'subtle'));
    if(contact.source === 'user_provided' || contact.status === 'user_provided') card.append(node('p', 'User-provided address; not independently verified.', 'subtle'));
    $('contacts').append(card);
  }
  if(!detail.context.messages.length) $('messages').append(node('p', 'No Gmail draft creation snapshot is saved for this packet. Older email copy may appear in the full review notes.', 'empty'));
  for(const message of detail.context.messages) {
    const card = node('article', undefined, 'message'); card.append(node('span', message.state === 'created' ? 'Draft creation snapshot' : 'Draft creation unconfirmed', 'label'), node('h3', message.recipient), node('p', message.subject), node('pre', message.body || 'No body saved.'));
    card.append(node('p', `Originally attached: ${message.attachment_path || 'No attachment'}`, 'subtle'), node('p', `Created: ${message.created_at || 'Not recorded'} · Draft ID: ${message.draft_id || 'Unavailable'}`, 'subtle'));
    if(message.attachment_sha256 && detail.review_revision) card.append(node('p', 'This snapshot predates your edited resume. Replace the attachment in Gmail.', 'notice'));
    const link = node('a', 'Open Gmail drafts ↗'); link.href = 'https://mail.google.com/mail/u/0/#drafts'; link.target = '_blank'; link.rel = 'noopener noreferrer'; card.append(link); $('messages').append(card);
  }
  $('notes').textContent = detail.context.notes; $('notes-wrap').hidden = !detail.context.notes;
}
async function select(id) {
  if(busy || (dirty() && !confirm('Discard your unsaved bullet edits and open another packet?'))) return;
  const request = ++loading; busy = true; updateEdits(); renderList(); status('Loading packet…');
  try {const detail = await api(`/api/packets/${id}`); if(request !== loading) return; busy = false; renderDetail(detail); history.replaceState(null, '', `#${id}`); status();}
  catch(error) {if(request === loading) {busy = false; updateEdits(); renderList(); status(error.message, true);}}
}
async function refresh() {
  try {packets = await api('/api/packets'); renderList();} catch(error) {status(error.message, true);}
}
$('save').onclick = async () => {
  const payload = {revision: current.revision, bullets: texts()}; busy = true; updateEdits(); renderList(); status('Validating your changes and rebuilding the one-page PDF…');
  try {
    const result = await api(`/api/packets/${current.id}/save`, payload); busy = false; renderDetail(result); history.replaceState(null, '', `#${result.id}`); await refresh(); status('New version saved. The PDF preview now shows your edits. Existing Gmail drafts are unchanged.');
  } catch(error) {busy = false; updateEdits(); renderList(); status(error.message, true);}
};
$('discard').onclick = () => {if(confirm('Discard all unsaved bullet edits?')) {renderDetail(current); status();}};
$('search').oninput = renderList; $('refresh').onclick = refresh;
const tabs = [...document.querySelectorAll('[data-tab]')];
function activateTab(tab) {tabs.forEach(button => {const active = button === tab; button.setAttribute('aria-selected', String(active)); button.tabIndex = active ? 0 : -1; $(button.dataset.tab + '-panel').hidden = !active;});}
tabs.forEach((tab, i) => {tab.onclick = () => activateTab(tab); tab.onkeydown = event => {if(['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {event.preventDefault(); const next = tabs[event.key === 'Home' ? 0 : event.key === 'End' ? tabs.length - 1 : (i + (event.key === 'ArrowRight' ? 1 : tabs.length - 1)) % tabs.length]; activateTab(next); next.focus();}};});
window.addEventListener('beforeunload', event => {if(dirty() || busy) {event.preventDefault(); event.returnValue = '';}});
(async () => {await refresh(); const id = new URLSearchParams(location.search).get('packet') || location.hash.slice(1); if(id && packets.some(p => p.id === id)) await select(id);})();

const pairingID=new URLSearchParams(location.search).get("extension_id");
if(/^[a-p]{32}$/.test(pairingID||"")){$("extension-id").value=pairingID;$("extension-id").closest("details").open=true;}
