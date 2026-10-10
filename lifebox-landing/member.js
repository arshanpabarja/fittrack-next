/* Personal records live in memory. Only the appearance preference uses localStorage. */
(() => {
  'use strict';
  const $ = (s, root = document) => root.querySelector(s);
  const $$ = (s, root = document) => [...root.querySelectorAll(s)];
  const main = $('#member-content'), dialog = $('#member-dialog');
  const state = { data: null, day: 0, sessionFilter: 'upcoming', workout: null };
  const views = { dashboard: 'نمای کلی', program: 'برنامه من', workout: 'تمرین', membership: 'عضویت من', sessions: 'جلسات من', attendance: 'حضور در باشگاه', coach: 'مربی من', payments: 'پرداخت‌ها', notifications: 'اعلان‌ها', profile: 'پروفایل من' };
  const weekdays = { saturday: 'شنبه', sunday: 'یکشنبه', monday: 'دوشنبه', tuesday: 'سه‌شنبه', wednesday: 'چهارشنبه', thursday: 'پنج‌شنبه', friday: 'جمعه' };
  const requestKinds = { coach_contact: 'تماس با مربی' };
  const statuses = { active: ['فعال', 'success'], unknown: ['نیاز به بررسی', 'warning'], expired: ['پایان‌یافته', 'danger'], scheduled: ['برنامه‌ریزی‌شده', 'warning'], in_progress: ['در حال تمرین', 'warning'], completed: ['انجام‌شده', 'success'], cancelled: ['لغوشده', ''], no_show: ['عدم حضور', 'danger'], pending: ['در انتظار بررسی', 'warning'], approved: ['تأییدشده', 'success'], closed: ['بسته‌شده', ''], registered: ['ثبت‌شده', 'success'] };
  const e = value => String(value ?? '').replace(/[&<>"']/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]));
  const fa = value => String(value ?? 'ثبت نشده').replace(/\d/g, d => '۰۱۲۳۴۵۶۷۸۹'[d]);
  const numeric = value => value == null ? 'نامشخص' : fa(value);
  const money = value => value == null ? 'نامشخص' : fa(Number(value).toLocaleString('en-US'));
  const icon = name => `<img src="/assets/icons/${name}.svg" alt="" loading="lazy" />`;
  const badge = (label, tone = '') => `<span class="badge ${tone}">${e(label)}</span>`;
  const statusBadge = status => badge(...(statuses[status] || ['ثبت نشده', '']));
  const btn = (label, action, id = '', style = '', symbol = '') => `<button type="button" class="button ${style}" data-action="${action}" data-id="${e(id)}">${symbol ? icon(symbol) : ''}${label}</button>`;
  const link = (label, view, style = 'text') => `<a href="#${view}" class="button ${style}">${label}</a>`;
  const heading = (title, sub, action = '') => `<div class="page-heading"><div><h1>${e(title)}</h1>${sub ? `<p>${e(sub)}</p>` : ''}</div>${action}</div>`;
  const panel = (title, body, action = '', description = '') => `<section class="panel"><div class="panel-head"><h2>${title}</h2>${action}</div>${description ? `<p class="muted small" style="padding:8px 22px 0">${e(description)}</p>` : ''}${body}</section>`;
  const empty = (title, sub = '', action = '', symbol = 'clipboard-list') => `<div class="empty">${icon(symbol)}<h3>${e(title)}</h3>${sub ? `<p>${e(sub)}</p>` : ''}${action}</div>`;
  const facts = (items, wide = false) => `<dl class="fact-grid ${wide ? 'wide' : ''}">${items.map(([label, value]) => `<div class="fact"><dt>${e(label)}</dt><dd>${value}</dd></div>`).join('')}</dl>`;
  const table = (columns, rows) => `<div class="table-wrap"><table><thead><tr>${columns.map(c => `<th scope="col">${c}</th>`).join('')}</tr></thead><tbody>${rows.map(r => `<tr>${r.map(c => `<td>${c}</td>`).join('')}</tr>`).join('')}</tbody></table></div>`;
  const options = (values, selected) => Object.entries(values).map(([key, label]) => `<option value="${e(key)}" ${key === selected ? 'selected' : ''}>${e(label)}</option>`).join('');
  function dateValue(value) {
    if (!value || Number(String(value).slice(0, 4)) < 1700) return null;
    return new Date(/^\d{4}-\d\d-\d\d$/.test(value) ? value + 'T12:00:00+03:30' : String(value).replace(' ', 'T'));
  }
  function dateText(value, config = {}) {
    if (!value) return 'ثبت نشده';
    const date = dateValue(value);
    if (!date || Number.isNaN(date.getTime())) return e(fa(String(value).slice(0, 10).replace(/-/g, '/')));
    return date.toLocaleDateString('fa-IR', { timeZone: 'Asia/Tehran', day: 'numeric', month: 'long', ...config });
  }
  function timeText(value) {
    if (!value) return 'ثبت نشده';
    const date = dateValue(value);
    if (!date || Number.isNaN(date.getTime())) return e(fa(String(value).slice(11, 16)));
    return date.toLocaleTimeString('fa-IR', { timeZone: 'Asia/Tehran', hour: '2-digit', minute: '2-digit' });
  }
  function dateKey(value) {
    const d = dateValue(value);
    return d && !Number.isNaN(d.getTime()) ? d.toLocaleDateString('en-CA', { timeZone: 'Asia/Tehran' }) : String(value || '').slice(0, 10);
  }
  function initials(name) { return String(name).split(/\s+/).filter(Boolean).slice(0, 2).map(s => s[0]).join(''); }
  let toastTimer;
  function toast(message) { $('#toast').textContent = message; $('#toast').hidden = false; clearTimeout(toastTimer); toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 4500); }
  async function api(path, method = 'GET', body) {
    const token = document.cookie.split('; ').find(c => c.startsWith('csrftoken='))?.slice(10) || '';
    const response = await fetch(path, { method, credentials: 'same-origin', headers: { 'Content-Type': 'application/json', 'X-CSRFToken': decodeURIComponent(token) }, ...(body !== undefined ? { body: JSON.stringify(body) } : {}) });
    const data = await response.json().catch(() => ({}));
    if (response.status === 401) { window.location.replace('/login'); throw new Error('وارد حساب شوید.'); }
    if (!response.ok || data.ok === false) throw new Error(data.message || data.error || 'ارتباط برقرار نشد. دوباره تلاش کنید.');
    return data;
  }
  async function load() {
    try {
      const bootstrap = $('#member-bootstrap');
      if (bootstrap) { state.data = JSON.parse(bootstrap.textContent); bootstrap.remove(); }
      else state.data = await api('/api/member/workspace');
      state.workout = state.data.workouts.find(w => !w.finishedAt) || null;
      state.day = state.data.todayDay ?? state.data.nextDay;
      const name = state.data.user.fullName;
      $('#member-name').textContent = name;
      $('#member-initials').textContent = initials(name);
      $('#topbar-initials').textContent = initials(name);
      updateNotifications();
      render();
    } catch (err) { main.innerHTML = empty('دریافت اطلاعات انجام نشد', err.message, btn('تلاش دوباره', 'retry', '', 'primary', 'refresh')); }
    main.setAttribute('aria-busy', 'false');
  }
  function updateNotifications() {
    const unread = state.data.notifications.filter(n => !n.read).length;
    $('#notification-count').textContent = fa(unread);
    $('#notification-count').hidden = !unread || !state.data.notificationsEnabled;
  }
  function currentView() { const key = location.hash.slice(1).split('?')[0] || 'dashboard'; return views[key] ? key : 'dashboard'; }
  function render() {
    if (!state.data) return;
    const view = currentView();
    $('#current-location').textContent = views[view];
    document.title = `${views[view]} | لایف باکس`;
    $$('[data-view]').forEach(a => { a.classList.toggle('active', a.dataset.view === view); if (a.dataset.view === view) a.setAttribute('aria-current', 'page'); else a.removeAttribute('aria-current'); });
    const renderers = { dashboard: dashboardView, program: programView, membership: membershipView, workout: workoutView, attendance: attendanceView, sessions: sessionsView, coach: coachView, payments: paymentsView, notifications: notificationsView, profile: profileView };
    main.innerHTML = renderers[view]();
  }
  function metric(label, value, unit, foot, symbol, small = false) { return `<article class="metric"><div class="metric-top"><span>${label}</span>${icon(symbol)}</div><div class="metric-value ${small ? 'small-value' : ''}">${value}<span>${unit}</span></div><div class="metric-foot">${foot}</div></article>`; }
  function upcomingSessions() { return state.data.sessions.filter(s => s.status === 'scheduled' && dateValue(s.date)?.getTime() >= Date.now()).sort((a, b) => new Date(a.date) - new Date(b.date)); }
  function nextSessionMarkup() {
    const next = upcomingSessions()[0];
    if (!next) return empty('جلسه‌ای پیش رو ثبت نشده', 'برای هماهنگی زمان تمرین، درخواست تماس با مربی ثبت کنید.', btn('تماس با مربی', 'request', 'coach_contact', 'text'), 'calendar');
    return `<div class="next-session"><div class="calendar-tile"><small>${dateText(next.date, { month: 'short', day: undefined })}</small><strong>${dateText(next.date, { month: undefined })}</strong></div><div class="session-copy"><h3>${e(next.trainingDay || next.programTitle || 'جلسه تمرین')}</h3><p>${e(next.coachName)}</p></div><span class="session-time">${timeText(next.date)}</span></div>`;
  }
  function coachSummary() {
    const c = state.data.coach;
    return c ? `<div class="coach-summary"><span class="avatar coach-avatar">${e(initials(c.name))}</span><div><strong>${e(c.name)}</strong><small>${e(c.specialty || 'مربی برنامه تمرینی شما')}</small></div></div>` : empty('هنوز مربی تعیین نشده', 'پس از ثبت برنامه، مربی شما در این بخش نمایش داده می‌شود.');
  }
  function membershipCard() {
    const m = state.data.membership;
    return panel('عضویت من', `<div class="panel-body"><h3 class="plan-name">${e(m.plan || 'طرح ثبت نشده')}</h3><p class="muted small">${m.expiresAt ? `اعتبار تا ${dateText(m.expiresAt)}` : 'تاریخ اعتبار در دسترس نیست'}</p><div class="session-count"><strong>${numeric(m.remaining)} <small>جلسه باقی‌مانده</small></strong><span>از ${numeric(m.included)} جلسه</span></div>${m.included ? `<div class="progress-track" role="progressbar" aria-label="جلسات استفاده‌شده" aria-valuemin="0" aria-valuemax="${m.included}" aria-valuenow="${Math.min(m.used, m.included)}"><span style="width:${Math.min(100, Math.max(0, m.used / m.included * 100))}%"></span></div>` : ''}<div class="membership-foot"><span>${numeric(m.used)} جلسه استفاده‌شده</span></div></div>`, statusBadge(m.status));
  }
  function weekStrip() {
    const today = dateValue(state.data.today), start = new Date(today);
    start.setDate(start.getDate() - (start.getDay() + 1) % 7);
    return `<div class="week-strip" aria-label="برنامه این هفته">${Object.entries(weekdays).map(([key, label], index) => {
      const day = new Date(start); day.setDate(start.getDate() + index);
      const date = dateKey(day.toISOString()), training = state.data.program?.days.some(d => d.weekday === key);
      return `<div class="week-day ${date === state.data.today ? 'today' : ''} ${training ? 'training' : ''}"><span>${label}</span><strong>${day.toLocaleDateString('fa-IR', { timeZone: 'Asia/Tehran', day: 'numeric' })}</strong></div>`;
    }).join('')}</div><p class="week-legend">نقطه زیر روز: تمرین در برنامه مربی</p>`;
  }
  function dashboardView() {
    const d = state.data, m = d.membership, a = d.attendance, program = d.program;
    const day = program?.days[d.todayDay ?? d.nextDay], rest = d.todayDay === null;
    const last = a.visits[0];
    const date = `<div class="date-label">${icon('calendar')}<span>${dateText(d.today, { weekday: 'long' })}</span></div>`;
    const welcome = heading(`سلام، ${d.user.fullName.split(' ')[0]}`, 'مسیر تمرینت اینجاست. امروز هم یک قدم جلوتر.', date);
    const warning = m.status === 'expired' || (m.daysLeft != null && m.daysLeft <= 7) || (m.remaining != null && m.remaining <= 2);
    const metrics = `<div class="metric-grid">${metric('جلسات باقی‌مانده', numeric(m.remaining), m.remaining == null ? '' : 'جلسه', `${numeric(m.used)} از ${numeric(m.included)} جلسه استفاده شده`, 'barbell')}${metric('اعتبار عضویت', m.daysLeft == null ? 'نامشخص' : fa(Math.max(0, m.daysLeft)), m.daysLeft == null ? '' : 'روز', m.expiresAt ? `تا ${dateText(m.expiresAt)}` : 'نیاز به تأیید پذیرش', 'id')}${metric('حضور این ماه', a.available ? fa(a.month) : 'نامشخص', a.available ? 'بار' : '', a.available ? `${fa(a.week)} بار در این هفته` : 'اطلاعات دستگاه در دسترس نیست', 'calendar')}${metric('آخرین حضور', last ? dateText(last.checkIn) : 'ثبت نشده', '', last ? `ورود ساعت ${timeText(last.checkIn)}` : 'حضورهای ثبت‌شده اینجا نمایش داده می‌شود', 'door-enter', true)}</div>`;
    const workout = `<section class="panel workout-card"><div class="workout-feature"><div class="workout-copy"><span class="eyebrow">${icon('barbell')}${rest && program ? 'تمرین بعدی در برنامه' : 'تمرین امروز'}</span><h2>${e(day?.label || 'برنامه‌ات را شروع کن')}</h2><p>${e(program?.title || 'مربی، برنامه تمرینی تو را اینجا ثبت می‌کند.')}</p><div class="workout-meta">${day ? `<span>${icon('clipboard-list')}${fa(day.exercises.length)} حرکت</span><span>${icon('calendar')}${fa(program.days.length)} روز در هفته</span>` : '<span>متناسب با هدف و توانایی تو</span>'}</div>${program ? btn(state.workout ? 'ادامه تمرین' : 'شروع تمرین', 'start', d.nextDay, 'primary', 'barbell') : link('برنامه من', 'program', 'primary')}</div><img class="workout-photo" src="/assets/bodybuilding/image3-720.webp" alt="فضای تمرین و دستگاه‌های باشگاه لایف باکس" width="720" height="405" fetchpriority="high" /></div>${weekStrip()}</section>`;
    const visit = panel('آخرین حضورها', a.available && a.visits.length ? visitsMarkup(a.visits.slice(0, 3)) : empty(a.available ? 'هنوز حضوری ثبت نشده' : 'در انتظار اطلاعات دستگاه', 'ورود و خروج‌های ثبت‌شده توسط دستگاه باشگاه اینجا نمایش داده می‌شود.', '', 'door-enter'), link('همه حضورها ←', 'attendance'));
    const coach = panel('مربی کنار تو', `<div class="panel-body" style="padding-top:0">${coachSummary()}${d.coach?.notes ? `<p class="coach-note">${e(d.coach.notes.slice(0, 180))}</p>` : `<p class="coach-note">${d.coach ? 'برنامه را با راهنمایی مربی دنبال کن. برای هماهنگی می‌توانی درخواست تماس ثبت کنی.' : 'برای هماهنگی مربی به پذیرش مراجعه کن.'}</p>`}<div class="actions">${d.coach ? btn('تماس با مربی', 'request', 'coach_contact', 'text', 'arrow-left') : ''}</div></div>`, link('پروفایل مربی ←', 'coach'));
    return welcome + (warning ? `<div class="notice">${icon('alert-circle')}<span>اعتبار یا جلسات عضویت رو به پایان است. اطلاعات عضویتت را بررسی کن.</span><a href="#membership">مشاهده عضویت ←</a></div>` : '') + metrics + `<div class="dashboard-grid"><div>${workout}<div class="section-gap">${visit}</div></div><div class="dashboard-aside">${membershipCard()}${coach}${panel('جلسه بعدی', nextSessionMarkup(), link('همه جلسات ←', 'sessions'))}</div></div>`;
  }
  function programView() {
    const p = state.data.program;
    if (!p) return heading('برنامه من', '') + panel('برنامه تمرینی', empty('هنوز برنامه‌ای ثبت نشده', 'پس از ثبت برنامه توسط مربی، حرکات و روزهای تمرین اینجا نمایش داده می‌شود.'));
    const day = p.days[state.day] || p.days[0];
    return heading(p.title, '') + `<div class="tabs" aria-label="روزهای برنامه">${p.days.map((d, i) => btn(e(d.label), 'day', i, i === state.day ? 'active' : '')).join('')}</div>` + panel(e(day.label), exercisesMarkup(day.exercises));
  }
  function exercisesMarkup(exercises) {
    return `<div>${exercises.map((ex, i) => `<article class="exercise"><span class="exercise-number">${fa(i + 1)}</span><h3>${e(ex.name)}</h3><div class="exercise-stat">${fa(ex.sets)}<small>ست</small></div><div class="exercise-stat">${e(fa(ex.reps || 'ثبت نشده'))}<small>تکرار</small></div></article>`).join('')}</div>`;
  }

  function membershipView() {
    const m = state.data.membership;
    const history = state.data.membershipHistory;
    return heading('عضویت من', 'اعتبار، سهمیه جلسات و اطلاعات طرح فعلی.') +
      `<div class="two-col">${membershipCard()}${panel('اطلاعات عضویت', `<div class="panel-body">${facts([['شروع عضویت', dateText(m.startsAt)], ['پایان اعتبار', dateText(m.expiresAt)], ['جلسات طرح', numeric(m.included)], ['جلسات استفاده‌شده', numeric(m.used)], ['جلسات باقی‌مانده', numeric(m.remaining)], ['وضعیت', statusBadge(m.status)]])}</div>`)}</div>` +
      `<div class="section-gap">${panel('دسترسی چهره', `<div class="panel-body access-card">${icon('circle-check')}<div><h3>${m.faceRegistered ? 'ثبت‌شده' : 'ثبت نشده'}</h3><p>${m.faceRegistered ? 'وضعیت ثبت از دستگاه باشگاه دریافت می‌شود.' : 'برای ثبت چهره به پذیرش باشگاه مراجعه کنید.'}</p></div></div>`)}</div>` +
      `<div class="section-gap">${panel('سوابق تمدید عضویت', history.length ? table(['طرح', 'شروع', 'پایان اعتبار', 'جلسات', 'وضعیت ثبت'], history.map(p => [e(p.plan), dateText(p.startsAt), dateText(p.endsAt), numeric(p.sessions), statusBadge(p.status)])) : empty('تمدید پیشینی ثبت نشده', 'سوابق ثبت‌شده در پذیرش در این بخش نمایش داده می‌شود.'))}</div>`;
  }
  function visitsMarkup(visits) { return visits.map(v => `<div class="visit-row">${icon('door-enter')}<div><strong>${dateText(v.checkIn)}</strong><p>${dateText(v.checkIn, { weekday: 'long', day: undefined, month: undefined })}</p></div><span class="visit-times">${timeText(v.checkIn)} ← ${v.checkOut ? timeText(v.checkOut) : 'خروج ثبت نشده'}</span></div>`).join(''); }
  function attendanceView() {
    const a = state.data.attendance;
    return heading('حضور در باشگاه', 'ورود و خروج‌های شخصی، ثبت‌شده توسط دستگاه باشگاه.') + `<div class="metric-grid attendance-metrics">${metric('حضور این ماه', a.available ? fa(a.month) : 'نامشخص', 'بار', 'ماه جاری شمسی', 'calendar')}${metric('آخرین حضور', a.visits[0] ? dateText(a.visits[0].checkIn) : 'ثبت نشده', '', a.visits[0] ? timeText(a.visits[0].checkIn) : 'اطلاعاتی ثبت نشده', 'history', true)}</div>` + panel('سوابق حضور', a.available && a.visits.length ? visitsMarkup(a.visits) : empty(a.available ? 'هنوز حضوری ثبت نشده' : 'اطلاعات دستگاه در دسترس نیست', a.available ? 'پس از اولین ورود به باشگاه، سابقه حضور اینجا نمایش داده می‌شود.' : 'پس از اتصال یا همگام‌سازی دستگاه، اطلاعات به‌روز می‌شود.', '', 'door-enter'), '', a.total > 100 ? '۱۰۰ حضور اخیر نمایش داده می‌شود.' : 'حضور در باشگاه با جلسه تمرینی مربی متفاوت است.');
  }
  function sessionsView() {
    const upcoming = upcomingSessions(), rows = state.sessionFilter === 'upcoming' ? upcoming : state.data.sessions.filter(s => !upcoming.includes(s));
    return heading('جلسات من', 'زمان‌بندی جلسات خصوصی و نیمه‌خصوصی.') + `<div class="tabs" aria-label="زمان جلسات">${btn('جلسات پیش رو', 'session-filter', 'upcoming', state.sessionFilter === 'upcoming' ? 'active' : '')}${btn('جلسات گذشته', 'session-filter', 'past', state.sessionFilter === 'past' ? 'active' : '')}</div>` + panel(state.sessionFilter === 'upcoming' ? 'جلسات پیش رو' : 'سوابق جلسات', rows.length ? table(['تاریخ', 'ساعت', 'جلسه', 'مربی', 'وضعیت'], rows.map(s => [dateText(s.date), timeText(s.date), `${e(s.trainingDay || s.programTitle || 'تمرین')}<p class="muted small">${fa(s.duration)} دقیقه${s.group ? ` | ${e(s.group)}` : ''}</p>`, e(s.coachName), statusBadge(s.status)])) : empty('جلسه‌ای ثبت نشده', '', '', 'calendar'));
  }
  function coachView() {
    const c = state.data.coach;
    if (!c) return heading('مربی من', 'همراه تو در مسیر تمرین و پیشرفت.') + panel('مربی', empty('هنوز مربی تعیین نشده', 'پس از ثبت برنامه، اطلاعات مربی اینجا نمایش داده می‌شود.', '', 'users'));
    return heading('مربی من', 'مربی برنامه تمرینی تو.', btn('تماس با مربی', 'request', 'coach_contact', 'primary')) + panel('مربی برنامه من', `<div class="panel-body" style="padding-top:0">${coachSummary()}<p class="muted small">${e(c.bio || 'مربی اختصاصی برنامه تمرینی شما')}</p><div style="margin-top:24px">${facts([['برنامه فعلی', e(state.data.program.title)]])}</div><div class="actions">${link('مشاهده برنامه', 'program')}</div></div>`);
  }

  function paymentsView() {
    const d = state.data;
    return heading('پرداخت‌ها و رسیدها', 'پرداخت‌های ثبت‌شده برای حساب شخصی شما.') + panel('وضعیت حساب', `<div class="panel-body"><div class="account-values"><strong>${d.balance === 0 ? 'بدون بدهی' : d.balance == null ? 'در دسترس نیست' : money(d.balance) + ' تومان'}</strong>${d.balance > 0 ? badge('مانده قابل پرداخت', 'warning') : d.balance === 0 ? badge('تسویه‌شده', 'success') : ''}</div></div>`) + `<div class="section-gap">${panel('سوابق پرداخت', d.payments.length ? table(['طرح', 'مبلغ (تومان)', 'تاریخ', 'روش', 'وضعیت', 'رسید'], d.payments.map(p => [e(p.plan), money(p.amount), dateText(p.date), e(p.method), statusBadge(p.status), btn('مشاهده رسید', 'receipt', p.id, 'text')])) : empty('پرداختی در سوابق دریافت‌شده نیست', d.paymentsAvailable ? 'پرداخت‌های ثبت‌شده در پذیرش اینجا نمایش داده می‌شود.' : 'اطلاعات پرداخت از پذیرش هنوز در دسترس نیست.', '', 'wallet'))}</div>`;
  }
  function notificationsView() {
    const list = state.data.notifications;
    return heading('اعلان‌ها', 'به‌روزرسانی‌های برنامه، عضویت و جلسات شما.', list.some(n => !n.read) ? btn('خواندن همه', 'read-all', '', '', 'circle-check') : '') + panel('آخرین به‌روزرسانی‌ها', list.length ? list.map(n => `<div class="notification-row ${n.read ? 'read' : ''}">${icon('bell')}<div><strong>${e(n.title)}</strong><p>${e(n.description)}</p></div>${n.read ? badge('خوانده‌شده') : badge('جدید', 'warning')}${btn('مشاهده', 'notification', n.id, 'text')}</div>`).join('') : empty('اعلان جدیدی نیست', 'وقتی اطلاعات برنامه یا عضویت به‌روز شود، اینجا به تو اطلاع می‌دهیم.', '', 'bell'));
  }
  function profileView() {
    const u = state.data.user;
    return heading('پروفایل من', 'اطلاعات ثبت‌نام و تنظیمات حساب شخصی.') + panel('اطلاعات حساب', `<div class="panel-body">${facts([['نام و نام خانوادگی', e(u.fullName)], ['شماره موبایل', `<span dir="ltr">${e(fa(u.mobile))}</span>`], ['کد ملی', e(u.nationalId ? fa(u.nationalId) : 'ثبت نشده')], ['سن', numeric(u.age)], ['جنسیت', e({male:'مرد',female:'زن'}[u.gender] || u.gender || 'ثبت نشده')], ['آدرس', e(u.address || 'ثبت نشده')]], true)}</div>`) + `<div class="section-gap">${panel('تنظیمات حساب', `<div class="panel-body" style="padding:0"><div class="settings-row"><div><h3>نشان اعلان‌های جدید</h3><p>نمایش تعداد اعلان‌های خوانده‌نشده در منو</p></div><label><span class="small">فعال</span> <input id="notification-setting" type="checkbox" aria-label="نمایش نشان اعلان‌های جدید" ${state.data.notificationsEnabled ? 'checked' : ''} /></label></div></div>`)}</div>`;
  }

  function workoutView() {
    const w = state.workout;
    if (!w) return heading('تمرین من', '') + panel('تمرین', state.data.program ? empty('برنامه بعدی آماده است', state.data.program.days[state.data.nextDay]?.label || state.data.program.title, btn('شروع تمرین', 'start', state.data.nextDay, 'primary', 'barbell'), 'barbell') : empty('هنوز برنامه‌ای ثبت نشده', '', link('برنامه من', 'program')));
    return heading(w.trainingDay, '') + `<div id="workout-error" class="form-error" role="alert"></div>` + panel('حرکات تمرین', exercisesMarkup(w.exercises.map(x => ({ name: x.name, sets: x.sets.length, reps: x.prescription?.reps })))) + `<div class="actions">${btn('پایان تمرین', 'finish-workout', '', 'primary', 'circle-check')}</div>`;
  }
  function openDialog(title, content, onSubmit) {
    $('#dialog-title').textContent = title;
    $('#dialog-content').innerHTML = onSubmit ? `<form id="dialog-form">${content}<p class="form-error" role="alert" id="dialog-error"></p><div class="dialog-actions">${btn('انصراف', 'close-dialog')}<button class="button primary" type="submit">ثبت</button></div></form>` : content;
    if (onSubmit) $('#dialog-form').addEventListener('submit', async ev => {
      ev.preventDefault(); const form = ev.currentTarget, submit = $('button[type=submit]', form); submit.disabled = true; $('#dialog-error').textContent = '';
      try { await onSubmit(Object.fromEntries(new FormData(form))); dialog.close(); }
      catch (err) { $('#dialog-error').textContent = err.message; }
      finally { submit.disabled = false; }
    });
    dialog.showModal();
  }
  function requestDialog(kind) {
    openDialog(requestKinds[kind] || 'درخواست جدید', `<div class="form-grid"><label class="field">نوع درخواست<select name="kind">${options(requestKinds, kind)}</select></label><label class="field">توضیحات<textarea name="message" required maxlength="3000"></textarea><small>این درخواست برای بررسی به پذیرش ارسال می‌شود. ثبت درخواست، عضویت یا زمان جلسه را تغییر نمی‌دهد.</small></label></div>`, async data => {
      const result = await api('/api/member/requests', 'POST', data); state.data.requests.unshift(result.request); toast('درخواست تماس با مربی ثبت شد.');
    });
  }
  async function finishWorkout() {
    const result = await api(`/api/member/workouts/${state.workout.id}`, 'PATCH', { finish: true });
    const index = state.data.workouts.findIndex(w => w.id === result.workout.id);
    if (index >= 0) state.data.workouts[index] = result.workout;
    state.workout = null;
    location.hash = 'dashboard';
    toast('تمرین پایان یافت. خسته نباشی!');
  }
  document.addEventListener('change', async ev => {
    if (ev.target.id === 'notification-setting') {
      const input = ev.target, previous = state.data.notificationsEnabled; input.disabled = true;
      try { await api('/api/member/preferences', 'PATCH', { notificationsEnabled: input.checked }); state.data.notificationsEnabled = input.checked; updateNotifications(); toast('تنظیم اعلان ذخیره شد.'); }
      catch (err) { input.checked = previous; toast(err.message); } finally { input.disabled = false; }
    }
  });
  async function action(button) {
    const id = button.dataset.id, name = button.dataset.action;
    if (name === 'retry') return load();
    if (name === 'request') return requestDialog(id);
    if (name === 'close-dialog') return dialog.close();
    if (name === 'day') { state.day = Number(id); render(); return; }
    if (name === 'session-filter') { state.sessionFilter = id; render(); return; }
    if (name === 'start') {
      if (!state.workout) { const result = await api('/api/member/workouts', 'POST', { dayIndex: Number(id) }); state.workout = result.workout; state.data.workouts.unshift(result.workout); }
      if (location.hash === '#workout') render(); else location.hash = 'workout';
    }
    if (name === 'finish-workout') return finishWorkout();
    if (name === 'receipt') {
      const p = state.data.payments.find(p => p.id === id);
      openDialog('رسید پرداخت', facts([['نام عضو', e(state.data.user.fullName)], ['طرح', e(p.plan)], ['مبلغ', money(p.amount) + ' تومان'], ['تاریخ', dateText(p.date)], ['مرجع پرداخت', e(p.reference || 'ثبت پذیرش')], ['وضعیت', statusBadge(p.status)]]) + `<div class="actions"><a class="button primary" href="/api/member/receipts/${encodeURIComponent(p.id)}" download>${icon('download')}دانلود رسید</a></div>`);
    }
    if (name === 'notification' || name === 'read-all') {
      const rows = name === 'read-all' ? state.data.notifications : state.data.notifications.filter(n => n.id === id);
      await api('/api/member/preferences', 'PATCH', { read: rows.map(n => n.id) }); rows.forEach(n => { n.read = true; }); updateNotifications();
      if (name === 'notification') location.hash = rows[0].view; else render();
    }
  }
  document.addEventListener('click', async ev => {
    const button = ev.target.closest('[data-action]'); if (!button || button.disabled) return;
    button.disabled = true;
    try { await action(button); }
    catch (err) { if (currentView() === 'workout' && $('#workout-error')) $('#workout-error').textContent = err.message; else toast(err.message); }
    finally { button.disabled = false; }
  });
  function closeMenu() { $('#member-sidebar').classList.remove('open'); $('#sidebar-shade').hidden = true; $('#menu-button').setAttribute('aria-expanded', 'false'); document.body.style.overflow = ''; }
  $('#menu-button').addEventListener('click', () => { const open = !$('#member-sidebar').classList.contains('open'); $('#member-sidebar').classList.toggle('open', open); $('#sidebar-shade').hidden = !open; $('#menu-button').setAttribute('aria-expanded', String(open)); document.body.style.overflow = open ? 'hidden' : ''; if (open) $('nav a', $('#member-sidebar')).focus(); });
  $('#sidebar-shade').addEventListener('click', () => { closeMenu(); $('#menu-button').focus(); });
  document.addEventListener('keydown', ev => {
    if ($('#member-sidebar').classList.contains('open')) {
      if (ev.key === 'Escape') { closeMenu(); $('#menu-button').focus(); }
      if (ev.key === 'Tab') { const items = $$('a,button', $('#member-sidebar')), first = items[0], last = items.at(-1); if (ev.shiftKey && document.activeElement === first) { ev.preventDefault(); last.focus(); } else if (!ev.shiftKey && document.activeElement === last) { ev.preventDefault(); first.focus(); } }
    }
  });
  $('#close-dialog').addEventListener('click', () => dialog.close());
  let theme;
  try { theme = localStorage.getItem('lifebox-member-theme'); } catch { /* Storage can be unavailable in private browsers. */ }
  const media = matchMedia('(prefers-color-scheme: dark)');
  function applyTheme(value) { document.documentElement.dataset.theme = value; $('#theme-button').setAttribute('aria-label', value === 'dark' ? 'تغییر به ظاهر روشن' : 'تغییر به ظاهر تاریک'); $('#theme-button img').src = `/assets/icons/${value === 'dark' ? 'sun' : 'moon'}.svg`; }
  applyTheme(theme === 'dark' || theme === 'light' ? theme : media.matches ? 'dark' : 'light');
  media.addEventListener('change', ev => { if (!theme) applyTheme(ev.matches ? 'dark' : 'light'); });
  $('#theme-button').addEventListener('click', () => { theme = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark'; applyTheme(theme); try { localStorage.setItem('lifebox-member-theme', theme); } catch { /* Appearance remains available for this session. */ } });
  $('#logout-button').addEventListener('click', async () => { try { await api('/api/logout', 'POST', {}); window.location.replace('/login'); } catch (err) { toast(err.message); } });
  window.addEventListener('hashchange', async () => { closeMenu(); render(); main.focus({ preventScroll: true }); window.scrollTo(0, 0); });
  load();
})();
