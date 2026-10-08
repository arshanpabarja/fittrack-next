/* Coach workspace. Client records stay in memory; only theme preference is persisted. */
(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const main = $('#workspace-content');
  const dialog = $('#editor-dialog');
  const state = { data: null, library: [], detail: null, session: null, route: 0, search: '', filter: 'all', page: 1, dirty: false };
  const goals = { muscle_gain: 'افزایش عضله', fat_loss: 'کاهش چربی', strength: 'افزایش قدرت', recomposition: 'بازترکیب بدنی', fitness: 'آمادگی عمومی' };
  const muscles = { chest: 'سینه', back: 'پشت', shoulders: 'شانه', arms: 'بازو', legs: 'پا', core: 'میان‌تنه', full_body: 'تمام بدن' };
  const weekdays = { saturday: 'شنبه', sunday: 'یکشنبه', monday: 'دوشنبه', tuesday: 'سه‌شنبه', wednesday: 'چهارشنبه', thursday: 'پنج‌شنبه', friday: 'جمعه' };
  const statuses = { scheduled: ['برنامه‌ریزی‌شده', 'info'], in_progress: ['در حال تمرین', 'warning'], completed: ['انجام‌شده', 'success'], cancelled: ['لغوشده', ''], no_show: ['عدم حضور', 'danger'] };
  const membership = { active: ['فعال', 'success'], expiring: ['نزدیک به پایان', 'warning'], expired: ['پایان‌یافته', 'danger'] };
  const views = { dashboard: 'نمای کلی', clients: 'ورزشکاران من', programs: 'برنامه‌های تمرینی', sessions: 'جلسات تمرین', library: 'کتابخانه حرکات', performance: 'عملکرد من', profile: 'پروفایل من' };
  const fa = (value) => String(value ?? 'ثبت نشده').replace(/\d/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);
  const e = (value) => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const icon = (name) => `<img src="/assets/icons/${name}.svg" alt="" />`;
  const initials = (name) => String(name).split(/\s+/).filter(Boolean).slice(0, 2).map(s => s[0]).join('');
  const avatar = (name, id = 0) => `<span class="avatar tone-${id % 5}" aria-hidden="true">${e(initials(name))}</span>`;
  const badge = (label, tone = '') => `<span class="badge ${tone}">${e(label)}</span>`;
  const sessionBadge = (status) => badge(...(statuses[status] || [status, '']));
  const memberBadge = (status) => badge(...(membership[status] || ['نامشخص', '']));
  const btn = (label, action, id = '', style = '', symbol = '') => `<button type="button" class="button ${style}" data-action="${action}" data-id="${e(id)}">${symbol ? icon(symbol) : ''}${label}</button>`;
  const link = (label, hash, style = 'text-button') => `<a class="button ${style}" href="#${e(hash)}">${label}</a>`;
  const dateText = (value, long = false) => {
    if (!value) return 'ثبت نشده';
    const match = String(value).match(/^(1[34]\d{2})[-_/](\d\d)[-_/](\d\d)/);
    if (match) return fa(`${match[1]}/${match[2]}/${match[3]}`);
    const d = new Date(value);
    return Number.isNaN(d.getTime()) ? 'نامشخص' : new Intl.DateTimeFormat('fa-IR', { timeZone: 'Asia/Tehran', ...(long ? { weekday: 'long', month: 'long', day: 'numeric' } : { year: 'numeric', month: 'short', day: 'numeric' }) }).format(d);
  };
  const timeText = (value) => new Intl.DateTimeFormat('fa-IR', { timeZone: 'Asia/Tehran', hour: '2-digit', minute: '2-digit', hour12: false }).format(new Date(value));
  const shiftDate = (value, count) => { const d = new Date(`${value}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + count); return d.toISOString().slice(0, 10); };
  const getClient = (id) => state.data.clients.find(c => c.id === Number(id));
  let toastTimer, dialogSubmit, librarySearch = '', libraryMuscle = 'all';

  async function api(path, options = {}) {
    const method = options.method || 'GET';
    const token = document.cookie.split('; ').find(s => s.startsWith('csrftoken='))?.slice(10);
    const response = await fetch(path, { credentials: 'same-origin', ...options, headers: { 'Content-Type': 'application/json', ...(method !== 'GET' && token ? { 'X-CSRFToken': decodeURIComponent(token) } : {}) }, ...(options.body ? { body: JSON.stringify(options.body) } : {}) });
    let result;
    try { result = await response.json(); } catch { throw new Error('پاسخ سرور قابل خواندن نیست. دوباره تلاش کنید.'); }
    if (!response.ok) {
      if (response.status === 403) {
        const session = await fetch('/api/me', { credentials: 'same-origin' });
        if (!session.ok) location.replace('/login');
      }
      throw new Error(result.message || 'درخواست انجام نشد.');
    }
    return result;
  }
  function toast(message, error = false) { const box = $('#toast'); box.textContent = message; box.classList.toggle('error', error); box.hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { box.hidden = true; }, 5000); }
  function heading(title, subtitle = '', actions = '') { return `<div class="page-heading"><div><h1>${e(title)}</h1>${subtitle ? `<p>${e(subtitle)}</p>` : ''}</div><div class="heading-actions">${actions}</div></div>`; }
  function empty(title, subtitle = '', action = '') { return `<div class="empty-state">${icon('clipboard-list')}<h3>${e(title)}</h3><p>${e(subtitle)}</p>${action}</div>`; }
  function panel(title, content, action = '', subtitle = '') { return `<section class="panel"><div class="panel-header"><div><h2>${e(title)}</h2>${subtitle ? `<p>${e(subtitle)}</p>` : ''}</div>${action}</div>${content}</section>`; }
  function metric(label, value, symbol, foot) { return `<article class="metric"><div class="metric-top"><span>${e(label)}</span><span class="metric-icon">${icon(symbol)}</span></div><div class="metric-value">${fa(value)}</div><div class="metric-foot">${foot}</div></article>`; }
  function person(client) { return `<button class="person-link person-cell" data-action="client" data-id="${client.id}">${avatar(client.fullName, client.id)}<span><strong>${e(client.fullName)}</strong><small>${e(goals[client.mainGoal] || 'هدف هنوز ثبت نشده')}</small></span></button>`; }
  function renderHeader() {
    const data = state.data;
    $('#coach-name').textContent = data.coach.fullName || 'مربی لایف‌باکس';
    $('#coach-specialty').textContent = data.coach.specialty || 'تخصص ثبت نشده';
    $('#coach-initials').textContent = initials(data.coach.fullName || 'مربی');
    $('#nav-client-count').textContent = fa(data.clients.length);
    const count = data.metrics.followUps;
    $('#notification-dot').hidden = count === 0;
  }
  async function refresh() { state.data = await api('/api/coach/workspace'); renderHeader(); }
  function clientsTable(clients, full = false) {
    if (!clients.length) return empty('ورزشکاری پیدا نشد', state.data.clients.length ? 'فیلتر یا عبارت جستجو را تغییر دهید.' : 'اعضای فعال پلن‌های مجاز شما اینجا نمایش داده می‌شوند.');
    return `<div class="table-scroll"><table class="data-table"><thead><tr><th>ورزشکار</th>${full ? '<th>سن / جنسیت</th>' : ''}<th>پلن عضویت</th><th>وضعیت</th><th>جلسات</th><th>آخرین حضور</th><th>برنامه فعلی</th>${full ? '<th>نیاز به توجه</th>' : ''}<th></th></tr></thead><tbody>${clients.map(c => `<tr><td>${person(c)}</td>${full ? `<td>${c.age === null ? 'نامشخص' : fa(c.age)} / ${e({ male: 'مرد', female: 'زن', all: 'ثبت نشده' }[c.gender] || c.gender)}</td>` : ''}<td>${e(c.plan)}</td><td>${memberBadge(c.status)}</td><td><strong>${fa(c.sessionsRemaining ?? 'نامشخص')}</strong> باقی‌مانده<br><small class="muted">${fa(c.sessionsUsed)} استفاده‌شده</small></td><td>${state.data.attendanceAvailable ? dateText(c.lastVisit) : 'داده در دسترس نیست'}</td><td>${e(c.currentProgram?.title || 'ثبت نشده')}</td>${full ? `<td>${c.alerts.length ? badge(c.alerts[0].message, c.alerts[0].severity) : badge('به‌روز', 'success')}</td>` : ''}<td>${btn('پروفایل', 'client', c.id, 'text-button')}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function dashboard() {
    const d = state.data, m = d.metrics;
    const name = d.coach.fullName?.split(' ')[0];
    const today = `<span class="date-chip">${icon('calendar')}${dateText(d.today + 'T12:00:00+03:30', true)}</span>`;
    main.innerHTML = heading(name ? `${name}، روزت بخیر` : 'روزت بخیر، مربی', 'ورزشکاران و تمرین‌های امروز را یکجا ببین.', today + btn('ساخت برنامه', 'program', '', 'primary', 'plus')) +
      `<div class="metric-grid">${metric('ورزشکاران فعال', m.activeClients, 'users', link('مشاهده ورزشکاران', 'clients'))}${metric('ورزشکاران امروز', m.trainingToday, 'barbell', link('ورزشکاران امروز', 'clients?filter=today'))}${metric('جلسات امروز', m.sessionsToday, 'calendar', `${fa(d.todaySessions.filter(s => s.status === 'completed').length)} جلسه انجام شده`)}${metric('برنامه‌های نیازمند تغییر', m.programsDue, 'clipboard-list', link('بررسی برنامه‌ها', 'clients?filter=program'))}</div>` +
      panel('ورزشکاران من', clientsTable(d.clients.slice(0, 5)) + `<div class="table-footer"><span>${fa(Math.min(5, d.clients.length))} از ${fa(d.clients.length)} ورزشکار</span><span>${d.attendanceAvailable ? 'حضور از دستگاه باشگاه دریافت می‌شود' : 'اطلاعات دستگاه حضور در دسترس نیست'}</span></div>`, link('مشاهده همه ←', 'clients'));
  }
  const filters = { all: 'همه ورزشکاران', active: 'فعال', new: 'جدید', private: 'خصوصی', semi_private: 'نیمه‌خصوصی', muscle_gain: 'افزایش عضله', fat_loss: 'کاهش چربی', strength: 'قدرت', program: 'نیاز به برنامه', low: 'جلسات کم', inactive: 'حضور نامنظم', followup: 'نیاز به پیگیری', today: 'تمرین امروز' };
  function filteredClients() {
    return state.data.clients.filter(c => {
      const f = state.filter;
      const matches = f === 'all' || (f === 'active' && c.status !== 'expired') || (f === 'new' && c.isNew) || c.trainingStyle === f || c.mainGoal === f || c.alerts.some(a => a.kind === ({ low: 'low_sessions' }[f] || f)) || (f === 'followup' && c.alerts.some(a => ['inactive', 'attendance_drop'].includes(a.kind))) || (f === 'today' && state.data.todaySessions.some(s => s.memberId === c.id && !['cancelled', 'no_show'].includes(s.status)));
      return matches && `${c.fullName} ${c.plan} ${c.currentProgram?.title || ''}`.toLocaleLowerCase('fa').includes(state.search.toLocaleLowerCase('fa'));
    });
  }
  function renderClientResults() {
    const rows = filteredClients(), pages = Math.max(1, Math.ceil(rows.length / 15)); state.page = Math.min(state.page, pages);
    $('#client-results').innerHTML = clientsTable(rows.slice((state.page - 1) * 15, state.page * 15), true) + `<div class="table-footer"><span>${fa(rows.length)} ورزشکار</span><div>${btn('قبلی', 'prev-clients', '', 'compact')} <span>${fa(state.page)} / ${fa(pages)}</span> ${btn('بعدی', 'next-clients', '', 'compact')}</div></div>`;
    $$('[data-filter]').forEach(b => { b.classList.toggle('active', b.dataset.filter === state.filter); b.setAttribute('aria-pressed', String(b.dataset.filter === state.filter)); });
  }
  function clientsView() {
    main.innerHTML = heading('ورزشکاران من', 'تمرین هر ورزشکار را بشناس و قدم بعدی را مشخص کن.', btn('ساخت برنامه', 'program', '', 'primary', 'plus')) + `<div class="toolbar"><input type="search" id="client-search" placeholder="جستجوی نام، پلن یا برنامه..." aria-label="جستجوی ورزشکار" value="${e(state.search)}" /><span class="muted">${fa(state.data.clients.length)} ورزشکار در پلن‌های مجاز شما</span></div><div class="filters">${Object.entries(filters).map(([key, label]) => `<button class="filter-button" data-filter="${key}" aria-pressed="false">${label}</button>`).join('')}</div><section class="panel" id="client-results"></section>`;
    renderClientResults();
    $('#client-search').addEventListener('input', ev => { state.search = ev.target.value; state.page = 1; renderClientResults(); });
  }
  function facts(entries) { return `<dl class="profile-facts">${entries.map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join('')}</dl>`; }
  const tabs = { overview: 'نمای کلی', program: 'برنامه تمرینی', sessions: 'جلسات', attendance: 'حضور در باشگاه' };
  function clientView(detail, tab) {
    const c = detail.client;
    main.innerHTML = `<div class="page-heading"><div class="client-heading">${avatar(c.fullName, c.id)}<div><h1>${e(c.fullName)}</h1><p>${e(c.plan)} · ${e(goals[c.mainGoal] || 'هدف ثبت نشده')}</p></div></div><div class="heading-actions">${link('ورزشکاران من', 'clients')}</div></div>` +
      panel('اطلاعات عضویت', `<div class="panel-body">${facts([['وضعیت عضویت', memberBadge(c.status)], ['جلسات استفاده‌شده', fa(c.sessionsUsed)], ['جلسات باقی‌مانده', fa(c.sessionsRemaining ?? 'نامشخص')], ['آخرین حضور', detail.attendanceAvailable ? dateText(c.lastVisit) : 'داده در دسترس نیست'], ['سن / جنسیت', `${fa(c.age ?? 'ثبت نشده')} / ${e({ male: 'مرد', female: 'زن', all: 'نامشخص' }[c.gender] || c.gender)}`], ['شروع عضویت', dateText(c.membershipStart)], ['پایان عضویت', dateText(c.expiresAt)], ['ثبت چهره', c.faceRegistered ? badge('ثبت شده', 'success') : badge('ثبت نشده', 'warning')]])}<div class="alert-list">${c.alerts.map(a => badge(a.message, a.severity)).join('')}</div></div>`) +
      `<div class="profile-tabs" role="tablist" aria-label="بخش‌های پروفایل">${Object.entries(tabs).map(([key, label]) => `<button role="tab" aria-selected="${key === tab}" class="${key === tab ? 'active' : ''}" data-action="client-tab" data-id="${key}" id="tab-${key}" aria-controls="client-tab-panel">${label}</button>`).join('')}</div><div id="client-tab-panel" role="tabpanel" aria-labelledby="tab-${e(tab)}"></div>`;
    const content = $('#client-tab-panel');
    if (tab === 'overview') content.innerHTML = panel('برنامه فعلی', c.currentProgram ? `<div class="panel-body"><h2>${e(c.currentProgram.title)}</h2><p class="muted">${fa(c.currentProgram.days.length)} روز تمرین در هفته · تا ${dateText(c.currentProgram.endDate)}</p><div class="quick-actions">${btn('مشاهده برنامه', 'client-tab', 'program')}${btn('ویرایش برنامه', 'program', c.id, 'primary')}</div></div>` : empty('برنامه‌ای ثبت نشده', 'برای ورزشکار برنامه تمرینی بساز.', btn('ساخت برنامه', 'program', c.id, 'primary')));
    if (tab === 'program') content.innerHTML = panel('برنامه تمرینی فعلی', c.currentProgram ? `<div class="panel-body">${programMarkup(c.currentProgram)}</div><div class="card-footer">${btn('ویرایش', 'program', c.id)}${btn('نسخه برای ورزشکار دیگر', 'duplicate', c.id)}${btn('بایگانی', 'archive', c.currentProgram.id, 'danger')}</div>` : empty('برنامه فعالی وجود ندارد', '', btn('ساخت برنامه', 'program', c.id, 'primary')), btn('جایگزینی برنامه', 'program-new', c.id, 'primary')) + `<div class="detail-section" style="margin-top:22px">${panel('تاریخچه برنامه‌ها', detail.programHistory.length ? `<div class="panel-body">${detail.programHistory.map((r, index) => `<div class="history-row"><div class="history-meta">${dateText(r.savedAt)} ${r.program.archived ? badge('بایگانی') : badge('نسخه پیشین')}</div><h3>${e(r.program.title)}</h3>${btn('مشاهده نسخه', 'history', index, 'text-button')}</div>`).join('')}</div>` : empty('هنوز نسخه پیشینی وجود ندارد', 'هنگام ویرایش یا جایگزینی، نسخه قبلی حفظ می‌شود.'))}</div>`;
    if (tab === 'sessions') content.innerHTML = panel('جلسات تمرینی', sessionTable(detail.sessions)) + `<div class="detail-section" style="margin-top:22px">${panel('نتایج تمرین ثبت‌شده توسط عضو', detail.workouts?.length ? `<div class="panel-body">${detail.workouts.map(w => `<details class="history-row"><summary><strong>${e(w.trainingDay)}</strong> | ${dateText(w.finishedAt)}</summary><p class="muted">${e(w.programTitle)}</p>${w.exercises.map(x => `<div class="history-row"><h3>${e(x.name)}</h3><p>${x.skipped ? 'ردشده' : x.sets.map((s, i) => `ست ${fa(i + 1)}: ${s.complete ? `${fa(s.weight)} kg × ${fa(s.reps)}` : 'نتیجه ثبت نشده'}`).join(' / ')}</p></div>`).join('')}</details>`).join('')}</div>` : empty('هنوز تمرینی ثبت نشده', 'نتایج تمرین عضو پس از پایان تمرین اینجا نمایش داده می‌شود.'))}</div>`;
    if (tab === 'attendance') content.innerHTML = panel('حضور در باشگاه', attendanceMarkup(detail), badge(fa(detail.visitCount) + ' ورود'), 'اطلاعات از دستگاه باشگاه دریافت می‌شود. ورود به باشگاه با جلسه تمرین متفاوت است.');
    $$('[role=tab]').forEach(button => button.addEventListener('keydown', ev => {
      if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(ev.key)) {
        ev.preventDefault(); const all = $$('[role=tab]'); const index = all.indexOf(button); const next = ev.key === 'Home' ? 0 : ev.key === 'End' ? all.length - 1 : (index + (ev.key === 'ArrowLeft' ? 1 : -1) + all.length) % all.length;
        all[next].focus();
      }
    }));
  }
  function programMarkup(p) {
    return `<h2>${e(p.title)}</h2><p class="muted">${e(goals[p.mainGoal] || 'هدف ثبت نشده')} · ${dateText(p.startDate)} تا ${dateText(p.endDate)} · ${fa(p.durationWeeks)} هفته</p><div style="margin-top:20px">${p.days.map(d => `<section class="day-panel"><div class="day-heading"><h3>${e(d.label)}</h3>${badge(weekdays[d.weekday] || 'روز نامشخص')}</div><div class="table-scroll"><table class="workout-table"><thead><tr><th>حرکت</th><th>ست × تکرار</th></tr></thead><tbody>${d.exercises?.length ? d.exercises.map(x => `<tr><td>${e(x.name)}</td><td dir="ltr">${fa(x.sets)} × ${fa(x.reps)}</td></tr>`).join('') : (d.movements || []).map(m => `<tr><td colspan="2">${e(m)}</td></tr>`).join('')}</tbody></table></div></section>`).join('')}</div>`;
  }
  function attendanceMarkup(detail) {
    if (!detail.attendanceAvailable) return empty('داده حضور در دسترس نیست', 'پس از اتصال یا همگام‌سازی دستگاه، حضور خودکار نمایش داده می‌شود.');
    if (!detail.attendance.length) return empty('حضوری ثبت نشده', 'برای این ورزشکار هنوز سابقه‌ای از دستگاه دریافت نشده است.');
    return `<div class="table-scroll"><table class="data-table"><thead><tr><th>تاریخ</th><th>ورود</th><th>خروج</th></tr></thead><tbody>${detail.attendance.map(v => `<tr><td>${dateText(v.checkIn)}</td><td>${e(fa(String(v.checkIn).slice(11, 16)))}</td><td>${v.checkOut ? e(fa(String(v.checkOut).slice(11, 16))) : 'خروج ثبت نشده'}</td></tr>`).join('')}</tbody></table></div><div class="table-footer">${fa(detail.attendance.length)} رکورد اخیر از ${fa(detail.visitCount)} حضور</div>`;
  }
  function sessionTable(sessions) {
    if (!sessions.length) return empty('جلسه‌ای در این بازه نیست', 'سوابق تمرین‌های قبلی اینجا نمایش داده می‌شود.');
    return `<div class="table-scroll"><table class="data-table"><thead><tr><th>ورزشکار</th><th>زمان جلسه</th><th>برنامه / روز تمرین</th><th>حرکت‌های انجام‌شده</th><th>وضعیت</th><th>عملیات</th></tr></thead><tbody>${sessions.map(s => `<tr><td><a href="#client/${s.memberId}">${e(s.memberName)}</a>${s.groupLabel ? `<br><small class="muted">${e(s.groupLabel)}</small>` : ''}</td><td>${dateText(s.scheduledAt)}<br>${timeText(s.scheduledAt)}</td><td>${e(s.programTitle)}<br><small class="muted">${e(s.trainingDay)}</small></td><td>${fa(s.exercises.filter(x => !x.skipped && x.sets.some(t => t.complete)).length)} از ${fa(s.exercises.length)}</td><td>${sessionBadge(s.status)}</td><td>${btn('مشاهده', 'session', s.id, 'compact')}${['scheduled', 'in_progress'].includes(s.status) ? ` ${btn('انجام‌شده', 'mark-complete', s.id, 'compact')} ${btn('لغو', 'cancel-session', s.id, 'text-button')}${s.status === 'scheduled' ? ` ${btn('عدم حضور', 'no-show', s.id, 'text-button')}` : ''}` : ''}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function programsView() {
    const rows = state.data.clients.filter(c => c.currentProgram);
    main.innerHTML = heading('برنامه‌های تمرینی', 'برنامه مناسب، اجرای دقیق، تغییر به‌موقع.', btn('ساخت برنامه', 'program', '', 'primary', 'plus')) + (rows.length ? `<div class="program-grid">${rows.map(c => `<article class="panel program-card"><div class="panel-body">${person(c)}<h3>${e(c.currentProgram.title)}</h3><p>${e(goals[c.currentProgram.mainGoal] || 'هدف ثبت نشده')} · ${fa(c.currentProgram.days.length)} روز در هفته</p><p>${dateText(c.currentProgram.startDate)} تا ${dateText(c.currentProgram.endDate)}</p><div class="alert-list">${c.alerts.filter(a => a.kind === 'program').map(a => badge(a.message, a.severity)).join('') || badge('برنامه جاری', 'success')}</div></div><div class="card-footer">${btn('ویرایش', 'program', c.id)}${link('برنامه و تاریخچه', `client/${c.id}/program`, 'compact')}${btn('نسخه جدید', 'duplicate', c.id, 'compact')}</div></article>`).join('')}</div>` : panel('برنامه‌های جاری', empty('هنوز برنامه‌ای ثبت نشده', 'با ساخت برنامه برای یک ورزشکار شروع کن.', btn('ساخت برنامه', 'program', '', 'primary'))));
  }
  function libraryView() {
    main.innerHTML = heading('کتابخانه حرکات', 'حرکت مناسب را پیدا کن و به برنامه اضافه کن.', btn('حرکت اختصاصی', 'exercise', '', 'primary', 'plus')) + `<div class="toolbar"><input id="library-search" type="search" aria-label="جستجوی حرکت" placeholder="جستجوی نام یا تجهیزات..." value="${e(librarySearch)}" /><select id="library-muscle" aria-label="گروه عضلانی">${options({ all: 'همه گروه‌ها', ...muscles }, libraryMuscle)}</select></div><div class="library-grid" id="library-results"></div>`;
    const render = () => { const rows = state.library.filter(x => (libraryMuscle === 'all' || x.muscleGroup === libraryMuscle) && `${x.name} ${x.equipment}`.includes(librarySearch)); $('#library-results').innerHTML = rows.length ? rows.map(x => `<article class="panel exercise-card">${badge(muscles[x.muscleGroup])}${x.custom ? ' ' + badge('حرکت شما', 'info') : ''}<h3>${e(x.name)}</h3><p>${e(x.equipment || 'بدون تجهیزات')}</p><details><summary>روش اجرا و نکته‌ها</summary><p>${e(x.instructions || 'دستورالعملی ثبت نشده')}</p><h3>اشتباه‌های رایج</h3><p>${e(x.commonMistakes || 'ثبت نشده')}</p>${x.mediaUrl ? `<a class="button compact" href="${e(x.mediaUrl)}" target="_blank" rel="noopener noreferrer">مشاهده ویدیو / GIF ${icon('external-link')}</a>` : '<small class="muted">رسانه‌ای ثبت نشده</small>'}</details></article>`).join('') : empty('حرکتی پیدا نشد', 'عبارت جستجو یا گروه عضلانی را تغییر بده.'); };
    render(); $('#library-search').addEventListener('input', ev => { librarySearch = ev.target.value; render(); }); $('#library-muscle').addEventListener('change', ev => { libraryMuscle = ev.target.value; render(); });
  }
  function performanceView() {
    const p = state.data.performance;
    main.innerHTML = heading('عملکرد من', 'نمایی از جلسات این ماه و همراهی ورزشکارانت.') + `<div class="metric-grid">${metric('ورزشکاران فعال', p.activeClients, 'users', 'در پلن‌های مجاز شما')}${metric('جلسات این ماه', p.sessionsMonth, 'calendar', 'از ابتدای ماه میلادی تا امروز')}${metric('جلسات انجام‌شده', p.completed, 'circle-check', 'تمرین ثبت‌شده توسط شما')}${metric('ورزشکاران جدید', p.newClients, 'users', 'عضویت‌های این ماه')}</div>` + panel('کیفیت همراهی', `<div class="panel-body">${facts([['جلسات لغوشده', fa(p.cancelled)], ['عدم حضور در جلسه', fa(p.noShow)], ['حضور هفتگی ورزشکاران', p.attendanceRate === null ? 'داده در دسترس نیست' : fa(p.attendanceRate) + '٪'], ['تداوم عضویت', p.retention === null ? 'داده کافی نیست' : fa(p.retention) + '٪']])}<p class="muted" style="margin-top:22px">حضور هفتگی: سهم ورزشکاران فعال با حداقل یک ورود در ۷ روز اخیر. تداوم عضویت: سهم اعضای پیش از این ماه که هنوز عضویت فعال دارند.</p></div>`);
  }
  function options(dictionary, selected = '', blank = false) { return `${blank ? '<option value="">انتخاب کنید</option>' : ''}${Object.entries(dictionary).map(([key, label]) => `<option value="${e(key)}" ${String(selected) === key ? 'selected' : ''}>${e(label)}</option>`).join('')}`; }
  let fieldIndex = 0;
  function field(label, name, value = '', type = 'text', extra = '', full = false) {
    const id = `field-${++fieldIndex}`;
    const input = type === 'textarea' ? `<textarea id="${id}" name="${name}" ${extra.includes('maxlength') ? '' : 'maxlength="3000"'} ${extra}>${e(value)}</textarea>` : `<input id="${id}" name="${name}" type="${type}" value="${e(value)}" ${extra} />`;
    return `<div class="field ${full ? 'full' : ''}"><label for="${id}">${label}</label>${input}</div>`;
  }
  function selectField(label, name, dictionary, selected, required = true, full = false) {
    const id = `field-${++fieldIndex}`;
    return `<div class="field ${full ? 'full' : ''}"><label for="${id}">${label}</label><select id="${id}" name="${name}" ${required ? 'required' : ''}>${options(dictionary, selected, required)}</select></div>`;
  }
  const clientCollator = new Intl.Collator('fa', { sensitivity: 'base', numeric: true });
  const sortableName = name => name.trim().replace(/ي/g, 'ی').replace(/ك/g, 'ک');
  function clientSelect(id = '') {
    const fieldId = `field-${++fieldIndex}`;
    const clients = [...state.data.clients].sort((a, b) => clientCollator.compare(sortableName(a.fullName), sortableName(b.fullName)) || a.id - b.id);
    return `<div class="field"><label for="${fieldId}">ورزشکار</label><select id="${fieldId}" name="memberId" required><option value="">انتخاب کنید</option>${clients.map(c => `<option value="${c.id}" ${String(id) === String(c.id) ? 'selected' : ''}>${e(c.fullName)}</option>`).join('')}</select></div>`;
  }
  function jalaliDate(value) {
    const parts = new Intl.DateTimeFormat('en-US-u-ca-persian', { timeZone: 'Asia/Tehran', year: 'numeric', month: '2-digit', day: '2-digit' }).formatToParts(new Date(`${value}T12:00:00Z`));
    const part = key => parts.find(p => p.type === key).value;
    return `${part('year')}/${part('month')}/${part('day')}`;
  }
  function jalaliDateField(label, name, value) {
    const id = `field-${++fieldIndex}`;
    return `<div class="field"><label for="${id}">${label} (شمسی)</label><input id="${id}" name="${name}" type="text" dir="ltr" inputmode="numeric" maxlength="10" value="${fa(jalaliDate(value))}" placeholder="۱۴۰۵/۰۷/۱۶" required aria-describedby="${id}-hint" /><small id="${id}-hint">سال/ماه/روز، مثلاً ۱۴۰۵/۰۷/۱۶</small></div>`;
  }
  function openDialog(title, html, submit = null, label = 'ذخیره') {
    $('#dialog-title').textContent = title;
    $('#dialog-content').innerHTML = submit ? `<form id="dialog-form"><div class="form-error" role="alert" hidden></div>${html}<div class="form-actions">${btn('انصراف', 'close-dialog')}<button class="button primary" type="submit">${label}</button></div></form>` : html;
    dialogSubmit = submit;
    if (!dialog.open) dialog.showModal();
    $('#dialog-form')?.addEventListener('submit', async ev => {
      ev.preventDefault(); const form = ev.target, button = $('button[type=submit]', form), box = $('.form-error', form), original = button.textContent; button.disabled = true; button.textContent = 'در حال ذخیره...'; box.hidden = true;
      try { await dialogSubmit(form, Object.fromEntries(new FormData(form))); dialog.close(); toast('با موفقیت ذخیره شد.'); await refresh(); await route(); }
      catch (err) { box.hidden = false; box.textContent = err.message; box.setAttribute('tabindex', '-1'); box.focus(); }
      finally { button.disabled = false; button.textContent = original; }
    });
  }
  function profileView() {
    const c = state.data.coach;
    main.innerHTML = heading('پروفایل من', 'نام و تخصصی که ورزشکاران در برنامه خود می‌بینند.') + panel('اطلاعات مربی', `<div class="panel-body"><form id="profile-form"><div class="form-error" role="alert" hidden></div><div class="form-grid">${field('نام و نام خانوادگی', 'fullName', c.fullName, 'text', 'required minlength="3" maxlength="150"')}${field('تخصص', 'specialty', c.specialty, 'text', 'required minlength="2" maxlength="160"')}${field('معرفی کوتاه', 'bio', c.bio, 'textarea', 'maxlength="1500"', true)}<div class="full"><h3>پلن‌های مجاز شما</h3><div class="alert-list">${c.plans.map(p => badge(p)).join('') || 'پلنی اختصاص داده نشده'}</div></div></div><div class="form-actions"><button type="submit" class="button primary">ذخیره پروفایل</button></div></form></div>`);
    $('#profile-form').addEventListener('submit', async ev => { ev.preventDefault(); const form = ev.target, button = $('button[type=submit]', form); button.disabled = true; try { await api('/api/coach/profile', { method: 'PATCH', body: Object.fromEntries(new FormData(form)) }); await refresh(); toast('پروفایل ذخیره شد.'); } catch (err) { const box = $('.form-error', form); box.textContent = err.message; box.hidden = false; } finally { button.disabled = false; } });
  }
  function exerciseEditor() {
    openDialog('حرکت اختصاصی جدید', `<div class="form-grid">${field('نام حرکت', 'name', '', 'text', 'required maxlength="160"')}${selectField('گروه عضلانی', 'muscleGroup', muscles)}${field('تجهیزات', 'equipment', '', 'text', 'maxlength="160"')}${field('لینک ویدیو / GIF (اختیاری)', 'mediaUrl', '', 'url', 'maxlength="200" placeholder="https://..."')}${field('روش اجرا', 'instructions', '', 'textarea')}${field('اشتباه‌های رایج', 'commonMistakes', '', 'textarea')}</div>`, async (_, data) => { await api('/api/coach/exercises', { method: 'POST', body: data }); state.library = (await api('/api/coach/exercises')).exercises; });
  }
  function exerciseRow(x = {}) {
    const n = (label, key, value, extra = '') => `<label>${label}<input data-ex-field="${key}" value="${e(value)}" ${extra} /></label>`;
    return `<div class="exercise-editor">${n('حرکت', 'name', x.name || '', 'required maxlength="160" list="exercise-names"')}${n('ست', 'sets', x.sets || 3, 'type="number" min="1" max="10" required')}${n('تکرار', 'reps', x.reps || '8-10', 'required maxlength="40"')}${btn('×', 'remove-exercise', '', 'compact remove-exercise')}</div>`;
  }
  function programDay(d = {}, index = 0) {
    const defaultDays = ['saturday', 'monday', 'wednesday', 'sunday', 'tuesday', 'thursday', 'friday'];
    const exercises = d.exercises?.length ? d.exercises : d.movements?.length ? d.movements.map(name => ({ name, sets: 3, reps: '10' })) : [{}];
    return `<section class="program-day-editor"><div class="day-heading"><input data-day-label aria-label="نام روز تمرین" value="${e(d.label || 'روز ' + fa(index + 1))}" required maxlength="160" /><select data-day-weekday aria-label="روز هفته">${options(weekdays, d.weekday || defaultDays[index])}</select>${btn('حذف روز', 'remove-day', '', 'compact')}</div><div class="day-exercises">${exercises.map(exerciseRow).join('')}</div>${btn('افزودن حرکت', 'add-exercise', '', 'compact', 'plus')}</section>`;
  }
  function programEditor(id, mode = 'edit') {
    const source = getClient(id)?.currentProgram, program = mode === 'new' ? null : source;
    const memberId = mode === 'duplicate' ? '' : id;
    const start = program?.startDate || state.data.today, end = program?.endDate || shiftDate(start, 28);
    openDialog(mode === 'duplicate' ? 'کپی برنامه برای ورزشکار' : program ? 'ویرایش برنامه تمرینی' : 'ساخت برنامه تمرینی', `<div class="form-grid">${clientSelect(memberId)}${field('نام برنامه', 'title', program ? program.title + (mode === 'duplicate' ? ' (کپی)' : '') : '', 'text', 'required maxlength="180"')}${selectField('هدف برنامه', 'mainGoal', goals, program?.mainGoal || getClient(id)?.mainGoal)}${jalaliDateField('شروع برنامه', 'startDate', start)}${jalaliDateField('پایان برنامه', 'endDate', end)}</div><datalist id="exercise-names">${state.library.map(x => `<option value="${e(x.name)}"></option>`).join('')}</datalist><div id="program-days">${(program?.days?.length ? program.days : [{}]).map(programDay).join('')}</div>${btn('افزودن روز تمرین', 'add-day', '', '', 'plus')}<p class="muted" style="margin-top:16px">ذخیره، برنامه فعلی این ورزشکار را جایگزین می‌کند. نسخه قبلی در تاریخچه نگه داشته می‌شود.</p>`, async (form, data) => {
      data.dateCalendar = 'persian';
      data.days = $$('.program-day-editor', form).map(node => ({ label: $('[data-day-label]', node).value, weekday: $('[data-day-weekday]', node).value, exercises: $$('.exercise-editor', node).map(row => Object.fromEntries($$('[data-ex-field]', row).map(input => [input.dataset.exField, input.value]))) }));
      await api('/api/coach/training-programs', { method: 'POST', body: data });
    }, 'ذخیره برنامه');
  }
  function confirmAction(title, description, callback, label = 'تأیید') { openDialog(title, `<p>${e(description)}</p>`, callback, label); }
  async function sessionView(session) {
    const s = session, editable = ['scheduled', 'in_progress'].includes(s.status);
    state.session = s;
    main.innerHTML = heading('جلسه تمرینی', `${s.memberName} · ${dateText(s.scheduledAt)}، ${timeText(s.scheduledAt)}`, link('پروفایل ورزشکار', `client/${s.memberId}/sessions`) + sessionBadge(s.status)) + `<div class="session-heading"><div><h2>${e(s.programTitle)}</h2><p class="muted">${e(s.trainingDay)} · ${fa(s.durationMinutes)} دقیقه ${s.groupLabel ? '· ' + e(s.groupLabel) : ''}</p></div><div class="heading-actions">${s.status === 'scheduled' ? btn('شروع جلسه', 'start-session', s.id, 'primary') : ''}${editable ? `${btn('افزودن حرکت', 'session-add', s.id, '', 'plus')}` : ''}</div></div>` +
      s.exercises.map((x, index) => `<section class="panel session-exercise ${x.skipped ? 'skipped' : ''}"><div class="day-heading"><div><h3>${fa(index + 1)}. ${e(x.name)}</h3><p>تکرار هدف: ${fa(x.targetReps || 'آزاد')} · استراحت: ${fa(x.rest)} ثانیه${x.rpe !== null && x.rpe !== undefined ? ' · RPE ' + fa(x.rpe) : ''}${x.rir !== null && x.rir !== undefined ? ' · RIR ' + fa(x.rir) : ''}${x.tempo ? ' · تمپو ' + e(x.tempo) : ''}</p></div>${editable ? btn(x.skipped ? 'برگرداندن حرکت' : 'رد کردن حرکت', 'skip-exercise', index, 'compact') : x.skipped ? badge('رد شده') : ''}</div>${x.sets.map((set, si) => `<div class="set-row ${set.complete ? 'done' : ''}"><strong>ست ${fa(si + 1)}</strong><label>وزن (kg)<input type="number" min="0" max="1000" step=".5" data-log-field="weight" data-ex="${index}" data-set="${si}" value="${set.weight ?? ''}" ${!editable || x.skipped ? 'disabled' : ''} /></label><label>تکرار<input type="number" min="1" max="1000" step="1" data-log-field="reps" data-ex="${index}" data-set="${si}" value="${set.reps ?? ''}" ${!editable || x.skipped ? 'disabled' : ''} /></label>${editable && !x.skipped ? `<button class="button ${set.complete ? '' : 'primary'}" data-action="complete-set" data-id="${index}:${si}" aria-pressed="${set.complete}">${set.complete ? 'انجام شد' : 'تکمیل ست'}</button>` : badge(set.complete ? 'انجام شد' : x.skipped ? 'رد شده' : 'ثبت نشده', set.complete ? 'success' : '')}</div>`).join('')}</section>`).join('') +
      (editable ? `<div class="session-bottom">${btn('ذخیره تمرین', 'save-session', s.id)}${btn('پایان جلسه', 'complete-session', s.id, 'primary', 'circle-check')}</div><p class="muted" style="margin-top:10px" id="session-save-status">تغییر وزن و تکرار را با «ذخیره تمرین» ثبت کن. تکمیل یا رد کردن ست فوراً ذخیره می‌شود.</p>` : '');
    $$('[data-log-field]').forEach(input => input.addEventListener('input', ev => { const t = ev.target; s.exercises[Number(t.dataset.ex)].sets[Number(t.dataset.set)][t.dataset.logField] = t.value === '' ? null : Number(t.value); state.dirty = true; $('#session-save-status').textContent = 'تغییرات ذخیره‌نشده دارید.'; }));
  }
  async function saveSession(status = 'in_progress') {
    const s = state.session;
    const result = await api(`/api/coach/sessions/${s.id}`, { method: 'PATCH', body: { exercises: s.exercises, status } });
    state.session = result.session; state.dirty = false;
    await refresh(); await sessionView(result.session);
  }
  async function sessionsView(token, start = shiftDate(state.data.today, -30), end = shiftDate(state.data.today, 30)) {
    const result = await api(`/api/coach/sessions?start=${start}&end=${end}`); if (token !== state.route) return;
    main.innerHTML = heading('جلسات تمرین', 'سابقه واقعی تمرین، جدا از ورود به باشگاه.') + `<form class="toolbar" id="session-range"><label>از <input name="start" type="date" value="${start}" required /></label><label>تا <input name="end" type="date" value="${end}" required /></label><button class="button" type="submit">نمایش</button><select id="session-filter" aria-label="وضعیت جلسه">${options({ all: 'همه وضعیت‌ها', ...Object.fromEntries(Object.entries(statuses).map(([k, v]) => [k, v[0]])) })}</select></form><section class="panel" id="session-results">${sessionTable(result.sessions)}</section>`;
    $('#session-range').addEventListener('submit', ev => { ev.preventDefault(); const form = ev.target; sessionsView(++state.route, form.start.value, form.end.value).catch(err => toast(err.message, true)); });
    $('#session-filter').addEventListener('change', ev => { $('#session-results').innerHTML = sessionTable(result.sessions.filter(s => ev.target.value === 'all' || s.status === ev.target.value)); });
  }
  async function route() {
    const token = ++state.route;
    const [path, query] = location.hash.slice(1).split('?'), [view = 'dashboard', id, requestedTab] = (path || 'dashboard').split('/');
    const activeView = view === 'client' ? 'clients' : view === 'session' ? 'sessions' : views[view] ? view : 'dashboard';
    $('#current-location').textContent = views[activeView];
    $$('[data-view]').forEach(a => { a.classList.toggle('active', a.dataset.view === activeView); if (a.dataset.view === activeView) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    closeMenu();
    try {
      if (view === 'client') {
        main.innerHTML = '<div class="loading-state" role="status">در حال دریافت پروفایل...</div>';
        const detail = await api(`/api/coach/clients/${Number(id)}`); if (token !== state.route) return;
        state.detail = detail; clientView(detail, tabs[requestedTab] ? requestedTab : 'overview');
      } else if (view === 'session') {
        main.innerHTML = '<div class="loading-state" role="status">در حال دریافت جلسه...</div>';
        const result = await api(`/api/coach/sessions/${Number(id)}`); if (token !== state.route) return;
        state.dirty = false; await sessionView(result.session);
      } else if (view === 'clients') { const filter = new URLSearchParams(query).get('filter'); if (filter && filters[filter]) state.filter = filter; clientsView(); }
      else if (view === 'programs') programsView();
      else if (view === 'library') libraryView();
      else if (view === 'profile') profileView();
      else if (view === 'performance') performanceView();
      else if (view === 'sessions') await sessionsView(token);
      else dashboard();
    } catch (err) { if (token === state.route) main.innerHTML = `<div class="error-state" role="alert"><h2>دریافت اطلاعات انجام نشد</h2><p>${e(err.message)}</p>${btn('تلاش دوباره', 'reload', '', '', 'refresh')}</div>`; }
  }
  async function action(button) {
    const a = button.dataset.action, id = button.dataset.id;
    if (a === 'client') location.hash = `client/${id}`;
    if (a === 'client-tab') location.hash = `client/${state.detail.client.id}/${id}`;
    if (a === 'session') location.hash = `session/${id}`;
    if (a === 'start-session') { if (state.dirty) await saveSession(); await api(`/api/coach/sessions/${id}`, { method: 'PATCH', body: { status: 'in_progress' } }); await refresh(); if (location.hash === `#session/${id}`) await route(); else location.hash = `session/${id}`; }
    if (a === 'today-clients') { state.filter = 'today'; location.hash = 'clients?filter=today'; }
    if (a === 'program') programEditor(id);
    if (a === 'program-new') programEditor(id, 'new');
    if (a === 'duplicate') programEditor(id, 'duplicate');
    if (a === 'exercise') exerciseEditor();
    if (a === 'close-dialog') dialog.close();
    if (a === 'reload') { await refresh(); await route(); }
    if (a === 'prev-clients') { state.page = Math.max(1, state.page - 1); renderClientResults(); }
    if (a === 'next-clients') { state.page++; renderClientResults(); }
    if (a === 'add-day') { const host = $('#program-days'); if ($$('.program-day-editor', host).length >= 7) throw new Error('حداکثر ۷ روز تمرین مجاز است.'); host.insertAdjacentHTML('beforeend', programDay({}, $$('.program-day-editor', host).length)); }
    if (a === 'remove-day') { if ($$('.program-day-editor').length === 1) throw new Error('حداقل یک روز تمرین لازم است.'); button.closest('.program-day-editor').remove(); }
    if (a === 'add-exercise') { const host = $('.day-exercises', button.closest('.program-day-editor')); if ($$('.exercise-editor', host).length >= 30) throw new Error('حداکثر ۳۰ حرکت مجاز است.'); host.insertAdjacentHTML('beforeend', exerciseRow()); }
    if (a === 'remove-exercise') { const row = button.closest('.exercise-editor'); if ($$('.exercise-editor', row.parentElement).length === 1) throw new Error('حداقل یک حرکت لازم است.'); row.remove(); }
    if (a === 'history') { const item = state.detail.programHistory[Number(id)]; openDialog('نسخه پیشین برنامه', programMarkup(item.program)); }
    if (a === 'archive') confirmAction('بایگانی برنامه', 'این برنامه از برنامه‌های جاری خارج می‌شود و در تاریخچه ورزشکار باقی می‌ماند.', async () => { await api(`/api/coach/training-programs/${id}`, { method: 'PATCH', body: { action: 'archive' } }); }, 'بایگانی');
    if (['cancel-session', 'no-show', 'mark-complete'].includes(a)) { const status = { 'cancel-session': 'cancelled', 'no-show': 'no_show', 'mark-complete': 'completed' }[a]; confirmAction(statuses[status][0], `وضعیت جلسه به «${statuses[status][0]}» تغییر می‌کند. اطلاعات تمرین ثبت‌شده حفظ می‌شود.`, async () => { await api(`/api/coach/sessions/${id}`, { method: 'PATCH', body: { status } }); }); }
    if (a === 'save-session') { await saveSession(); toast('تمرین ذخیره شد.'); }
    if (a === 'complete-set') {
      const [ei, si] = id.split(':').map(Number), set = state.session.exercises[ei].sets[si], previous = set.complete;
      if (!previous && (set.weight === null || set.reps === null || set.reps < 1)) throw new Error('وزن و تکرار این ست را وارد کن (برای وزن بدن، صفر).');
      set.complete = !previous; try { await saveSession(); toast('ست ذخیره شد.'); } catch (err) { set.complete = previous; throw err; }
    }
    if (a === 'skip-exercise') { const x = state.session.exercises[Number(id)], previous = x.skipped; x.skipped = !previous; try { await saveSession(); } catch (err) { x.skipped = previous; throw err; } }
    if (a === 'session-add') {
      openDialog('افزودن حرکت به جلسه', `<datalist id="session-exercise-names">${state.library.map(x => `<option value="${e(x.name)}"></option>`).join('')}</datalist><div class="form-grid">${field('نام حرکت', 'name', '', 'text', 'required maxlength="160" list="session-exercise-names"')}${field('تعداد ست', 'sets', 3, 'number', 'required min="1" max="10"')}${field('تکرار هدف', 'targetReps', '10', 'text', 'maxlength="40"')}${field('استراحت (ثانیه)', 'rest', 90, 'number', 'required min="0" max="600"')}</div>`, async (_, data) => { const s = state.session, length = s.exercises.length; s.exercises.push({ name: data.name, targetReps: data.targetReps, rest: Number(data.rest), rpe: null, rir: null, tempo: '', skipped: false, sets: Array.from({ length: Number(data.sets) }, () => ({ weight: null, reps: null, complete: false })) }); try { await saveSession(); } catch (err) { s.exercises.length = length; throw err; } });
    }
    if (a === 'complete-session') { const count = state.session.exercises.reduce((n, x) => n + (x.skipped ? 0 : x.sets.filter(s => s.complete).length), 0); confirmAction('پایان جلسه تمرینی', `${fa(count)} ست ثبت‌شده است. پایان جلسه، گزارش تمرین را ذخیره می‌کند و جلسه بسته می‌شود.`, async () => { await saveSession('completed'); }, 'پایان و ذخیره'); }
  }
  function closeMenu() { $('#coach-sidebar').classList.remove('open'); $('#sidebar-shade').hidden = true; $('#menu-button').setAttribute('aria-expanded', 'false'); $('.workspace-shell').inert = false; }
  $('#menu-button').addEventListener('click', () => { const open = !$('#coach-sidebar').classList.contains('open'); $('#coach-sidebar').classList.toggle('open', open); $('#sidebar-shade').hidden = !open; $('#menu-button').setAttribute('aria-expanded', String(open)); $('.workspace-shell').inert = open; if (open) $('a.active', $('#coach-sidebar'))?.focus(); });
  $('#sidebar-shade').addEventListener('click', () => { closeMenu(); $('#menu-button').focus(); });
  document.addEventListener('keydown', ev => { if (ev.key === 'Escape' && $('#coach-sidebar').classList.contains('open')) { closeMenu(); $('#menu-button').focus(); } if (ev.key === 'Tab' && $('#coach-sidebar').classList.contains('open')) { const nodes = $$('a,button', $('#coach-sidebar')), first = nodes[0], last = nodes.at(-1); if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); } else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); } } });
  $('#close-dialog').addEventListener('click', () => dialog.close());
  document.addEventListener('click', async ev => {
    const filter = ev.target.closest('[data-filter]'); if (filter) { state.filter = filter.dataset.filter; state.page = 1; renderClientResults(); return; }
    const button = ev.target.closest('[data-action]'); if (!button || button.disabled) return;
    const wasDisabled = button.disabled; button.disabled = true; try { await action(button); } catch (err) { toast(err.message, true); } finally { button.disabled = wasDisabled; }
  });
  $('#logout-button').addEventListener('click', async () => { try { await api('/api/logout', { method: 'POST', body: {} }); location.replace('/login'); } catch (err) { toast(err.message, true); } });
  $('#global-search').addEventListener('input', ev => { state.search = ev.target.value; state.filter = 'all'; state.page = 1; if (location.hash.startsWith('#clients')) clientsView(); else location.hash = 'clients'; });
  let savedTheme; try { savedTheme = localStorage.getItem('lifebox-coach-theme'); } catch { /* Browser storage may be disabled. */ }
  document.documentElement.dataset.theme = savedTheme || (matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light');
  $('#theme-button').addEventListener('click', () => { const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = theme; try { localStorage.setItem('lifebox-coach-theme', theme); } catch { /* Preference only. */ } });
  window.addEventListener('hashchange', async () => { if (state.dirty) { try { await saveSession(); } catch (err) { toast('تغییرات جلسه ذخیره نشد: ' + err.message, true); location.hash = `session/${state.session.id}`; return; } } if (state.data) route(); });
  window.addEventListener('beforeunload', ev => { if (state.dirty) { ev.preventDefault(); ev.returnValue = ''; } });
  window.addEventListener('resize', () => { if (window.innerWidth > 760) closeMenu(); });
  async function start() { try { const [data, library] = await Promise.all([api('/api/coach/workspace'), api('/api/coach/exercises')]); state.data = data; state.library = library.exercises; renderHeader(); await route(); } catch (err) { main.innerHTML = `<div class="error-state" role="alert"><h2>اتصال به فضای مربی انجام نشد</h2><p>${e(err.message)}</p>${btn('تلاش دوباره', 'reload', '', '', 'refresh')}</div>`; } }
  start();
})();
