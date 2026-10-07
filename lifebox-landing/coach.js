/* Coach workspace. Client records stay in memory; only theme preference is persisted. */
(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const main = $('#workspace-content');
  const dialog = $('#editor-dialog');
  const state = { data: null, library: [], detail: null, session: null, route: 0, search: '', filter: 'all', page: 1, scheduleMode: 'week', scheduleDate: '', progressMetric: 'weight', progressClient: '', dirty: false };
  const goals = { muscle_gain: 'افزایش عضله', fat_loss: 'کاهش چربی', strength: 'افزایش قدرت', recomposition: 'بازترکیب بدنی', fitness: 'آمادگی عمومی' };
  const muscles = { chest: 'سینه', back: 'پشت', shoulders: 'شانه', arms: 'بازو', legs: 'پا', core: 'میان‌تنه', full_body: 'تمام بدن' };
  const weekdays = { saturday: 'شنبه', sunday: 'یکشنبه', monday: 'دوشنبه', tuesday: 'سه‌شنبه', wednesday: 'چهارشنبه', thursday: 'پنج‌شنبه', friday: 'جمعه' };
  const statuses = { scheduled: ['برنامه‌ریزی‌شده', 'info'], in_progress: ['در حال تمرین', 'warning'], completed: ['انجام‌شده', 'success'], cancelled: ['لغوشده', ''], no_show: ['عدم حضور', 'danger'] };
  const membership = { active: ['فعال', 'success'], expiring: ['نزدیک به پایان', 'warning'], expired: ['پایان‌یافته', 'danger'] };
  const measures = { weight: ['وزن', 'کیلوگرم'], height: ['قد', 'سانتی‌متر'], body_fat: ['چربی بدن', 'درصد'], waist: ['دور کمر', 'سانتی‌متر'], chest: ['دور سینه', 'سانتی‌متر'], arms: ['دور بازو', 'سانتی‌متر'], thighs: ['دور ران', 'سانتی‌متر'], bench_press: ['پرس سینه', 'کیلوگرم'], squat: ['اسکوات', 'کیلوگرم'], deadlift: ['ددلیفت', 'کیلوگرم'], pull_ups: ['بارفیکس', 'تکرار'] };
  const views = { dashboard: 'نمای کلی', clients: 'ورزشکاران من', programs: 'برنامه‌های تمرینی', sessions: 'جلسات تمرین', schedule: 'تقویم مربی', assessments: 'ارزیابی‌ها', progress: 'روند پیشرفت', library: 'کتابخانه حرکات', notes: 'یادداشت و پیگیری', performance: 'عملکرد من', profile: 'پروفایل من' };
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
  const dateKey = (value) => new Intl.DateTimeFormat('en-CA', { timeZone: 'Asia/Tehran', year: 'numeric', month: '2-digit', day: '2-digit' }).format(new Date(value));
  const shiftDate = (value, count) => { const d = new Date(`${value}T12:00:00Z`); d.setUTCDate(d.getUTCDate() + count); return d.toISOString().slice(0, 10); };
  const getClient = (id) => state.data.clients.find(c => c.id === Number(id));
  let toastTimer, chartObserver, dialogSubmit, librarySearch = '', libraryMuscle = 'all', notesFilter = 'open';

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
    const count = data.clients.filter(c => c.alerts.length).length;
    $('#nav-alert-count').textContent = fa(count);
    $('#notification-dot').hidden = count === 0;
  }
  async function refresh() { state.data = await api('/api/coach/workspace'); renderHeader(); }
  function attentionClients() {
    const priority = { pain: 0, inactive: 1, expired: 2, low_sessions: 3, follow_up: 4, program: 5, assessment: 6 };
    return state.data.clients.filter(c => c.alerts.length).map(c => ({ ...c, alerts: [...c.alerts].sort((a, b) => (priority[a.kind] ?? 7) - (priority[b.kind] ?? 7)) })).sort((a, b) => (priority[a.alerts[0].kind] ?? 7) - (priority[b.alerts[0].kind] ?? 7));
  }
  function scheduleRows(sessions) {
    if (!sessions.length) return empty('برای امروز جلسه‌ای ثبت نشده', 'با ثبت یک جلسه، برنامه روزانه اینجا نمایش داده می‌شود.', btn('ثبت جلسه', 'book', '', 'primary', 'plus'));
    return groupedSessions(sessions).map(group => {
      const s = group[0];
      if (s.groupLabel && group.length > 1) return `<details class="group-session"><summary><span class="schedule-time">${timeText(s.scheduledAt)}<small>${fa(s.durationMinutes)} دقیقه</small></span><span class="schedule-person"><strong>${e(s.groupLabel)}</strong><span class="muted">${fa(group.length)} ورزشکار، نیمه‌خصوصی</span></span>${badge('مشاهده اعضا', 'warning')}</summary><div>${group.map(item => `<div class="schedule-row"><div class="schedule-person"><strong>${e(item.memberName)}</strong><p>${e(item.trainingDay)}</p></div>${sessionBadge(item.status)}${btn(item.status === 'scheduled' ? 'شروع تمرین' : 'مشاهده', item.status === 'scheduled' ? 'start-session' : 'session', item.id, 'compact')}</div>`).join('')}</div></details>`;
      return `<div class="schedule-row"><div class="schedule-time">${timeText(s.scheduledAt)}<small>${fa(s.durationMinutes)} دقیقه</small></div>${avatar(s.memberName, s.memberId)}<div class="schedule-person"><strong>${e(s.memberName)}</strong><p>${e(s.groupLabel || getClient(s.memberId)?.plan || '')} · ${e(s.trainingDay)}</p></div>${sessionBadge(s.status)}${btn(s.status === 'scheduled' ? 'شروع تمرین' : s.status === 'in_progress' ? 'ادامه تمرین' : 'مشاهده', s.status === 'scheduled' ? 'start-session' : 'session', s.id, s.status === 'scheduled' ? 'primary compact' : 'compact')}</div>`;
    }).join('');
  }
  function groupedSessions(sessions) {
    const groups = new Map();
    sessions.forEach(s => { const key = s.groupLabel ? `${s.groupLabel}:${s.scheduledAt}:${s.durationMinutes}` : `session:${s.id}`; if (!groups.has(key)) groups.set(key, []); groups.get(key).push(s); });
    return [...groups.values()];
  }
  function followups(clients) {
    return clients.length ? clients.map(c => `<div class="followup-row">${avatar(c.fullName, c.id)}<div class="followup-info"><strong>${e(c.fullName)}</strong><p>${e(c.alerts[0].message)}</p></div>${btn('بررسی', 'client', c.id, 'compact')}</div>`).join('') : empty('همه‌چیز مرتب است', 'ورزشکاری در انتظار پیگیری نیست.');
  }
  function clientsTable(clients, full = false) {
    if (!clients.length) return empty('ورزشکاری پیدا نشد', state.data.clients.length ? 'فیلتر یا عبارت جستجو را تغییر دهید.' : 'اعضای فعال پلن‌های مجاز شما اینجا نمایش داده می‌شوند.');
    return `<div class="table-scroll"><table class="data-table"><thead><tr><th>ورزشکار</th>${full ? '<th>سن / جنسیت</th>' : ''}<th>پلن عضویت</th><th>وضعیت</th><th>جلسات</th><th>آخرین حضور</th><th>برنامه فعلی</th><th>نیاز به توجه</th><th></th></tr></thead><tbody>${clients.map(c => `<tr><td>${person(c)}</td>${full ? `<td>${c.age === null ? 'نامشخص' : fa(c.age)} / ${e({ male: 'مرد', female: 'زن', all: 'ثبت نشده' }[c.gender] || c.gender)}</td>` : ''}<td>${e(c.plan)}</td><td>${memberBadge(c.status)}</td><td><strong>${fa(c.sessionsRemaining ?? 'نامشخص')}</strong> باقی‌مانده<br><small class="muted">${fa(c.sessionsUsed)} استفاده‌شده</small></td><td>${state.data.attendanceAvailable ? dateText(c.lastVisit) : 'داده در دسترس نیست'}</td><td>${e(c.currentProgram?.title || 'ثبت نشده')}</td><td>${c.alerts.length ? badge(c.alerts[0].message, c.alerts[0].severity) : badge('به‌روز', 'success')}</td><td>${btn('پروفایل', 'client', c.id, 'text-button')}</td></tr>`).join('')}</tbody></table></div>`;
  }
  function dashboard() {
    const d = state.data, m = d.metrics;
    const name = d.coach.fullName?.split(' ')[0];
    const today = `<span class="date-chip">${icon('calendar')}${dateText(d.today + 'T12:00:00+03:30', true)}</span>`;
    main.innerHTML = heading(name ? `${name}، روزت بخیر` : 'روزت بخیر، مربی', 'یک نگاه به امروز؛ یک قدم برای پیشرفت ورزشکارانت.', today + btn('ثبت جلسه', 'book', '', 'primary', 'plus')) +
      `<div class="metric-grid">${metric('ورزشکاران فعال', m.activeClients, 'users', link('مشاهده ورزشکاران', 'clients'))}${metric('ورزشکاران امروز', m.trainingToday, 'barbell', link('تمرین‌های امروز', 'schedule'))}${metric('جلسات امروز', m.sessionsToday, 'calendar', `${fa(d.todaySessions.filter(s => s.status === 'completed').length)} جلسه انجام شده`)}${metric('برنامه‌های نیازمند تغییر', m.programsDue, 'clipboard-list', link('بررسی برنامه‌ها', 'clients?filter=program'))}</div>` +
      `<div class="attention-strip">${icon('alert-circle')}<strong>امروز به این موارد توجه کن</strong><a href="#clients?filter=assessment">${fa(m.assessmentsDue)} ارزیابی موعدرسیده</a><a href="#clients?filter=followup">${fa(m.followUps)} ورزشکار نیازمند پیگیری</a><a href="#clients?filter=low">${fa(m.lowSessions)} سهمیه رو به پایان</a><a href="#notes">همه پیگیری‌ها ←</a></div>` +
      `<div class="dashboard-grid">${panel('برنامه امروز', scheduleRows(d.todaySessions) + `<div class="quick-actions">${btn('ساخت برنامه', 'program', '', '', 'plus')}${btn('ثبت ارزیابی', 'assessment', '', '', 'clipboard-list')}${btn('یادداشت مربی', 'note', '', '', 'plus')}${btn('ثبت پیشرفت', 'assessment', '', '', 'arrow-up-left')}${btn('ورزشکاران امروز', 'today-clients', '', '', 'users')}</div>`, link('مشاهده تقویم ←', 'schedule'), dateText(d.today + 'T12:00:00+03:30', true))}${panel('نیاز به توجه', followups(attentionClients().slice(0, 4)), badge(fa(attentionClients().length) + ' ورزشکار', 'warning'), 'یک پیگیری به‌موقع، یک تمرین بهتر')}</div>` +
      panel('ورزشکاران من', clientsTable(d.clients.slice(0, 5)) + `<div class="table-footer"><span>${fa(Math.min(5, d.clients.length))} از ${fa(d.clients.length)} ورزشکار</span><span>${d.attendanceAvailable ? 'حضور از دستگاه باشگاه دریافت می‌شود' : 'اطلاعات دستگاه حضور در دسترس نیست'}</span></div>`, link('مشاهده همه ←', 'clients'));
  }
  const filters = { all: 'همه ورزشکاران', active: 'فعال', new: 'جدید', private: 'خصوصی', semi_private: 'نیمه‌خصوصی', muscle_gain: 'افزایش عضله', fat_loss: 'کاهش چربی', strength: 'قدرت', assessment: 'نیاز به ارزیابی', program: 'نیاز به برنامه', low: 'جلسات کم', inactive: 'حضور نامنظم', followup: 'نیاز به پیگیری', today: 'تمرین امروز' };
  function filteredClients() {
    return state.data.clients.filter(c => {
      const f = state.filter;
      const matches = f === 'all' || (f === 'active' && c.status !== 'expired') || (f === 'new' && c.isNew) || c.trainingStyle === f || c.mainGoal === f || c.alerts.some(a => a.kind === ({ low: 'low_sessions', followup: 'follow_up' }[f] || f)) || (f === 'followup' && c.alerts.some(a => ['inactive', 'pain', 'attendance_drop'].includes(a.kind))) || (f === 'today' && state.data.todaySessions.some(s => s.memberId === c.id && !['cancelled', 'no_show'].includes(s.status)));
      return matches && `${c.fullName} ${c.plan} ${c.currentProgram?.title || ''}`.toLocaleLowerCase('fa').includes(state.search.toLocaleLowerCase('fa'));
    });
  }
  function renderClientResults() {
    const rows = filteredClients(), pages = Math.max(1, Math.ceil(rows.length / 15)); state.page = Math.min(state.page, pages);
    $('#client-results').innerHTML = clientsTable(rows.slice((state.page - 1) * 15, state.page * 15), true) + `<div class="table-footer"><span>${fa(rows.length)} ورزشکار</span><div>${btn('قبلی', 'prev-clients', '', 'compact')} <span>${fa(state.page)} / ${fa(pages)}</span> ${btn('بعدی', 'next-clients', '', 'compact')}</div></div>`;
    $$('[data-filter]').forEach(b => { b.classList.toggle('active', b.dataset.filter === state.filter); b.setAttribute('aria-pressed', String(b.dataset.filter === state.filter)); });
  }
  function clientsView() {
    main.innerHTML = heading('ورزشکاران من', 'تمرین هر ورزشکار را بشناس و قدم بعدی را مشخص کن.', btn('ثبت ارزیابی', 'assessment', '', '', 'plus') + btn('ساخت برنامه', 'program', '', 'primary', 'plus')) + `<div class="toolbar"><input type="search" id="client-search" placeholder="جستجوی نام، پلن یا برنامه..." aria-label="جستجوی ورزشکار" value="${e(state.search)}" /><span class="muted">${fa(state.data.clients.length)} ورزشکار در پلن‌های مجاز شما</span></div><div class="filters">${Object.entries(filters).map(([key, label]) => `<button class="filter-button" data-filter="${key}" aria-pressed="false">${label}</button>`).join('')}</div><section class="panel" id="client-results"></section>`;
    renderClientResults();
    $('#client-search').addEventListener('input', ev => { state.search = ev.target.value; state.page = 1; renderClientResults(); });
  }
  function facts(entries) { return `<dl class="profile-facts">${entries.map(([label, value]) => `<div><dt>${label}</dt><dd>${value}</dd></div>`).join('')}</dl>`; }
  const tabs = { overview: 'نمای کلی', training: 'پروفایل تمرینی', program: 'برنامه تمرینی', assessments: 'ارزیابی‌ها', progress: 'پیشرفت', sessions: 'جلسات', attendance: 'حضور در باشگاه', notes: 'یادداشت مربی' };
  function clientView(detail, tab) {
    const c = detail.client;
    main.innerHTML = `<div class="page-heading"><div class="client-heading">${avatar(c.fullName, c.id)}<div><h1>${e(c.fullName)}</h1><p>${e(c.plan)} · ${e(goals[c.mainGoal] || 'هدف ثبت نشده')}</p></div></div><div class="heading-actions">${link('ورزشکاران من', 'clients')}${btn('ثبت جلسه', 'book', c.id, 'primary', 'plus')}</div></div>` +
      panel('اطلاعات عضویت', `<div class="panel-body">${facts([['وضعیت عضویت', memberBadge(c.status)], ['جلسات استفاده‌شده', fa(c.sessionsUsed)], ['جلسات باقی‌مانده', fa(c.sessionsRemaining ?? 'نامشخص')], ['آخرین حضور', detail.attendanceAvailable ? dateText(c.lastVisit) : 'داده در دسترس نیست'], ['سن / جنسیت', `${fa(c.age ?? 'ثبت نشده')} / ${e({ male: 'مرد', female: 'زن', all: 'نامشخص' }[c.gender] || c.gender)}`], ['شروع عضویت', dateText(c.membershipStart)], ['پایان عضویت', dateText(c.expiresAt)], ['ثبت چهره', c.faceRegistered ? badge('ثبت شده', 'success') : badge('ثبت نشده', 'warning')]])}<div class="alert-list">${c.alerts.map(a => badge(a.message, a.severity)).join('')}</div></div>`) +
      `<div class="profile-tabs" role="tablist" aria-label="بخش‌های پروفایل">${Object.entries(tabs).map(([key, label]) => `<button role="tab" aria-selected="${key === tab}" class="${key === tab ? 'active' : ''}" data-action="client-tab" data-id="${key}" id="tab-${key}" aria-controls="client-tab-panel">${label}</button>`).join('')}</div><div id="client-tab-panel" role="tabpanel" aria-labelledby="tab-${e(tab)}"></div>`;
    const content = $('#client-tab-panel');
    if (tab === 'overview') content.innerHTML = `<div class="detail-grid">${panel('برنامه فعلی', c.currentProgram ? `<div class="panel-body"><h2>${e(c.currentProgram.title)}</h2><p class="muted">${fa(c.currentProgram.days.length)} روز تمرین در هفته · تا ${dateText(c.currentProgram.endDate)}</p><div class="quick-actions">${btn('مشاهده برنامه', 'client-tab', 'program')}${btn('ویرایش برنامه', 'program', c.id, 'primary')}</div></div>` : empty('برنامه‌ای ثبت نشده', 'برنامه تمرینی متناسب با هدف ورزشکار بساز.', btn('ساخت برنامه', 'program', c.id, 'primary')))}${panel('آخرین ارزیابی', c.lastAssessment ? `<div class="panel-body">${facts([['تاریخ', dateText(c.lastAssessment.date)], ['وزن', fa(c.lastAssessment.weight ?? 'ثبت نشده')], ['دور کمر', fa(c.lastAssessment.waist ?? 'ثبت نشده')], ['چربی بدن', fa(c.lastAssessment.body_fat ?? 'ثبت نشده')]])}</div>` : empty('ارزیابی اولیه ثبت نشده', 'نقطه شروع پیشرفت را ثبت کن.', btn('ثبت ارزیابی', 'assessment', c.id, 'primary')))}</div>${panel('آخرین یادداشت‌ها', `<div class="panel-body">${notesMarkup(detail.notes.slice(0, 3))}</div>`, btn('یادداشت جدید', 'note', c.id, 'compact', 'plus'))}`;
    if (tab === 'training') content.innerHTML = panel('پروفایل تمرینی', `<div class="panel-body">${facts([['هدف اصلی', e(goals[c.profile.main_goal] || 'ثبت نشده')], ['تجربه تمرین', e({ beginner: 'مبتدی', intermediate: 'متوسط', advanced: 'پیشرفته' }[c.profile.experience] || 'ثبت نشده')], ['دفعات تمرین', c.profile.frequency ? `${fa(c.profile.frequency)} روز در هفته` : 'ثبت نشده'], ['سبک ترجیحی', e(c.profile.preferred_style || 'ثبت نشده')]])}<div class="detail-section" style="margin-top:24px"><h3>محدودیت‌های جسمی</h3><p class="muted">${e(c.profile.limitations || 'ثبت نشده')}</p></div><div class="detail-section"><h3>آسیب‌ها</h3><p class="muted">${e(c.profile.injuries || 'ثبت نشده')}</p></div><h3>یادداشت تمرینی</h3><p class="muted">${e(c.profile.notes || 'ثبت نشده')}</p></div>`, btn('ویرایش پروفایل تمرینی', 'training', c.id, 'primary'));
    if (tab === 'program') content.innerHTML = panel('برنامه تمرینی فعلی', c.currentProgram ? `<div class="panel-body">${programMarkup(c.currentProgram)}</div><div class="card-footer">${btn('ویرایش', 'program', c.id)}${btn('نسخه برای ورزشکار دیگر', 'duplicate', c.id)}${btn('بایگانی', 'archive', c.currentProgram.id, 'danger')}</div>` : empty('برنامه فعالی وجود ندارد', '', btn('ساخت برنامه', 'program', c.id, 'primary')), btn('جایگزینی برنامه', 'program-new', c.id, 'primary')) + `<div class="detail-section" style="margin-top:22px">${panel('تاریخچه برنامه‌ها', detail.programHistory.length ? `<div class="panel-body">${detail.programHistory.map((r, index) => `<div class="note-row"><div class="note-meta">${dateText(r.savedAt)} ${r.program.archived ? badge('بایگانی') : badge('نسخه پیشین')}</div><h3>${e(r.program.title)}</h3>${btn('مشاهده نسخه', 'history', index, 'text-button')}</div>`).join('')}</div>` : empty('هنوز نسخه پیشینی وجود ندارد', 'هنگام ویرایش یا جایگزینی، نسخه قبلی حفظ می‌شود.'))}</div>`;
    if (tab === 'assessments') content.innerHTML = assessmentsMarkup(detail, c.id);
    if (tab === 'progress') { content.innerHTML = progressMarkup(detail); renderChart(detail); }
    if (tab === 'sessions') content.innerHTML = panel('جلسات تمرینی', sessionTable(detail.sessions), btn('ثبت جلسه', 'book', c.id, 'primary'));
    if (tab === 'attendance') content.innerHTML = panel('حضور در باشگاه', attendanceMarkup(detail), badge(fa(detail.visitCount) + ' ورود'), 'اطلاعات از دستگاه باشگاه دریافت می‌شود. ورود به باشگاه با جلسه تمرین متفاوت است.');
    if (tab === 'notes') content.innerHTML = panel('یادداشت‌های خصوصی مربی', `<div class="panel-body">${notesMarkup(detail.notes)}</div>`, btn('یادداشت جدید', 'note', c.id, 'primary', 'plus'));
    $$('[role=tab]').forEach(button => button.addEventListener('keydown', ev => {
      if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(ev.key)) {
        ev.preventDefault(); const all = $$('[role=tab]'); const index = all.indexOf(button); const next = ev.key === 'Home' ? 0 : ev.key === 'End' ? all.length - 1 : (index + (ev.key === 'ArrowLeft' ? 1 : -1) + all.length) % all.length;
        all[next].focus();
      }
    }));
  }
  function programMarkup(p) {
    return `<h2>${e(p.title)}</h2><p class="muted">${e(goals[p.mainGoal] || 'هدف ثبت نشده')} · ${dateText(p.startDate)} تا ${dateText(p.endDate)} · ${fa(p.durationWeeks)} هفته</p>${p.notes ? `<p>${e(p.notes)}</p>` : ''}<div style="margin-top:20px">${p.days.map(d => `<section class="day-panel"><div class="day-heading"><h3>${e(d.label)}</h3>${badge(weekdays[d.weekday] || 'روز نامشخص')}</div><div class="table-scroll"><table class="workout-table"><thead><tr><th>حرکت</th><th>ست × تکرار</th><th>وزن</th><th>استراحت</th><th>RPE / RIR</th><th>تمپو / نکته</th></tr></thead><tbody>${d.exercises?.length ? d.exercises.map(x => `<tr><td>${e(x.name)}</td><td dir="ltr">${fa(x.sets)} × ${fa(x.reps)}</td><td>${fa(x.weight ?? 'آزاد')}</td><td>${fa(x.rest)} ثانیه</td><td>${fa(x.rpe ?? '-')} / ${fa(x.rir ?? '-')}</td><td>${e(x.tempo)} ${e(x.note)}</td></tr>`).join('') : (d.movements || []).map(m => `<tr><td colspan="6">${e(m)}</td></tr>`).join('')}</tbody></table></div></section>`).join('')}</div>`;
  }
  function assessmentsMarkup(detail, id) {
    const rows = detail.assessments;
    const comparison = Object.entries(detail.comparison).map(([key, value]) => `<div><dt>${measures[key][0]}</dt><dd dir="ltr">${fa(value > 0 ? '+' + value : value)} <small>${measures[key][1]}</small></dd></div>`).join('');
    return `${comparison ? `<div class="detail-section">${panel('تغییر نسبت به ارزیابی قبل', `<div class="panel-body"><dl class="profile-facts">${comparison}</dl></div>`)}</div>` : ''}${panel('تاریخچه ارزیابی', rows.length ? `<div class="table-scroll"><table class="data-table"><thead><tr><th>تاریخ</th>${Object.values(measures).map(([label, unit]) => `<th>${label}<br><small>${unit}</small></th>`).join('')}<th>توضیحات</th></tr></thead><tbody>${rows.map(a => `<tr><td>${dateText(a.date)}</td>${Object.keys(measures).map(key => `<td>${fa(a[key] ?? 'ثبت نشده')}</td>`).join('')}<td>${btn('مشاهده', 'assessment-detail', a.id, 'compact')}</td></tr>`).join('')}</tbody></table></div>` : empty('ارزیابی ثبت نشده', 'اندازه‌ها و توانایی‌های اولیه ورزشکار را ثبت کن.'), btn('ثبت ارزیابی', 'assessment', id, 'primary', 'plus'))}`;
  }
  function attendanceMarkup(detail) {
    if (!detail.attendanceAvailable) return empty('داده حضور در دسترس نیست', 'پس از اتصال یا همگام‌سازی دستگاه، حضور خودکار نمایش داده می‌شود.');
    if (!detail.attendance.length) return empty('حضوری ثبت نشده', 'برای این ورزشکار هنوز سابقه‌ای از دستگاه دریافت نشده است.');
    return `<div class="table-scroll"><table class="data-table"><thead><tr><th>تاریخ</th><th>ورود</th><th>خروج</th></tr></thead><tbody>${detail.attendance.map(v => `<tr><td>${dateText(v.checkIn)}</td><td>${e(fa(String(v.checkIn).slice(11, 16)))}</td><td>${v.checkOut ? e(fa(String(v.checkOut).slice(11, 16))) : 'خروج ثبت نشده'}</td></tr>`).join('')}</tbody></table></div><div class="table-footer">${fa(detail.attendance.length)} رکورد اخیر از ${fa(detail.visitCount)} حضور</div>`;
  }
  function notesMarkup(notes) {
    return notes.length ? notes.map(n => `<article class="note-row ${n.resolved ? 'resolved' : ''}"><div class="note-meta"><span>${dateText(n.createdAt)}</span><span>${e(n.coachName)}</span>${n.sessionId ? `<a href="#session/${n.sessionId}">جلسه ${fa(n.sessionId)}</a>` : ''}${n.followUpOn ? `<span>پیگیری: ${dateText(n.followUpOn)}</span>` : ''}</div><h3><a href="#client/${n.memberId}/notes">${e(n.memberName)}</a></h3><p>${e(n.content)}</p>${n.reportedPain ? badge('درد گزارش شده', 'danger') : ''}${n.resolved ? badge('پیگیری انجام شده', 'success') : btn('انجام پیگیری', 'resolve-note', n.id, 'compact')}</article>`).join('') : empty('یادداشتی وجود ندارد', 'نکته‌های تمرینی و پیگیری‌های ورزشکار را اینجا ثبت کن.');
  }
  function sessionTable(sessions) {
    if (!sessions.length) return empty('جلسه‌ای در این بازه نیست', 'جلسه تمرینی را از تقویم یا پروفایل ورزشکار ثبت کن.', btn('ثبت جلسه', 'book', '', 'primary'));
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
  function progressMarkup(detail) {
    return `<div class="toolbar"><select id="progress-metric" aria-label="شاخص پیشرفت"><optgroup label="اندازه‌های بدن">${options(Object.fromEntries(Object.entries(measures).slice(0, 7).map(([k, v]) => [k, v[0]])), state.progressMetric)}</optgroup><optgroup label="توانایی تمرینی">${options(Object.fromEntries(Object.entries(measures).slice(7).map(([k, v]) => [k, v[0]])), state.progressMetric)}</optgroup></select><select id="progress-exercise" aria-label="پیشرفت حرکت دیگر"><option value="">حرکت‌های دیگر (از جلسات انجام‌شده)</option>${[...new Set(detail.sessions.filter(s => s.status === 'completed').flatMap(s => s.exercises.map(x => x.name)))].map(name => `<option value="exercise:${e(name)}" ${state.progressMetric === 'exercise:' + name ? 'selected' : ''}>${e(name)}</option>`).join('')}</select></div><section class="panel" id="progress-panel"></section>`;
  }
  function progressPoints(detail) {
    const key = state.progressMetric;
    if (key.startsWith('exercise:')) {
      const name = key.slice(9);
      return detail.sessions.filter(s => s.status === 'completed').map(s => ({ date: s.scheduledAt, value: Math.max(...s.exercises.filter(x => x.name === name && !x.skipped).flatMap(x => x.sets.filter(t => t.complete && t.weight !== null).map(t => t.weight)), -1) })).filter(p => p.value >= 0).sort((a, b) => new Date(a.date) - new Date(b.date));
    }
    return [...detail.assessments].reverse().filter(a => a[key] !== null).map(a => ({ date: a.date, value: a[key] }));
  }
  function renderChart(detail) {
    const points = progressPoints(detail), key = state.progressMetric;
    const label = key.startsWith('exercise:') ? key.slice(9) + '، بیشترین وزن ثبت‌شده' : measures[key][0];
    const unit = key.startsWith('exercise:') ? 'کیلوگرم' : measures[key][1];
    const host = $('#progress-panel');
    if (!points.length) host.innerHTML = empty('برای این شاخص داده‌ای وجود ندارد', 'یک ارزیابی یا جلسه تکمیل‌شده با وزن ثبت کن.');
    else {
      const first = points[0].value, current = points.at(-1).value, change = Math.round((current - first) * 100) / 100;
      host.innerHTML = `<div class="panel-header"><h2>${e(label)}</h2>${badge(unit)}</div><div class="progress-summary"><div><small>مقدار شروع</small><strong>${fa(first)}</strong><span>${dateText(points[0].date)}</span></div><div><small>مقدار فعلی</small><strong>${fa(current)}</strong><span>${dateText(points.at(-1).date)}</span></div><div><small>تغییر کل</small><strong>${fa(change > 0 ? '+' + change : change)}</strong><span>${unit}</span></div></div>${points.length > 1 ? '<div class="chart-wrap"><canvas id="progress-chart" role="img" aria-label="روند پیشرفت؛ مقادیر در جدول زیر آمده است"></canvas></div>' : '<p class="empty-state">برای نمایش روند، حداقل دو رکورد لازم است.</p>'}<div class="table-scroll"><table class="data-table"><thead><tr><th>تاریخ</th><th>${e(label)} (${unit})</th></tr></thead><tbody>${points.map(p => `<tr><td>${dateText(p.date)}</td><td>${fa(p.value)}</td></tr>`).join('')}</tbody></table></div>`;
      chartObserver?.disconnect();
      const canvas = $('#progress-chart');
      if (canvas) {
        const draw = () => {
          const width = canvas.clientWidth, height = 235, ratio = window.devicePixelRatio || 1;
          canvas.width = width * ratio; canvas.height = height * ratio;
          const ctx = canvas.getContext('2d'); ctx.scale(ratio, ratio);
          const style = getComputedStyle(document.documentElement), textColor = style.getPropertyValue('--muted'), border = style.getPropertyValue('--border');
          const low = Math.min(...points.map(p => p.value)), high = Math.max(...points.map(p => p.value)), spread = Math.max(high - low, Math.abs(high) * .03, 1), bottom = low - spread * .25, top = high + spread * .25;
          const left = 52, right = width - 15, yBottom = height - 35, yTop = 15;
          const times = points.map(p => new Date(p.date).getTime()), timeSpread = times.at(-1) - times[0];
          const positions = points.map((p, i) => ({ x: timeSpread ? left + (right - left) * (times[i] - times[0]) / timeSpread : left + (right - left) * i / (points.length - 1), y: yBottom - (yBottom - yTop) * (p.value - bottom) / (top - bottom) }));
          ctx.font = '10px Vazirmatn, sans-serif'; ctx.textAlign = 'right';
          for (let i = 0; i < 4; i++) { const y = yTop + (yBottom - yTop) * i / 3; ctx.strokeStyle = border; ctx.beginPath(); ctx.moveTo(left, y); ctx.lineTo(right, y); ctx.stroke(); ctx.fillStyle = textColor; ctx.fillText(fa(Math.round((top - (top - bottom) * i / 3) * 10) / 10), left - 10, y + 3); }
          ctx.strokeStyle = '#c7a600'; ctx.lineWidth = 2.5; ctx.beginPath(); positions.forEach((p, i) => i ? ctx.lineTo(p.x, p.y) : ctx.moveTo(p.x, p.y)); ctx.stroke();
          ctx.fillStyle = '#c7a600'; positions.forEach(p => { ctx.beginPath(); ctx.arc(p.x, p.y, 4, 0, Math.PI * 2); ctx.fill(); });
          ctx.fillStyle = textColor; ctx.textAlign = 'left'; ctx.fillText(dateText(points[0].date), left, height - 10); ctx.textAlign = 'right'; ctx.fillText(dateText(points.at(-1).date), right, height - 10);
        };
        draw(); chartObserver = new ResizeObserver(draw); chartObserver.observe(canvas);
      }
    }
    $('#progress-metric').onchange = ev => { state.progressMetric = ev.target.value; const root = $('#client-tab-panel') || $('#progress-content'); root.innerHTML = progressMarkup(detail); renderChart(detail); };
    $('#progress-exercise').onchange = ev => { if (!ev.target.value) return; state.progressMetric = ev.target.value; const root = $('#client-tab-panel') || $('#progress-content'); root.innerHTML = progressMarkup(detail); renderChart(detail); };
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
  function clientSelect(id = '', filter = () => true) { return selectField('ورزشکار', 'memberId', Object.fromEntries(state.data.clients.filter(filter).map(c => [c.id, c.fullName])), id, true); }
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
  function assessmentEditor(id) {
    openDialog('ثبت ارزیابی و پیشرفت', `<div class="form-grid">${clientSelect(id)}${field('تاریخ ارزیابی', 'date', state.data.today, 'date', `required max="${state.data.today}"`)}${Object.entries(measures).map(([key, [label, unit]]) => field(`${label} (${unit})`, key, '', 'number', `min="0" max="${key === 'body_fat' ? 100 : key === 'weight' ? 500 : key === 'height' ? 250 : ['bench_press','squat','deadlift','pull_ups'].includes(key) ? 1000 : 300}" step="${key === 'pull_ups' ? 1 : '.01'}"`)).join('')}${field('آمادگی عمومی', 'fitness_notes', '', 'textarea', '', true)}${field('موبیلیتی', 'mobility_notes', '', 'textarea')}${field('قدرت', 'strength_notes', '', 'textarea')}</div>`, async (_, data) => { await api('/api/coach/assessments', { method: 'POST', body: data }); });
  }
  function noteEditor(id, sessionId = null) {
    openDialog('یادداشت خصوصی مربی', `<div class="form-grid">${clientSelect(id)}${field('تاریخ پیگیری (اختیاری)', 'followUpOn', '', 'date')}${field('نکته تمرین یا پیگیری', 'content', '', 'textarea', 'required', true)}<label class="checkbox-field full"><input type="checkbox" name="reportedPain" />ورزشکار درد یا ناراحتی گزارش کرده است</label></div>`, async (_, data) => { data.reportedPain = data.reportedPain === 'on'; if (sessionId) data.sessionId = sessionId; await api('/api/coach/notes', { method: 'POST', body: data }); });
  }
  function trainingEditor(id) {
    const c = getClient(id), p = c.profile;
    openDialog(`پروفایل تمرینی ${c.fullName}`, `<div class="form-grid">${selectField('هدف اصلی', 'main_goal', goals, p.main_goal)}${selectField('تجربه تمرین', 'experience', { beginner: 'مبتدی', intermediate: 'متوسط', advanced: 'پیشرفته' }, p.experience)}${field('روزهای تمرین در هفته', 'frequency', p.frequency || 3, 'number', 'required min="1" max="7" step="1"')}${field('سبک تمرین ترجیحی', 'preferred_style', p.preferred_style || '', 'text', 'maxlength="160"')}${field('محدودیت‌های جسمی', 'limitations', p.limitations || '', 'textarea')}${field('آسیب‌ها', 'injuries', p.injuries || '', 'textarea')}${field('یادداشت تمرینی', 'notes', p.notes || '', 'textarea', '', true)}<label class="checkbox-field full"><input type="checkbox" name="reported_pain" ${p.reported_pain ? 'checked' : ''} />درد یا ناراحتی فعلی دارد</label></div>`, async (_, data) => { data.reported_pain = data.reported_pain === 'on'; await api(`/api/coach/clients/${c.id}`, { method: 'PATCH', body: data }); });
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
    return `<div class="exercise-editor">${n('حرکت', 'name', x.name || '', 'required maxlength="160" list="exercise-names"')}${n('ست', 'sets', x.sets || 3, 'type="number" min="1" max="10" required')}${n('تکرار', 'reps', x.reps || '8-10', 'required maxlength="40"')}${n('وزن (kg)', 'weight', x.weight ?? '', 'type="number" min="0" max="1000" step=".5"')}${n('استراحت (ثانیه)', 'rest', x.rest ?? 90, 'type="number" min="0" max="600" required')}${btn('×', 'remove-exercise', '', 'compact remove-exercise')}<div class="exercise-details">${n('RPE', 'rpe', x.rpe ?? '', 'type="number" min="1" max="10" step=".5"')}${n('RIR', 'rir', x.rir ?? '', 'type="number" min="0" max="10" step=".5"')}${n('تمپو', 'tempo', x.tempo || '', 'maxlength="40"')}${n('نکته مربی', 'note', x.note || '', 'maxlength="500"')}</div></div>`;
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
    openDialog(mode === 'duplicate' ? 'کپی برنامه برای ورزشکار' : program ? 'ویرایش برنامه تمرینی' : 'ساخت برنامه تمرینی', `<div class="form-grid">${clientSelect(memberId)}${field('نام برنامه', 'title', program ? program.title + (mode === 'duplicate' ? ' (کپی)' : '') : '', 'text', 'required maxlength="180"')}${selectField('هدف برنامه', 'mainGoal', goals, program?.mainGoal || getClient(id)?.mainGoal)}${field('شروع برنامه', 'startDate', start, 'date', 'required')}${field('پایان برنامه', 'endDate', end, 'date', 'required')}${field('نکته مربی', 'notes', program?.notes || '', 'textarea', '', true)}</div><datalist id="exercise-names">${state.library.map(x => `<option value="${e(x.name)}"></option>`).join('')}</datalist><div id="program-days">${(program?.days || [{}, {}, {}]).map(programDay).join('')}</div>${btn('افزودن روز تمرین', 'add-day', '', '', 'plus')}<p class="muted" style="margin-top:16px">ذخیره، برنامه فعلی این ورزشکار را جایگزین می‌کند. نسخه قبلی در تاریخچه نگه داشته می‌شود.</p>`, async (form, data) => {
      data.days = $$('.program-day-editor', form).map(node => ({ label: $('[data-day-label]', node).value, weekday: $('[data-day-weekday]', node).value, exercises: $$('.exercise-editor', node).map(row => Object.fromEntries($$('[data-ex-field]', row).map(input => [input.dataset.exField, input.value]))) }));
      await api('/api/coach/training-programs', { method: 'POST', body: data });
    }, 'ذخیره برنامه');
  }
  function bookingEditor(id = '') {
    const eligible = state.data.clients.filter(c => c.currentProgram && c.status !== 'expired');
    if (!eligible.length) { openDialog('ثبت جلسه', empty('ابتدا یک برنامه تمرینی ثبت کن', 'برای رزرو جلسه، ورزشکار به عضویت فعال و برنامه نیاز دارد.', btn('ساخت برنامه', 'program', id, 'primary'))); return; }
    const selected = eligible.find(c => c.id === Number(id)) || eligible[0];
    openDialog('ثبت جلسه تمرینی', `<div class="form-grid">${selectField('ورزشکار اصلی', 'memberId', Object.fromEntries(eligible.map(c => [c.id, c.fullName])), selected.id)}${field('تاریخ و ساعت (تهران)', 'scheduledAt', `${state.scheduleDate || state.data.today}T10:00`, 'datetime-local', 'required')}${selectField('روز برنامه', 'dayIndex', Object.fromEntries(selected.currentProgram.days.map((d, i) => [i, d.label])), 0)}${field('مدت (دقیقه)', 'durationMinutes', 60, 'number', 'required min="15" max="240"')}${field('نام گروه نیمه‌خصوصی (اختیاری)', 'groupLabel', '', 'text', 'maxlength="160"', true)}<div class="field full"><label>اعضای دیگر گروه (اختیاری)</label><small>روز انتخاب‌شده از برنامه هر عضو استفاده می‌شود.</small><div class="member-checks">${eligible.map(c => `<label class="checkbox-field"><input type="checkbox" name="additionalMember" value="${c.id}" />${e(c.fullName)}</label>`).join('')}</div></div></div>`, async (form, data) => {
      data.memberIds = [...new Set([data.memberId, ...new FormData(form).getAll('additionalMember')])];
      data.scheduledAt += '+03:30'; await api('/api/coach/sessions', { method: 'POST', body: data });
    }, 'ثبت در تقویم');
    $('[name=memberId]', dialog).addEventListener('change', ev => { const c = getClient(ev.target.value); $('[name=dayIndex]', dialog).innerHTML = options(Object.fromEntries(c.currentProgram.days.map((d, i) => [i, d.label])), 0); });
  }
  function confirmAction(title, description, callback, label = 'تأیید') { openDialog(title, `<p>${e(description)}</p>`, callback, label); }
  async function sessionView(session) {
    const s = session, editable = ['scheduled', 'in_progress'].includes(s.status);
    state.session = s;
    main.innerHTML = heading('جلسه تمرینی', `${s.memberName} · ${dateText(s.scheduledAt)}، ${timeText(s.scheduledAt)}`, link('پروفایل ورزشکار', `client/${s.memberId}/sessions`) + sessionBadge(s.status)) + `<div class="session-heading"><div><h2>${e(s.programTitle)}</h2><p class="muted">${e(s.trainingDay)} · ${fa(s.durationMinutes)} دقیقه ${s.groupLabel ? '· ' + e(s.groupLabel) : ''}</p></div><div class="heading-actions">${s.status === 'scheduled' ? btn('شروع جلسه', 'start-session', s.id, 'primary') : ''}${editable ? `${btn('افزودن حرکت', 'session-add', s.id, '', 'plus')}${btn('یادداشت سریع', 'session-note', s.id)}` : ''}</div></div>` +
      s.exercises.map((x, index) => `<section class="panel session-exercise ${x.skipped ? 'skipped' : ''}"><div class="day-heading"><div><h3>${fa(index + 1)}. ${e(x.name)}</h3><p>تکرار هدف: ${fa(x.targetReps || 'آزاد')} · استراحت: ${fa(x.rest)} ثانیه${x.rpe !== null && x.rpe !== undefined ? ' · RPE ' + fa(x.rpe) : ''}${x.rir !== null && x.rir !== undefined ? ' · RIR ' + fa(x.rir) : ''}${x.tempo ? ' · تمپو ' + e(x.tempo) : ''}</p>${x.note ? `<p>${e(x.note)}</p>` : ''}</div>${editable ? btn(x.skipped ? 'برگرداندن حرکت' : 'رد کردن حرکت', 'skip-exercise', index, 'compact') : x.skipped ? badge('رد شده') : ''}</div>${x.sets.map((set, si) => `<div class="set-row ${set.complete ? 'done' : ''}"><strong>ست ${fa(si + 1)}</strong><label>وزن (kg)<input type="number" min="0" max="1000" step=".5" data-log-field="weight" data-ex="${index}" data-set="${si}" value="${set.weight ?? ''}" ${!editable || x.skipped ? 'disabled' : ''} /></label><label>تکرار<input type="number" min="1" max="1000" step="1" data-log-field="reps" data-ex="${index}" data-set="${si}" value="${set.reps ?? ''}" ${!editable || x.skipped ? 'disabled' : ''} /></label>${editable && !x.skipped ? `<button class="button ${set.complete ? '' : 'primary'}" data-action="complete-set" data-id="${index}:${si}" aria-pressed="${set.complete}">${set.complete ? 'انجام شد' : 'تکمیل ست'}</button>` : badge(set.complete ? 'انجام شد' : x.skipped ? 'رد شده' : 'ثبت نشده', set.complete ? 'success' : '')}</div>`).join('')}</section>`).join('') +
      (editable ? `<div class="session-bottom"><textarea id="session-note" aria-label="یادداشت پایان جلسه" placeholder="نکته پایان تمرین؛ مثلاً افزایش وزنه در جلسه بعد..." maxlength="3000">${e(s.notes)}</textarea>${btn('ذخیره تمرین', 'save-session', s.id)}${btn('پایان جلسه', 'complete-session', s.id, 'primary', 'circle-check')}</div><p class="muted" style="margin-top:10px" id="session-save-status">تغییر وزن و تکرار را با «ذخیره تمرین» ثبت کن. تکمیل یا رد کردن ست فوراً ذخیره می‌شود.</p>` : panel('یادداشت پایان جلسه', `<div class="panel-body"><p>${e(s.notes || 'یادداشتی ثبت نشده')}</p></div>`));
    $$('[data-log-field]').forEach(input => input.addEventListener('input', ev => { const t = ev.target; s.exercises[Number(t.dataset.ex)].sets[Number(t.dataset.set)][t.dataset.logField] = t.value === '' ? null : Number(t.value); state.dirty = true; $('#session-save-status').textContent = 'تغییرات ذخیره‌نشده دارید.'; }));
    $('#session-note')?.addEventListener('input', ev => { s.notes = ev.target.value; state.dirty = true; });
  }
  async function saveSession(status = 'in_progress') {
    const s = state.session;
    const result = await api(`/api/coach/sessions/${s.id}`, { method: 'PATCH', body: { exercises: s.exercises, notes: s.notes, status } });
    state.session = result.session; state.dirty = false;
    await refresh(); await sessionView(result.session);
  }
  async function scheduleView(token) {
    const start = state.scheduleDate || state.data.today, end = state.scheduleMode === 'week' ? shiftDate(start, 6) : start;
    const result = await api(`/api/coach/sessions?start=${start}&end=${end}`); if (token !== state.route) return;
    main.innerHTML = heading('تقویم مربی', 'جلسات خصوصی و نیمه‌خصوصی؛ هر ورزشکار با ثبت تمرین مستقل.', btn('ثبت جلسه', 'book', '', 'primary', 'plus')) + `<div class="toolbar"><button class="filter-button ${state.scheduleMode === 'day' ? 'active' : ''}" data-action="schedule-mode" data-id="day">روزانه</button><button class="filter-button ${state.scheduleMode === 'week' ? 'active' : ''}" data-action="schedule-mode" data-id="week">هفتگی</button>${btn('قبلی', 'schedule-prev', '', 'compact')}${btn('امروز', 'schedule-today', '', 'compact')}${btn('بعدی', 'schedule-next', '', 'compact')}<input id="schedule-date" type="date" value="${start}" aria-label="تاریخ شروع تقویم" /></div>` +
      (state.scheduleMode === 'day' ? panel(dateText(start + 'T12:00:00+03:30', true), scheduleRows(result.sessions)) : `<div class="schedule-grid">${Array.from({ length: 7 }, (_, i) => { const d = shiftDate(start, i), sessions = result.sessions.filter(s => dateKey(s.scheduledAt) === d); return `<section class="schedule-column"><div class="schedule-day ${d === state.data.today ? 'today' : ''}">${dateText(d + 'T12:00:00+03:30', true)}</div>${sessions.length ? sessions.map(s => `<article class="calendar-event"><span>${timeText(s.scheduledAt)} (${fa(s.durationMinutes)} دقیقه)</span><strong>${e(s.memberName)}</strong><p>${e(s.groupLabel || s.trainingDay)}</p>${sessionBadge(s.status)}<div>${btn('مشاهده جلسه', 'session', s.id, 'text-button')}</div></article>`).join('') : '<p class="empty-state">بدون جلسه</p>'}</section>`; }).join('')}</div>`);
    $('#schedule-date').addEventListener('change', ev => { if (ev.target.value) { state.scheduleDate = ev.target.value; route(); } });
  }
  async function sessionsView(token, start = shiftDate(state.data.today, -30), end = shiftDate(state.data.today, 30)) {
    const result = await api(`/api/coach/sessions?start=${start}&end=${end}`); if (token !== state.route) return;
    main.innerHTML = heading('جلسات تمرین', 'سابقه واقعی تمرین، جدا از ورود به باشگاه.', btn('ثبت جلسه', 'book', '', 'primary', 'plus')) + `<form class="toolbar" id="session-range"><label>از <input name="start" type="date" value="${start}" required /></label><label>تا <input name="end" type="date" value="${end}" required /></label><button class="button" type="submit">نمایش</button><select id="session-filter" aria-label="وضعیت جلسه">${options({ all: 'همه وضعیت‌ها', ...Object.fromEntries(Object.entries(statuses).map(([k, v]) => [k, v[0]])) })}</select></form><section class="panel" id="session-results">${sessionTable(result.sessions)}</section>`;
    $('#session-range').addEventListener('submit', ev => { ev.preventDefault(); const form = ev.target; sessionsView(++state.route, form.start.value, form.end.value).catch(err => toast(err.message, true)); });
    $('#session-filter').addEventListener('change', ev => { $('#session-results').innerHTML = sessionTable(result.sessions.filter(s => ev.target.value === 'all' || s.status === ev.target.value)); });
  }
  async function notesView(token) {
    const result = await api('/api/coach/notes'); if (token !== state.route) return;
    main.innerHTML = heading('یادداشت و پیگیری', 'نکته‌های خصوصی شما، همراه با مواردی که نیاز به توجه دارند.', btn('یادداشت جدید', 'note', '', 'primary', 'plus')) + `<div class="dashboard-grid">${panel('پیگیری ورزشکاران', followups(attentionClients()))}${panel('یادداشت‌های من', `<div class="panel-body"><div class="filters"><button class="filter-button" data-note-filter="open">باز</button><button class="filter-button" data-note-filter="resolved">انجام‌شده</button><button class="filter-button" data-note-filter="all">همه</button></div><div id="notes-list"></div></div>`)}</div>`;
    const render = () => { $('#notes-list').innerHTML = notesMarkup(result.notes.filter(n => notesFilter === 'all' || n.resolved === (notesFilter === 'resolved'))); $$('[data-note-filter]').forEach(b => { b.classList.toggle('active', b.dataset.noteFilter === notesFilter); b.setAttribute('aria-pressed', String(b.dataset.noteFilter === notesFilter)); }); };
    $$('[data-note-filter]').forEach(b => b.addEventListener('click', () => { notesFilter = b.dataset.noteFilter; render(); })); render();
  }
  async function assessmentView() {
    const clients = state.data.clients;
    main.innerHTML = heading('ارزیابی‌ها', 'ارزیابی اولیه و ماهانه؛ مبنای تصمیم‌های تمرینی.', btn('ثبت ارزیابی', 'assessment', '', 'primary', 'plus')) + panel('وضعیت ارزیابی ورزشکاران', clients.length ? `<div class="table-scroll"><table class="data-table"><thead><tr><th>ورزشکار</th><th>آخرین ارزیابی</th><th>وزن (kg)</th><th>دور کمر (cm)</th><th>وضعیت</th><th></th></tr></thead><tbody>${clients.map(c => `<tr><td>${person(c)}</td><td>${dateText(c.lastAssessment?.date)}</td><td>${fa(c.lastAssessment?.weight ?? 'ثبت نشده')}</td><td>${fa(c.lastAssessment?.waist ?? 'ثبت نشده')}</td><td>${c.alerts.some(a => a.kind === 'assessment') ? badge(c.isNew ? 'ارزیابی اولیه' : 'ارزیابی ماهانه', 'info') : badge('به‌روز', 'success')}</td><td>${btn('ثبت ارزیابی', 'assessment', c.id, 'compact')} ${link('تاریخچه', `client/${c.id}/assessments`, 'compact')}</td></tr>`).join('')}</tbody></table></div>` : empty('ورزشکاری وجود ندارد'));
  }
  async function progressView(token) {
    const id = state.progressClient || state.data.clients[0]?.id;
    main.innerHTML = heading('روند پیشرفت', 'اندازه‌های بدن و توانایی تمرین در طول زمان.') + `<div class="toolbar"><select id="progress-client" aria-label="انتخاب ورزشکار">${options(Object.fromEntries(state.data.clients.map(c => [c.id, c.fullName])), id)}</select>${id ? btn('ثبت پیشرفت', 'assessment', id, 'primary', 'plus') : ''}</div><div id="progress-content"></div>`;
    if (!id) { $('#progress-content').innerHTML = empty('ورزشکاری وجود ندارد'); return; }
    const detail = await api(`/api/coach/clients/${id}`); if (token !== state.route) return;
    $('#progress-content').innerHTML = progressMarkup(detail); renderChart(detail);
    $('#progress-client').addEventListener('change', ev => { state.progressClient = ev.target.value; state.progressMetric = 'weight'; route(); });
  }
  async function route() {
    const token = ++state.route; chartObserver?.disconnect();
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
      else if (view === 'assessments') await assessmentView();
      else if (view === 'progress') await progressView(token);
      else if (view === 'schedule') await scheduleView(token);
      else if (view === 'sessions') await sessionsView(token);
      else if (view === 'notes') await notesView(token);
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
    if (a === 'assessment') assessmentEditor(id);
    if (a === 'note') noteEditor(id);
    if (a === 'training') trainingEditor(id);
    if (a === 'program') programEditor(id);
    if (a === 'program-new') programEditor(id, 'new');
    if (a === 'duplicate') programEditor(id, 'duplicate');
    if (a === 'exercise') exerciseEditor();
    if (a === 'book') bookingEditor(id);
    if (a === 'close-dialog') dialog.close();
    if (a === 'reload') { await refresh(); await route(); }
    if (a === 'prev-clients') { state.page = Math.max(1, state.page - 1); renderClientResults(); }
    if (a === 'next-clients') { state.page++; renderClientResults(); }
    if (a === 'add-day') { const host = $('#program-days'); if ($$('.program-day-editor', host).length >= 7) throw new Error('حداکثر ۷ روز تمرین مجاز است.'); host.insertAdjacentHTML('beforeend', programDay({}, $$('.program-day-editor', host).length)); }
    if (a === 'remove-day') { if ($$('.program-day-editor').length === 1) throw new Error('حداقل یک روز تمرین لازم است.'); button.closest('.program-day-editor').remove(); }
    if (a === 'add-exercise') { const host = $('.day-exercises', button.closest('.program-day-editor')); if ($$('.exercise-editor', host).length >= 30) throw new Error('حداکثر ۳۰ حرکت مجاز است.'); host.insertAdjacentHTML('beforeend', exerciseRow()); }
    if (a === 'remove-exercise') { const row = button.closest('.exercise-editor'); if ($$('.exercise-editor', row.parentElement).length === 1) throw new Error('حداقل یک حرکت لازم است.'); row.remove(); }
    if (a === 'history') { const item = state.detail.programHistory[Number(id)]; openDialog('نسخه پیشین برنامه', programMarkup(item.program)); }
    if (a === 'assessment-detail') { const item = state.detail.assessments.find(x => x.id === Number(id)); openDialog('جزئیات ارزیابی', `<p class="muted">${dateText(item.date)}</p>${facts(Object.entries(measures).map(([key, [label, unit]]) => [label, `${fa(item[key] ?? 'ثبت نشده')} <small>${unit}</small>`]))}<div style="margin-top:24px"><h3>آمادگی عمومی</h3><p>${e(item.fitness_notes || 'ثبت نشده')}</p><h3>موبیلیتی</h3><p>${e(item.mobility_notes || 'ثبت نشده')}</p><h3>قدرت</h3><p>${e(item.strength_notes || 'ثبت نشده')}</p></div>`); }
    if (a === 'archive') confirmAction('بایگانی برنامه', 'این برنامه از برنامه‌های جاری خارج می‌شود و در تاریخچه ورزشکار باقی می‌ماند.', async () => { await api(`/api/coach/training-programs/${id}`, { method: 'PATCH', body: { action: 'archive' } }); }, 'بایگانی');
    if (a === 'resolve-note') { await api(`/api/coach/notes/${id}`, { method: 'PATCH', body: { resolved: true } }); await refresh(); await route(); toast('پیگیری انجام شد.'); }
    if (a === 'schedule-mode') { state.scheduleMode = id; await route(); }
    if (a === 'schedule-prev' || a === 'schedule-next') { state.scheduleDate = shiftDate(state.scheduleDate || state.data.today, (a === 'schedule-prev' ? -1 : 1) * (state.scheduleMode === 'week' ? 7 : 1)); await route(); }
    if (a === 'schedule-today') { state.scheduleDate = state.data.today; await route(); }
    if (['cancel-session', 'no-show', 'mark-complete'].includes(a)) { const status = { 'cancel-session': 'cancelled', 'no-show': 'no_show', 'mark-complete': 'completed' }[a]; confirmAction(statuses[status][0], `وضعیت جلسه به «${statuses[status][0]}» تغییر می‌کند. اطلاعات تمرین ثبت‌شده حفظ می‌شود.`, async () => { await api(`/api/coach/sessions/${id}`, { method: 'PATCH', body: { status } }); }); }
    if (a === 'save-session') { await saveSession(); toast('تمرین ذخیره شد.'); }
    if (a === 'complete-set') {
      const [ei, si] = id.split(':').map(Number), set = state.session.exercises[ei].sets[si], previous = set.complete;
      if (!previous && (set.weight === null || set.reps === null || set.reps < 1)) throw new Error('وزن و تکرار این ست را وارد کن (برای وزن بدن، صفر).');
      set.complete = !previous; try { await saveSession(); toast('ست ذخیره شد.'); } catch (err) { set.complete = previous; throw err; }
    }
    if (a === 'skip-exercise') { const x = state.session.exercises[Number(id)], previous = x.skipped; x.skipped = !previous; try { await saveSession(); } catch (err) { x.skipped = previous; throw err; } }
    if (a === 'session-note') { if (state.dirty) await saveSession(); noteEditor(state.session.memberId, state.session.id); }
    if (a === 'session-add') {
      openDialog('افزودن حرکت به جلسه', `<datalist id="session-exercise-names">${state.library.map(x => `<option value="${e(x.name)}"></option>`).join('')}</datalist><div class="form-grid">${field('نام حرکت', 'name', '', 'text', 'required maxlength="160" list="session-exercise-names"')}${field('تعداد ست', 'sets', 3, 'number', 'required min="1" max="10"')}${field('تکرار هدف', 'targetReps', '10', 'text', 'maxlength="40"')}${field('استراحت (ثانیه)', 'rest', 90, 'number', 'required min="0" max="600"')}</div>`, async (_, data) => { const s = state.session, length = s.exercises.length; s.exercises.push({ name: data.name, targetReps: data.targetReps, rest: Number(data.rest), rpe: null, rir: null, tempo: '', note: '', skipped: false, sets: Array.from({ length: Number(data.sets) }, () => ({ weight: null, reps: null, complete: false })) }); try { await saveSession(); } catch (err) { s.exercises.length = length; throw err; } });
    }
    if (a === 'complete-session') { const count = state.session.exercises.reduce((n, x) => n + (x.skipped ? 0 : x.sets.filter(s => s.complete).length), 0); confirmAction('پایان جلسه تمرینی', `${fa(count)} ست ثبت‌شده است. پایان جلسه، گزارش تمرین و یادداشت را ذخیره می‌کند و جلسه بسته می‌شود.`, async () => { await saveSession('completed'); }, 'پایان و ذخیره'); }
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
  $('#theme-button').addEventListener('click', () => { const theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; document.documentElement.dataset.theme = theme; try { localStorage.setItem('lifebox-coach-theme', theme); } catch { /* Preference only. */ } if ($('#progress-chart')) { const detail = state.detail; if (location.hash.startsWith('#client') && detail) renderChart(detail); else route(); } });
  window.addEventListener('hashchange', async () => { if (state.dirty) { try { await saveSession(); } catch (err) { toast('تغییرات جلسه ذخیره نشد: ' + err.message, true); location.hash = `session/${state.session.id}`; return; } } if (state.data) route(); });
  window.addEventListener('beforeunload', ev => { if (state.dirty) { ev.preventDefault(); ev.returnValue = ''; } });
  window.addEventListener('resize', () => { if (window.innerWidth > 760) closeMenu(); });
  async function start() { try { const [data, library] = await Promise.all([api('/api/coach/workspace'), api('/api/coach/exercises')]); state.data = data; state.library = library.exercises; state.scheduleDate = data.today; renderHeader(); await route(); } catch (err) { main.innerHTML = `<div class="error-state" role="alert"><h2>اتصال به فضای مربی انجام نشد</h2><p>${e(err.message)}</p>${btn('تلاش دوباره', 'reload', '', '', 'refresh')}</div>`; } }
  start();
})();
