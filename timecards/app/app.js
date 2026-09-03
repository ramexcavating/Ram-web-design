/* RAM Timecard: a single-file, offline-first daily timecard.
   Data lives on the phone (localStorage). A card is sent as plain text with a machine-readable block that the
   finance system (finance/ramfin, `timecards` module) reads straight into the timesheet tables. */
(() => {
  'use strict';
  const STORE = 'ramtc.v1';
  const REF_CACHE = 'ramtc.ref';
  const $ = (sel, el = document) => el.querySelector(sel);
  const h = (tag, attrs = {}, ...kids) => {
    const el = document.createElement(tag);
    for (const [k, v] of Object.entries(attrs)) {
      if (k === 'class') el.className = v;
      else if (k === 'html') el.innerHTML = v;
      else if (k.startsWith('on')) el.addEventListener(k.slice(2), v);
      else if (v === false || v == null || (k === 'disabled' && !v)) continue;
      else el.setAttribute(k, v === true ? '' : v);
    }
    for (const kid of kids.flat()) if (kid != null && kid !== false) el.append(kid.nodeType ? kid : document.createTextNode(String(kid)));
    return el;
  };

  // ------------------------------------------------------------------ dates
  const pad = (n) => String(n).padStart(2, '0');
  const todayISO = () => { const d = new Date(); return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`; };
  const parseISO = (iso) => { const [y, m, d] = iso.split('-').map(Number); return new Date(y, m - 1, d); };
  const toISO = (d) => `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`;
  const addDays = (iso, n) => { const d = parseISO(iso); d.setDate(d.getDate() + n); return toISO(d); };
  const daysBetween = (a, b) => Math.round((parseISO(b) - parseISO(a)) / 86400000);
  const fmt = (iso, opts = { weekday: 'short', month: 'short', day: 'numeric' }) => parseISO(iso).toLocaleDateString('en-CA', opts);
  const periodEnd = (iso) => {
    const pp = REF.payPeriod; const diff = daysBetween(pp.anchorEnd, iso);
    return addDays(pp.anchorEnd, pp.days * Math.ceil(diff / pp.days));
  };
  const periodDays = (pe) => Array.from({ length: REF.payPeriod.days }, (_, i) => addDays(pe, i - (REF.payPeriod.days - 1)));

  // ------------------------------------------------------------------ state
  const blank = () => ({ profile: { name: '', position: '', supervisor: '', defaultJob: '', submitTo: '' }, days: {}, recents: { codes: [], units: [], jobs: [] }, sent: {} });
  let state = blank();
  try { const raw = localStorage.getItem(STORE); if (raw) state = Object.assign(blank(), JSON.parse(raw)); } catch (e) { /* fresh start */ }
  const save = () => { try { localStorage.setItem(STORE, JSON.stringify(state)); } catch (e) { toast('Could not save on this phone (storage full or blocked)'); } };
  const uid = () => Math.random().toString(36).slice(2, 9);
  const num = (v) => { const n = parseFloat(v); return isFinite(n) && n > 0 ? Math.round(n * 4) / 4 : 0; };
  const fmtH = (n) => (Math.round(n * 100) / 100).toString();

  let REF = null;
  const ui = { tab: 'day', date: todayISO() };

  const getDay = (iso) => state.days[iso] || (state.days[iso] = { date: iso, lines: [], loa: false, pu: false, km: 0, notes: '' });
  const dayHours = (d) => d.lines.reduce((a, l) => ({ reg: a.reg + l.reg, ot: a.ot + l.ot, dt: a.dt + l.dt, eq: a.eq + (l.unit ? l.eq : 0) }), { reg: 0, ot: 0, dt: 0, eq: 0 });
  const labour = (l) => l.reg + l.ot + l.dt;
  const hasWork = (d) => d && (d.lines.length || d.loa || d.pu || d.km);
  const jobName = (no) => (REF.jobs.find((j) => j.no === no) || {}).name || '';
  const codeDesc = (cc) => (REF.costCodes.find((c) => c.code === cc) || {}).desc || '';
  const unitType = (u) => (REF.equipment.find((e) => e.unit === u) || {}).type || '';
  const remember = (list, key, max = 8) => { const i = list.indexOf(key); if (i >= 0) list.splice(i, 1); list.unshift(key); list.length = Math.min(list.length, max); };

  // ------------------------------------------------------------------ validation
  const problems = (d) => {
    const out = [];
    if (!state.profile.name.trim()) out.push('Add your name under Me before sending.');
    if (!d.lines.length && !d.loa && !d.pu && !d.km) out.push('Nothing on this day yet.');
    d.lines.forEach((l, i) => {
      if (!l.job) out.push(`Line ${i + 1}: pick a job.`);
      if (!l.cc) out.push(`Line ${i + 1}: pick a cost code.`);
      if (!labour(l) && !(l.unit && l.eq)) out.push(`Line ${i + 1}: no hours.`);
      if (l.unit && l.eq > labour(l) && labour(l) > 0) out.push(`Line ${i + 1}: ${l.unit} has more hours than you do on that line. Fine if someone else ran it too, otherwise check it.`);
    });
    const t = dayHours(d);
    if (t.reg + t.ot + t.dt > REF.maxHoursDay) out.push(`${fmtH(t.reg + t.ot + t.dt)} hours in one day. Check it before sending.`);
    return out;
  };

  // ------------------------------------------------------------------ output
  const buildText = (days) => {
    const p = state.profile;
    const pe = periodEnd(days[0].date);
    const L = [];
    L.push('RAM EXCAVATING TIMECARD');
    L.push(`Employee: ${p.name}${p.position ? ' (' + p.position + ')' : ''}`);
    if (p.supervisor) L.push(`Supervisor: ${p.supervisor}`);
    L.push(`Pay period end: ${pe} (${fmt(pe, { month: 'short', day: 'numeric', year: 'numeric' })})`);
    L.push('');
    let reg = 0, ot = 0, dt = 0, eq = 0, loa = 0, pu = 0, km = 0;
    for (const d of days) {
      const t = dayHours(d); reg += t.reg; ot += t.ot; dt += t.dt; eq += t.eq; loa += d.loa ? 1 : 0; pu += d.pu ? 1 : 0; km += d.km || 0;
      L.push(`${fmt(d.date, { weekday: 'long', month: 'long', day: 'numeric' })}  Reg ${fmtH(t.reg)}  OT ${fmtH(t.ot)}  DT ${fmtH(t.dt)}  Equip ${fmtH(t.eq)}`);
      for (const l of d.lines) {
        const bits = [`${l.job} ${jobName(l.job)}`.trim(), `${l.cc} ${codeDesc(l.cc)}`.trim()];
        const hrs = []; if (l.reg) hrs.push(`${fmtH(l.reg)} reg`); if (l.ot) hrs.push(`${fmtH(l.ot)} OT`); if (l.dt) hrs.push(`${fmtH(l.dt)} DT`);
        bits.push(hrs.join(' + ') || 'no labour');
        if (l.unit) bits.push(`${l.unit} ${fmtH(l.eq)} h`);
        L.push('  - ' + bits.join(' | ') + (l.desc ? `\n    ${l.desc.replace(/\n/g, '\n    ')}` : ''));
      }
      const extras = []; if (d.loa) extras.push('LOA'); if (d.pu) extras.push('P/U truck'); if (d.km) extras.push(`Travel ${d.km} km`);
      if (extras.length) L.push('  ' + extras.join(' | '));
      if (d.notes) L.push('  Notes: ' + d.notes.replace(/\n/g, ' '));
      L.push('');
    }
    if (days.length > 1) L.push(`TOTALS  Reg ${fmtH(reg)}  OT ${fmtH(ot)}  DT ${fmtH(dt)}  Equip ${fmtH(eq)}  LOA ${loa}  P/U ${pu}  Travel ${km} km`);
    L.push('');
    L.push('--RAMTC1--');
    L.push(JSON.stringify(buildPayload(days, pe)));
    L.push('--END--');
    return L.join('\n');
  };
  const buildPayload = (days, pe) => ({
    v: 1, employee: state.profile.name.trim(), position: state.profile.position || undefined, supervisor: state.profile.supervisor || undefined,
    periodEnd: pe, sentAt: new Date().toISOString(),
    days: days.map((d) => ({
      date: d.date, loa: !!d.loa, pu: !!d.pu, km: d.km || 0, notes: d.notes || undefined,
      lines: d.lines.map((l) => ({ job: l.job, cc: l.cc, reg: l.reg, ot: l.ot, dt: l.dt, unit: l.unit || undefined, eq: l.unit ? l.eq : undefined, desc: l.desc || undefined })),
    })),
  });
  const subjectFor = (days) => `RAM Timecard | ${state.profile.name.trim()} | ${days.length === 1 ? days[0].date : 'PP ' + periodEnd(days[0].date)}`;

  async function send(days, how) {
    const text = buildText(days); const subject = subjectFor(days); const to = state.profile.submitTo || REF.submitTo;
    const mark = () => { const ts = new Date().toISOString(); days.forEach((d) => { state.sent[d.date] = ts; }); save(); render(); };
    if (how === 'copy') {
      try { await navigator.clipboard.writeText(text); toast('Copied. Paste it into an email or text to the office.'); mark(); }
      catch (e) { openSheet(h('div', {}, h('h1', {}, 'Copy this'), h('pre', { class: 'preview' }, text))); }
      return;
    }
    if (how === 'share' && navigator.share) {
      const fname = `${subject.replace(/[^A-Za-z0-9]+/g, '_')}.txt`;
      try {
        const file = new File([text], fname, { type: 'text/plain' });
        if (navigator.canShare && navigator.canShare({ files: [file] })) await navigator.share({ title: subject, text: `${subject}\n\n${text}`, files: [file] });
        else await navigator.share({ title: subject, text });
        toast('Shared'); mark();
      } catch (e) { if (e && e.name !== 'AbortError') toast('Share did not work here. Try Email.'); }
      return;
    }
    // email: the default. Works on any phone with a mail app; the office inbox is read by the finance system.
    window.location.href = `mailto:${encodeURIComponent(to)}?subject=${encodeURIComponent(subject)}&body=${encodeURIComponent(text)}`;
    setTimeout(mark, 800);
  }

  // ------------------------------------------------------------------ sheets, toasts, lists
  // Sheets stack: a picker opens on top of the line editor and closing it brings the editor back.
  const sheet = $('#sheet'); const sheetBody = $('#sheet-body'); const sheetStack = [];
  function openSheet(node) { sheetStack.push(node); sheetBody.replaceChildren(node); sheet.hidden = false; document.body.style.overflow = 'hidden'; $('.sheet-panel').scrollTop = 0; }
  function closeSheet() {
    sheetStack.pop();
    if (sheetStack.length) { sheetBody.replaceChildren(sheetStack[sheetStack.length - 1]); return; }
    sheet.hidden = true; sheetBody.replaceChildren(); document.body.style.overflow = '';
  }
  sheet.addEventListener('click', (e) => { if (e.target.dataset.close !== undefined) closeSheet(); });
  let toastT; function toast(msg) { const t = $('#toast'); t.textContent = msg; t.hidden = false; clearTimeout(toastT); toastT = setTimeout(() => { t.hidden = true; }, 2600); }

  function pickList({ title, items, groups, selected, onPick, placeholder }) {
    // items: [{key,label,sub,group}] ; groups: ordered group names (others follow alphabetically)
    const q = h('input', { type: 'search', class: 'input', placeholder: placeholder || 'Search…', autocomplete: 'off', autocorrect: 'off', spellcheck: 'false' });
    const list = h('div', { class: 'list' });
    const draw = () => {
      const needle = q.value.trim().toLowerCase(); const toks = needle.split(/\s+/).filter(Boolean);
      const hit = (it) => !toks.length || toks.every((t) => `${it.key} ${it.label} ${it.sub || ''}`.toLowerCase().includes(t));
      const rows = items.filter(hit);
      list.replaceChildren();
      const byGroup = new Map();
      for (const it of rows) { const g = needle ? 'Results' : (it.group || 'All'); if (!byGroup.has(g)) byGroup.set(g, []); byGroup.get(g).push(it); }
      const order = needle ? ['Results'] : [...(groups || []), ...[...byGroup.keys()].filter((g) => !(groups || []).includes(g)).sort()];
      let n = 0;
      for (const g of order) {
        const its = byGroup.get(g); if (!its || !its.length) continue;
        list.append(h('div', { class: 'group' }, g));
        for (const it of its.slice(0, 200)) {
          n++;
          list.append(h('button', { class: 'item' + (it.key === selected ? ' sel' : ''), type: 'button', onclick: () => { onPick(it.key); closeSheet(); } },
            h('span', { class: 'code' }, it.key), h('span', { class: 'name' }, it.label, it.sub ? h('div', { class: 'cat' }, it.sub) : null)));
        }
      }
      if (!n) list.append(h('div', { class: 'empty-state' }, 'Nothing matches. Try fewer letters, or the number.'));
    };
    q.addEventListener('input', draw); draw();
    openSheet(h('div', { class: 'stack' }, h('h1', {}, title), q, list, h('button', { class: 'btn block ghost', onclick: closeSheet }, 'Cancel')));
    setTimeout(() => q.focus({ preventScroll: true }), 50);
  }
  const pickJob = (selected, onPick) => pickList({
    title: 'Job', selected, onPick, placeholder: 'Job number or name',
    items: REF.jobs.map((j) => ({ key: j.no, label: j.name, sub: j.client, group: state.recents.jobs.includes(j.no) ? 'Recent' : 'All jobs' })), groups: ['Recent', 'All jobs'],
  });
  const pickCode = (selected, onPick) => pickList({
    title: 'Cost code', selected, onPick, placeholder: 'Code or words, e.g. 2-200 or water pipe',
    items: REF.costCodes.filter((c) => !/-000$/.test(c.code)).map((c) => ({ key: c.code, label: c.desc, sub: c.cat, group: state.recents.codes.includes(c.code) ? 'Recent' : REF.favouriteCodes.includes(c.code) ? 'Common field codes' : c.cat || 'Other' })),
    groups: ['Recent', 'Common field codes', 'Siteworks', 'General Requirements', 'Safety Services', 'Human Resources'],
  });
  const pickUnit = (selected, onPick) => pickList({
    title: 'Equipment unit', selected, onPick, placeholder: 'Unit number or type',
    items: [{ key: '', label: 'No equipment on this line', group: 'Recent' }, ...REF.equipment.map((e) => ({ key: e.unit, label: e.type, group: state.recents.units.includes(e.unit) ? 'Recent' : e.type }))],
    groups: ['Recent', 'Excavator', 'Rock truck', 'Dozer', 'Loader', 'Grader', 'Smooth packer', 'Gravel truck'],
  });

  const stepper = (value, onChange, step = 0.5) => {
    const inp = h('input', { type: 'number', inputmode: 'decimal', step: String(step), min: '0', value: value ? fmtH(value) : '' , placeholder: '0' });
    const set = (v) => { inp.value = v ? fmtH(v) : ''; onChange(v); };
    inp.addEventListener('change', () => set(num(inp.value)));
    return h('div', { class: 'stepper' }, h('button', { type: 'button', onclick: () => set(Math.max(0, num(inp.value) - step)) }, '−'), inp, h('button', { type: 'button', onclick: () => set(num(inp.value) + step) }, '+'));
  };

  // ------------------------------------------------------------------ line editor
  function editLine(day, line) {
    const isNew = !line;
    const l = line ? { ...line } : { id: uid(), job: state.profile.defaultJob || (day.lines.at(-1) || {}).job || '', cc: '', desc: '', reg: 0, ot: 0, dt: 0, unit: (day.lines.at(-1) || {}).unit || '', eq: 0 };
    let eqTouched = !isNew && l.unit && l.eq !== labour(l);
    const jobBtn = h('button', { type: 'button', class: 'picker', onclick: () => pickJob(l.job, (k) => { l.job = k; paint(); }) });
    const ccBtn = h('button', { type: 'button', class: 'picker', onclick: () => pickCode(l.cc, (k) => { l.cc = k; paint(); }) });
    const unitBtn = h('button', { type: 'button', class: 'picker', onclick: () => pickUnit(l.unit, (k) => { l.unit = k; if (k && !eqTouched) l.eq = labour(l) || 0; paint(); }) });
    const eqWrap = h('div');
    const desc = h('textarea', { placeholder: 'What you did, where. e.g. Laying 200 mm PVC water main, Sta 1+00 to 1+60, tie-in at hydrant.', oninput: () => { l.desc = desc.value; } }); desc.value = l.desc;
    const syncEq = () => { if (l.unit && !eqTouched) { l.eq = labour(l); paint(); } };
    const paint = () => {
      jobBtn.replaceChildren(h('span', { class: 'val' + (l.job ? '' : ' empty') }, l.job ? `${l.job}  ${jobName(l.job)}` : 'Pick a job'), h('span', { class: 'chev' }, '›'));
      ccBtn.replaceChildren(h('span', { class: 'val' + (l.cc ? '' : ' empty') }, l.cc ? `${l.cc}  ${codeDesc(l.cc)}` : 'Pick a cost code'), h('span', { class: 'chev' }, '›'));
      unitBtn.replaceChildren(h('span', { class: 'val' + (l.unit ? '' : ' empty') }, l.unit ? `${l.unit}  ${unitType(l.unit)}` : 'No equipment (labour only)'), h('span', { class: 'chev' }, '›'));
      eqWrap.replaceChildren(l.unit ? h('label', { class: 'field' }, h('span', {}, `${l.unit} hours`), stepper(l.eq, (v) => { l.eq = v; eqTouched = true; })) : null);
    };
    paint();
    const saveLine = () => {
      if (!l.job) return toast('Pick a job first');
      if (!l.cc) return toast('Pick a cost code');
      if (!labour(l) && !(l.unit && l.eq)) return toast('Enter some hours');
      if (!l.unit) l.eq = 0;
      const i = day.lines.findIndex((x) => x.id === l.id); if (i >= 0) day.lines[i] = l; else day.lines.push(l);
      remember(state.recents.jobs, l.job); remember(state.recents.codes, l.cc, 12); if (l.unit) remember(state.recents.units, l.unit);
      delete state.sent[day.date]; save(); closeSheet(); render();
    };
    openSheet(h('div', { class: 'stack' },
      h('h1', {}, isNew ? 'Add time' : 'Edit time'),
      h('label', { class: 'field' }, h('span', {}, 'Job'), jobBtn),
      h('label', { class: 'field' }, h('span', {}, 'Cost code'), ccBtn),
      h('div', { class: 'field-label' }, 'Your hours (labour)'),
      h('div', { class: 'grid3' },
        h('label', { class: 'field' }, h('span', {}, 'Regular'), stepper(l.reg, (v) => { l.reg = v; syncEq(); })),
        h('label', { class: 'field' }, h('span', {}, 'Overtime'), stepper(l.ot, (v) => { l.ot = v; syncEq(); })),
        h('label', { class: 'field' }, h('span', {}, 'Double time'), stepper(l.dt, (v) => { l.dt = v; syncEq(); }))),
      h('label', { class: 'field' }, h('span', {}, 'Equipment you ran on this cost code'), unitBtn),
      eqWrap,
      h('label', { class: 'field' }, h('span', {}, 'Description'), desc),
      h('button', { class: 'btn primary block', onclick: saveLine }, isNew ? 'Add to today' : 'Save'),
      isNew ? null : h('button', { class: 'btn block ghost danger', onclick: () => { day.lines = day.lines.filter((x) => x.id !== l.id); delete state.sent[day.date]; save(); closeSheet(); render(); } }, 'Remove this line'),
      h('button', { class: 'btn block ghost', onclick: closeSheet }, 'Cancel')));
  }

  // ------------------------------------------------------------------ views
  function viewDay() {
    const d = getDay(ui.date); const t = dayHours(d); const probs = problems(d); const pe = periodEnd(ui.date);
    const dateInp = h('input', { type: 'date', value: ui.date, onchange: () => { if (dateInp.value) { ui.date = dateInp.value; render(); } } });
    const lines = d.lines.length ? d.lines.map((l) => h('div', { class: 'line', role: 'button', tabindex: '0', onclick: () => editLine(d, l) },
      h('div', {}, h('div', { class: 'job' }, `${l.job} ${jobName(l.job)}`), h('div', { class: 'cc' }, `${l.cc} ${codeDesc(l.cc)}`)),
      h('div', {}, h('div', { class: 'hrs' }, `${fmtH(labour(l))} h`, l.ot || l.dt ? h('div', { class: 'small muted' }, [l.ot ? `${fmtH(l.ot)} OT` : '', l.dt ? `${fmtH(l.dt)} DT` : ''].filter(Boolean).join(' · ')) : null),
        l.unit ? h('div', { class: 'eq' }, `${l.unit} · ${fmtH(l.eq)} h`) : null),
      l.desc ? h('div', { class: 'desc' }, l.desc) : null))
      : [h('div', { class: 'empty-state' }, h('div', { class: 'big' }, '⏱'), h('div', {}, 'No time on this day yet.'), h('div', { class: 'small' }, 'Add a line for each job and cost code you worked. Equipment hours go on the same line as the labour that ran it.'))];
    const sentAt = state.sent[ui.date];
    return h('div', {},
      h('div', { class: 'daynav' },
        h('button', { class: 'btn', onclick: () => { ui.date = addDays(ui.date, -1); render(); } }, '‹'),
        dateInp,
        h('button', { class: 'btn', onclick: () => { ui.date = addDays(ui.date, 1); render(); } }, '›')),
      h('div', { class: 'card row between' },
        h('div', {}, h('div', { class: 'total' }, fmtH(t.reg + t.ot + t.dt), h('small', {}, ' h labour')), h('div', { class: 'small muted' }, `Reg ${fmtH(t.reg)} · OT ${fmtH(t.ot)} · DT ${fmtH(t.dt)}`)),
        h('div', { style: 'text-align:right' }, h('div', { class: 'total' }, fmtH(t.eq), h('small', {}, ' h equip')), h('div', { class: 'small muted' }, `Pay period ends ${fmt(pe)}`))),
      h('div', { class: 'card' }, ...lines, h('button', { class: 'btn dark block', style: 'margin-top:10px', onclick: () => editLine(d) }, '+ Add job / cost code line')),
      h('div', { class: 'card stack' },
        h('div', { class: 'field-label' }, 'Allowances for the day'),
        h('div', { class: 'chips' },
          h('button', { class: 'chip' + (d.loa ? ' on' : ''), onclick: () => { d.loa = !d.loa; delete state.sent[d.date]; save(); render(); } }, `LOA  $${REF.allowances.loa}`),
          h('button', { class: 'chip' + (d.pu ? ' on' : ''), onclick: () => { d.pu = !d.pu; delete state.sent[d.date]; save(); render(); } }, `Own truck (P/U)  $${REF.allowances.pickup}`)),
        h('div', { class: 'grid2' },
          h('label', { class: 'field' }, h('span', {}, `Travel km  ($${REF.allowances.travelKm}/km)`), h('input', { type: 'number', inputmode: 'decimal', min: '0', step: '1', value: d.km || '', placeholder: '0', onchange: (e) => { d.km = Math.max(0, parseFloat(e.target.value) || 0); delete state.sent[d.date]; save(); } })),
          h('div')),
        h('label', { class: 'field' }, h('span', {}, 'Notes for the office (optional)'), (() => { const ta = h('textarea', { placeholder: 'Rain day, waiting on materials, first aid, breakdown…', oninput: (e) => { d.notes = e.target.value; delete state.sent[d.date]; save(); } }); ta.value = d.notes || ''; return ta; })())),
      h('div', { class: 'card stack' },
        h('div', { class: 'row between' }, h('div', { class: 'field-label', style: 'margin:0' }, 'Send today\'s card'),
          sentAt ? h('span', { class: 'tag ok' }, `sent ${new Date(sentAt).toLocaleString('en-CA', { month: 'short', day: 'numeric', hour: 'numeric', minute: '2-digit' })}`) : null),
        ...probs.map((p) => h('div', { class: /Check it|more hours/.test(p) ? 'warn-text' : 'bad-text' }, p)),
        h('div', { class: 'grid2' },
          h('button', { class: 'btn primary', disabled: probs.some((p) => !/Check it|more hours/.test(p)), onclick: () => send([d], 'email') }, '✉ Email'),
          h('button', { class: 'btn', disabled: probs.some((p) => !/Check it|more hours/.test(p)), onclick: () => send([d], navigator.share ? 'share' : 'copy') }, navigator.share ? '⇪ Share' : '⎘ Copy')),
        h('div', { class: 'small muted' }, `Goes to ${state.profile.submitTo || REF.submitTo}. You can send one day at a time, or the whole pay period from the Pay period tab.`)));
  }

  function viewPeriod() {
    const pe = periodEnd(ui.date); const days = periodDays(pe); const today = todayISO();
    const worked = days.map((iso) => state.days[iso]).filter(hasWork);
    const sum = new Map(); let reg = 0, ot = 0, dt = 0, eq = 0, loa = 0, pu = 0, km = 0;
    for (const d of worked) {
      const t = dayHours(d); reg += t.reg; ot += t.ot; dt += t.dt; eq += t.eq; loa += d.loa ? 1 : 0; pu += d.pu ? 1 : 0; km += d.km || 0;
      for (const l of d.lines) { const k = `${l.job}|${l.cc}`; const s = sum.get(k) || { job: l.job, cc: l.cc, lab: 0, eq: 0, units: new Set() }; s.lab += labour(l); if (l.unit) { s.eq += l.eq; s.units.add(l.unit); } sum.set(k, s); }
    }
    const allSent = worked.length && worked.every((d) => state.sent[d.date]);
    const probs = worked.flatMap((d) => problems(d).filter((p) => !/Check it|more hours/.test(p)).map((p) => `${fmt(d.date)}: ${p}`));
    return h('div', {},
      h('div', { class: 'card' },
        h('div', { class: 'row between' },
          h('button', { class: 'btn sm', onclick: () => { ui.date = addDays(pe, -REF.payPeriod.days); render(); } }, '‹ prev'),
          h('div', { style: 'text-align:center' }, h('h1', {}, `${fmt(days[0], { month: 'short', day: 'numeric' })} – ${fmt(pe, { month: 'short', day: 'numeric' })}`), h('div', { class: 'small muted' }, `Pay period ends Sat ${fmt(pe, { month: 'short', day: 'numeric' })}`)),
          h('button', { class: 'btn sm', onclick: () => { ui.date = addDays(pe, REF.payPeriod.days); render(); } }, 'next ›')),
        h('div', { class: 'period-grid', style: 'margin-top:12px' }, ...days.map((iso) => {
          const d = state.days[iso]; const t = d ? dayHours(d) : null; const lab = t ? t.reg + t.ot + t.dt : 0;
          return h('button', { class: 'pday' + (iso === today ? ' today' : '') + (hasWork(d) ? '' : ' empty') + (state.sent[iso] ? ' sent' : ''), onclick: () => { ui.date = iso; ui.tab = 'day'; render(); } },
            h('div', { class: 'd' }, fmt(iso, { weekday: 'short' })), h('div', { class: 'n' }, parseISO(iso).getDate()), h('div', { class: 'h' }, lab ? fmtH(lab) : (d && (d.loa || d.pu || d.km) ? '·' : '')));
        }))),
      h('div', { class: 'card' },
        h('div', { class: 'row between' }, h('div', {}, h('div', { class: 'total' }, fmtH(reg + ot + dt), h('small', {}, ' h labour')), h('div', { class: 'small muted' }, `Reg ${fmtH(reg)} · OT ${fmtH(ot)} · DT ${fmtH(dt)}`)),
          h('div', { style: 'text-align:right' }, h('div', { class: 'total' }, fmtH(eq), h('small', {}, ' h equip')), h('div', { class: 'small muted' }, `LOA ${loa} · P/U ${pu} · ${km} km`))),
        sum.size ? h('table', { class: 'sum', style: 'margin-top:10px' }, h('thead', {}, h('tr', {}, h('th', {}, 'Job / cost code'), h('th', { class: 'num' }, 'Labour'), h('th', { class: 'num' }, 'Equip'))),
          h('tbody', {}, ...[...sum.values()].sort((a, b) => a.job.localeCompare(b.job) || a.cc.localeCompare(b.cc)).map((s) => h('tr', {},
            h('td', {}, h('div', {}, h('b', {}, s.job), ' ', jobName(s.job)), h('div', { class: 'small muted' }, `${s.cc} ${codeDesc(s.cc)}`)),
            h('td', { class: 'num' }, fmtH(s.lab)), h('td', { class: 'num' }, s.eq ? h('span', {}, fmtH(s.eq), h('div', { class: 'small muted' }, [...s.units].join(', '))) : '–')))))
          : h('div', { class: 'empty-state small' }, 'No time in this pay period yet.')),
      h('div', { class: 'card stack' },
        h('div', { class: 'row between' }, h('div', { class: 'field-label', style: 'margin:0' }, 'Send the whole pay period'), allSent ? h('span', { class: 'tag ok' }, 'all days sent') : null),
        ...probs.map((p) => h('div', { class: 'bad-text' }, p)),
        h('div', { class: 'grid2' },
          h('button', { class: 'btn primary', disabled: !worked.length || probs.length > 0, onclick: () => send(worked, 'email') }, '✉ Email period'),
          h('button', { class: 'btn', disabled: !worked.length || probs.length > 0, onclick: () => send(worked, navigator.share ? 'share' : 'copy') }, navigator.share ? '⇪ Share' : '⎘ Copy')),
        h('button', { class: 'btn block ghost', disabled: !worked.length, onclick: () => openSheet(h('div', {}, h('h1', {}, 'What the office receives'), h('pre', { class: 'preview' }, buildText(worked)), h('button', { class: 'btn block', onclick: closeSheet }, 'Close'))) }, 'Preview'),
        h('div', { class: 'small muted' }, 'Same as the paper weekly timesheet, plus the job, cost code and equipment split the office needs for job costing. Send by the deadline on the Employee Resources page.')));
  }

  function viewSettings() {
    const p = state.profile;
    const field = (label, key, attrs = {}) => h('label', { class: 'field' }, h('span', {}, label), h('input', Object.assign({ type: 'text', value: p[key] || '', onchange: (e) => { p[key] = e.target.value.trim(); save(); renderWho(); } }, attrs)));
    const jobBtn = h('button', { type: 'button', class: 'picker', onclick: () => pickJob(p.defaultJob, (k) => { p.defaultJob = k; save(); render(); }) },
      h('span', { class: 'val' + (p.defaultJob ? '' : ' empty') }, p.defaultJob ? `${p.defaultJob}  ${jobName(p.defaultJob)}` : 'Optional: the job you are usually on'), h('span', { class: 'chev' }, '›'));
    const standalone = window.matchMedia('(display-mode: standalone)').matches || navigator.standalone;
    const isiOS = /iphone|ipad|ipod/i.test(navigator.userAgent);
    return h('div', {},
      h('div', { class: 'card' }, h('h1', {}, 'About you'),
        field('Your name (as on your paycheque)', 'name', { autocomplete: 'name' }),
        field('Position', 'position', { placeholder: 'Operator, Labourer, Foreman…' }),
        field('Supervisor / foreman', 'supervisor'),
        h('label', { class: 'field' }, h('span', {}, 'Default job'), jobBtn),
        field('Send timecards to', 'submitTo', { type: 'email', placeholder: REF.submitTo, inputmode: 'email' })),
      standalone ? null : h('div', { class: 'card' }, h('h1', {}, 'Put it on your home screen'),
        isiOS ? h('div', { class: 'small' }, 'In Safari tap the ', h('b', {}, 'Share'), ' button, then ', h('b', {}, 'Add to Home Screen'), '. It opens like an app and works with no signal.')
          : h('div', { class: 'small' }, 'In Chrome tap the ', h('b', {}, '⋮ menu'), ', then ', h('b', {}, 'Add to Home screen'), ' (or "Install app"). It opens like an app and works with no signal.')),
      h('div', { class: 'card stack' }, h('h1', {}, 'Lists'),
        h('div', { class: 'small muted' }, `${REF.jobs.length} jobs · ${REF.costCodes.length} cost codes · ${REF.equipment.length} units · list version ${REF.version}`),
        h('button', { class: 'btn block', onclick: () => loadRef(true) }, 'Refresh job, cost code and equipment lists')),
      h('div', { class: 'card stack' }, h('h1', {}, 'Your data'),
        h('div', { class: 'small muted' }, `${Object.values(state.days).filter(hasWork).length} days on this phone. Nothing leaves the phone until you send it.`),
        h('button', { class: 'btn block', onclick: async () => { const txt = JSON.stringify(state); try { await navigator.clipboard.writeText(txt); toast('Backup copied. Paste it somewhere safe (a note, an email to yourself).'); } catch (e) { openSheet(h('div', {}, h('h1', {}, 'Backup'), h('pre', { class: 'preview' }, txt))); } } }, 'Copy a backup'),
        h('button', { class: 'btn block', onclick: () => { const ta = h('textarea', { placeholder: 'Paste a backup here' }); openSheet(h('div', { class: 'stack' }, h('h1', {}, 'Restore a backup'), ta, h('button', { class: 'btn primary block', onclick: () => { try { const s = JSON.parse(ta.value); if (!s.days) throw 0; state = Object.assign(blank(), s); save(); closeSheet(); render(); toast('Restored'); } catch (e) { toast('That is not a RAM Timecard backup'); } } }, 'Restore'))); } }, 'Restore a backup'),
        h('button', { class: 'btn block ghost danger', onclick: () => { if (confirm('Delete every day on this phone? Sent cards are already with the office.')) { state = Object.assign(blank(), { profile: state.profile }); save(); render(); } } }, 'Clear all days')),
      h('div', { class: 'small muted', style: 'text-align:center;padding:8px' }, 'RAM Excavating Limited · 1346 Winword Rd, Quesnel BC'));
  }

  // ------------------------------------------------------------------ shell
  const renderWho = () => { $('#who').textContent = state.profile.name || 'Set your name under Me'; };
  function render() {
    if (!REF) return;
    document.querySelectorAll('#tabs button').forEach((b) => b.classList.toggle('active', b.dataset.tab === ui.tab));
    const v = ui.tab === 'day' ? viewDay() : ui.tab === 'period' ? viewPeriod() : viewSettings();
    $('#view').replaceChildren(v); renderWho();
  }
  $('#tabs').addEventListener('click', (e) => { const b = e.target.closest('button'); if (!b) return; ui.tab = b.dataset.tab; render(); window.scrollTo(0, 0); });

  async function loadRef(force) {
    try {
      const r = await fetch('data/reference.json' + (force ? '?t=' + Date.now() : ''), { cache: force ? 'reload' : 'default' });
      if (!r.ok) throw new Error(r.status);
      REF = await r.json(); localStorage.setItem(REF_CACHE, JSON.stringify(REF));
      if (force) toast(`Lists updated (${REF.version})`);
    } catch (e) {
      const cached = localStorage.getItem(REF_CACHE);
      if (cached) { REF = JSON.parse(cached); if (force) toast('No signal. Using the last lists you had.'); }
      else { $('#view').replaceChildren(h('div', { class: 'empty-state' }, 'Could not load the job and cost code lists. Connect to the internet once and reopen.')); return; }
    }
    if (!state.profile.name && ui.tab === 'day' && !Object.keys(state.days).length) ui.tab = 'settings';
    render();
  }
  if ('serviceWorker' in navigator) navigator.serviceWorker.register('sw.js').catch(() => {});
  loadRef(false);
})();
