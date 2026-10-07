/* Owner UI uses existing Django sessions/CSRF and read-only operational insights. */
(() => {
  const isOwnerPanel = document.body.dataset.panelRole === 'owner';
  const apiRoot = isOwnerPanel ? '/api/owner' : '/api/admin';
  let remoteSync = false, members = [], plans = [], overview = null;
  let editingMember, editingPlan, refreshing = false, refreshPending = false, memberPage = 1;
  let activityAttendance = [], attendanceMember = null, attendanceRequest = 0, activitySearchTimer;
  let memberFilter = 'all', followupFilter = 'expiring';
  const html = escapeHtml;
  const number = value => value == null ? '—' : new Intl.NumberFormat('fa-IR').format(value);
  const clock = value => new Date(value).toLocaleTimeString('fa-IR', {timeZone:'Asia/Tehran', hour:'2-digit', minute:'2-digit'});
  const stamp = value => value ? `${formatDate(value)} · ${toFa((value.split('T')[1] || value.split(' ')[1] || '').slice(0,5))}` : '—';
  const empty = (cols, message) => `<tr><td colspan="${cols}" class="empty-state">${html(message)}</td></tr>`;
  const fullName = m => `${m.firstName || ''} ${m.lastName || ''}`.trim() || m.mobile;
  const initials = m => fullName(m).split(/\s+/).slice(0,2).map(v => v[0]).join('');
  const feedback = (message, failed = false) => {
    $('#owner-feedback').textContent = message;
    $('#owner-feedback').classList.toggle('error', failed);
  };
  const labels = {active:'فعال', expiring:'رو به پایان', expired:'پایان‌یافته', pending:'بدون عضویت حضوری', unknown:'تاریخ نامشخص'};
  const views = {
    overview:['نمای کلی','باشگاه، در یک نگاه','وضعیت امروز، پرداخت‌ها و اعضای نیازمند پیگیری.'],
    members:['اعضای باشگاه','مدیریت اعضای باشگاه','وضعیت عضویت و موارد نیازمند پیگیری را بررسی کنید.'],
    activity:['ورود و حضور','رفت‌وآمد باشگاه','تاریخچه حضور اعضا و ورود به حساب سایت.'],
    plans:['پلن‌ها و قیمت‌ها','پلن‌های عضویت','پلن‌های باشگاه، قیمت‌ها و ظرفیت جلسات.'],
    payments:['پرداخت‌های تمدید','وضعیت پرداخت‌ها','سوابق تمدید عضویت و بدهی اعضا.'],
    audit:['تغییرات اخیر','تاریخچه مدیریت','آخرین اقدامات ثبت‌شده در پنل باشگاه.']
  };
  if(!isOwnerPanel) views.overview[2]='حضور امروز، بدهی‌ها، تمدیدها و اعضای نیازمند پیگیری.';
  function matches(m, filter) {
    if (m.role !== 'member') return false;
    switch (filter) {
      case 'active': return ['active','expiring'].includes(m.membershipStatus);
      case 'expiring': return m.membershipStatus === 'expiring';
      case 'expired': return m.membershipStatus === 'expired';
      case 'debt': return m.debt > 0;
      case 'inactive': return m.inactive;
      case 'attention': return ['expiring','expired'].includes(m.membershipStatus) || m.debt > 0 || m.inactive;
      default: return true;
    }
  }
  function visibleMembers() {
    const query = $('#owner-search').value.trim().toLocaleLowerCase();
    return members.filter(m => matches(m,memberFilter) && (fullName(m).toLocaleLowerCase().includes(query) || normalizeDigits(m.mobile).includes(normalizeDigits(query)) || (m.nationalId || '').includes(normalizeDigits(query))));
  }
  function setFilter(filter) {
    memberFilter = filter;
    memberPage = 1;
    $$('[data-member-filter]').forEach(b => {
      const active = b.dataset.memberFilter === filter;
      b.classList.toggle('active',active); b.setAttribute('aria-pressed',String(active));
    });
    renderMembers();
  }
  function renderMembers() {
    const allRows = visibleMembers();
    const pageCount = Math.max(1,Math.ceil(allRows.length/20));
    memberPage = Math.max(1,Math.min(memberPage,pageCount));
    const rows = allRows.slice((memberPage-1)*20,memberPage*20);
    $('#member-page').textContent = `صفحه ${number(memberPage)} از ${number(pageCount)}`;
    $('#previous-members').disabled = memberPage === 1;
    $('#next-members').disabled = memberPage === pageCount;
    $('#member-count').textContent = `${number(allRows.length)} عضو از ${number(members.filter(m => m.role === 'member').length)} عضو مجموعه`;
    $('#owner-members').innerHTML = rows.map(m => `<tr>
      <td><div class="table-name"><span class="initial-avatar" aria-hidden="true">${html(initials(m))}</span><div><strong>${html(fullName(m))}</strong><small>${html(toFa(m.mobile))} · ${html(toFa(m.key.replace(':',' #')))}</small></div></div></td>
      <td>${html(m.plan || 'بدون پلن')}<small class="status-badge ${html(m.membershipStatus || 'unknown')}">${html(labels[m.membershipStatus] || 'نامشخص')}${m.expiresAt ? ' · '+html(formatDate(m.expiresAt)) : ''}</small></td>
      <td>${number(m.remainingSessions)}<small>${number(m.sessionsUsed)} جلسه مصرف‌شده</small></td>
      <td>${html(m.lastVisit ? formatDate(m.lastVisit) : overview?.attendanceAvailable ? 'سابقه‌ای ثبت نشده' : 'در دسترس نیست')}</td>
      <td class="money-cell">${number(m.debt)}</td>
      <td>${html(m.status === 'gym' ? 'فقط حضوری' : statusLabel(m.status))}</td>
      <td><div class="owner-actions">${m.remotePending ? '<small>در انتظار همگام‌سازی</small>' : `<button class="table-action" data-edit-member="${html(m.key)}" aria-label="مشاهده و ویرایش ${html(fullName(m))}">مشاهده و ویرایش</button>`}${m.webId ? `<button class="table-action" data-status-member="${m.webId}" data-status="${m.status === 'suspended' ? 'active' : 'suspended'}">${m.status === 'suspended' ? 'فعال‌سازی سایت' : 'تعلیق سایت'}</button>` : ''}</div></td>
    </tr>`).join('') || empty(7,'عضوی با این فیلتر پیدا نشد. فیلتر یا جست‌وجو را تغییر دهید.');
  }
  function renderPlans() {
    if (!isOwnerPanel) return;
    $('#owner-plans').innerHTML = plans.map(p => `<article class="owner-plan ${p.isActive ? '' : 'inactive'}"><span class="status-badge ${p.isActive ? 'active' : ''}">${p.isActive ? 'فعال' : 'غیرفعال'} · ${{all:'همه',male:'آقایان',female:'بانوان'}[p.gender] || ''}</span><h3>${html(p.name)}</h3><strong>${number(p.price)} <small>تومان</small></strong><p>${number(p.sessionsPerMonth)} جلسه در ماه</p>${p.remotePending ? '<small>در انتظار اعمال در باشگاه</small>' : `<button class="table-action" data-edit-plan="${p.id}">ویرایش پلن</button>`}</article>`).join('') || '<p class="empty-state">هنوز پلنی ثبت نشده است. اولین پلن را اضافه کنید.</p>';
  }
  function renderFollowups() {
    const rows = members.filter(m => followupFilter === 'expiring' ? matches(m,'expiring') || matches(m,'expired') : matches(m,followupFilter));
    rows.sort((a,b) => followupFilter === 'debt' ? b.debt-a.debt : followupFilter === 'inactive' ? (a.lastVisit || '').localeCompare(b.lastVisit || '') : (a.daysLeft ?? 999)-(b.daysLeft ?? 999));
    $('#attention-count').textContent = number(rows.length);
    $('#followup-all').dataset.filterLink = followupFilter === 'expiring' ? 'attention' : followupFilter;
    $('#followup-members').innerHTML = rows.slice(0,3).map(m => {
      const detail = followupFilter === 'debt' ? `${number(m.debt)} تومان بدهی` : followupFilter === 'inactive' ? `آخرین مراجعه: ${formatDate(m.lastVisit)}` : m.membershipStatus === 'expired' ? 'عضویت پایان یافته است' : `${number(m.daysLeft)} روز تا پایان عضویت`;
      return `<li><span class="initial-avatar" aria-hidden="true">${html(initials(m))}</span><div class="member-copy"><strong>${html(fullName(m))}</strong><small>${html(detail)}</small></div><button class="table-action" data-edit-member="${html(m.key)}" aria-label="بررسی ${html(fullName(m))}">بررسی</button></li>`;
    }).join('') || '<li class="empty-state">موردی برای پیگیری در این گروه نیست.</li>';
  }
  function paymentRows(rows, detailed=false) {
    return rows.map(p => `<tr><td><div class="table-name"><span class="initial-avatar" aria-hidden="true">${html(p.name.split(/\s+/).map(v => v[0]).slice(0,2).join(''))}</span><strong>${html(p.name)}</strong></div></td><td title="${html(p.plan)}">${html(p.plan)}</td><td class="money-cell">${number(p.amount)}</td><td>${html(detailed ? stamp(p.at) : formatDate(p.at))}</td>${detailed ? `<td dir="ltr">${html(p.reference || '—')}</td>` : ''}</tr>`).join('') || empty(detailed ? 5 : 4,overview?.paymentsAvailable ? 'پرداخت تمدیدی ثبت نشده است.' : 'سوابق پرداخت در دسترس نیست.');
  }
  function renderOverview() {
    const m = overview.metrics;
    const value = (id,v) => { const target=$(id); if(target) target.textContent = number(v); };
    value('#metric-active',m.active+m.expiring); value('#metric-members',m.total); value('#nav-members',m.total);
    value('#metric-expiring',m.expiring); value('#metric-revenue',m.monthPayments); value('#metric-today-revenue',m.todayPayments);
    value('#metric-visits',m.todayAttendance); value('#metric-inside',m.inside);
    value('#metric-debt-members',m.debtMembers);
    value('#attendance-today',m.todayAttendance);
    $('#attendance-inside').textContent = m.inside == null ? 'اطلاعات در دسترس نیست' : `${number(m.inside)} نفر در باشگاه`;
    value('#payment-today',m.todayPayments); value('#payment-month',m.monthPayments); value('#payment-debt',m.debt);
    $('#payment-debt-count').textContent = `${number(m.debtMembers)} عضو دارای بدهی`;
    const attention = members.filter(m => matches(m,'attention')).length;
    $('#attention-title').textContent = attention ? `${number(attention)} عضو به پیگیری شما نیاز دارند` : 'همه‌چیز برای ادامه روز آماده است';
    $('#attention-description').textContent = `${number(m.expired)} عضویت پایان‌یافته · ${number(m.expiring)} عضویت رو به پایان · ${number(m.debtMembers)} عضو دارای بدهی${m.unknown ? ` · ${number(m.unknown)} تاریخ نامشخص` : ''}`;
    $('.notification-dot').hidden = attention === 0;
    $('#recent-payments').innerHTML = paymentRows(overview.payments.slice(0,4));
    $('#owner-payments').innerHTML = paymentRows(overview.payments,true);
    $('#export-payments').disabled = !overview.paymentsAvailable || !overview.payments.length;
    renderFollowups(); drawCharts();
  }
  function renderActivity(activity) {
    activityAttendance = activity.attendance;
    $('#activity-visits').textContent = activity.attendanceAvailable ? number(activity.visitCount) : '—';
    $('#metric-visitors').textContent = activity.attendanceAvailable ? `${number(activity.visitors)} عضو یکتا` : 'اطلاعات حضور در دسترس نیست';
    $('#metric-logins').textContent = number(activity.loginCount);
    $('#metric-login-users').textContent = `${number(activity.loginUsers)} کاربر یکتا`;
    $('#activity-range').textContent = `${formatDate(activity.start)} تا ${formatDate(activity.end)} · ساعت تهران`;
    $('#attendance-warning').textContent = activity.syncedAt ? `آخرین دریافت از باشگاه: ${new Date(activity.syncedAt).toLocaleString('fa-IR',{timeZone:'Asia/Tehran'})}` : (activity.attendanceAvailable ? '' : 'اطلاعات حضور باشگاه هنوز دریافت نشده است.');
    $('#owner-attendance').innerHTML = activity.attendance.map(a => `<tr><td><strong>${html(a.full_name)}</strong><small>${html(toFa(a.mobile))}</small></td><td>${html(stamp(a.checked_in_at))}</td><td>${a.checked_out_at ? html(stamp(a.checked_out_at)) : '<span class="status-badge active">داخل باشگاه</span>'}</td><td><button class="table-action" data-attendance-member="${Number(a.member_id)}" aria-label="تردد ${html(a.full_name)}">تردد</button></td></tr>`).join('') || empty(4,activity.attendanceAvailable ? (activity.search ? 'با این نام یا شماره موبایل، مراجعه‌ای در این بازه پیدا نشد.' : 'در این بازه مراجعه‌ای ثبت نشده است.') : 'اطلاعات حضور در دسترس نیست.');
    $('#owner-logins').innerHTML = activity.logins.map(l => `<tr><td>${html(l.name)}</td><td>${html(toFa(l.mobile))}</td><td>${html(formatDate(l.at))} · ${html(clock(l.at))}</td></tr>`).join('') || empty(3,'در این بازه ورود به سایت ثبت نشده است.');
    $('#owner-audit').innerHTML = activity.audit.map(a => `<li><span>${html(a.action)}</span><small>${html(formatDate(a.at))} · ${html(clock(a.at))}</small></li>`).join('') || '<li class="empty-state">هنوز تغییری ثبت نشده است.</li>';
  }
  async function refresh() {
    if (refreshing) { refreshPending = true; return; }
    refreshing = true; $('#refresh-owner').disabled = true;
    $('#owner-date').textContent=new Intl.DateTimeFormat('fa-IR',{weekday:'long',day:'numeric',month:'long',year:'numeric',timeZone:'Asia/Tehran'}).format(new Date());
    $('#owner-content').setAttribute('aria-busy','true');
    try {
      const period = $('#activity-period').value;
      const search = $('#activity-search').value.trim();
      const [directory,catalog,activity,insights] = await Promise.all([api(`${apiRoot}/members`),isOwnerPanel ? api(`${apiRoot}/plans`) : Promise.resolve({plans:[]}),api(`${apiRoot}/activity?${new URLSearchParams({period,search})}`),api(`${apiRoot}/overview`)]);
      remoteSync = Boolean(directory.remoteSync); overview = insights;
      const details = new Map(insights.members.map(m => [m.key,m]));
      members = directory.members.map(m => ({...m,...details.get(m.key)}));
      plans = catalog.plans;
      if(isOwnerPanel) $('#new-plan').disabled = false;
      renderMembers(); renderPlans(); renderActivity(activity); renderOverview();
      feedback(`آخرین دریافت: ${clock(new Date().toISOString())} · هر ۳۰ ثانیه${activity.syncedAt ? ` · آخرین همگام‌سازی باشگاه: ${formatDate(activity.syncedAt)} ${clock(activity.syncedAt)}` : ''}`);
      if (!overview.attendanceAvailable || !overview.paymentsAvailable) feedback('بعضی سوابق باشگاه در دسترس نیست؛ علامت — یعنی داده دریافت نشده است.');
    } catch(e) { feedback(`${e.message}${overview ? ' · آخرین اطلاعات دریافت‌شده نمایش داده می‌شود.' : ' · برای تلاش دوباره، به‌روزرسانی را بزنید.'}`,true); }
    finally { refreshing = false; $('#refresh-owner').disabled = false; $('#owner-content').setAttribute('aria-busy','false'); if(refreshPending){refreshPending=false;refresh();} }
  }
  async function openAttendance(memberId, page = 1) {
    const dialog = $('#attendance-dialog');
    if (!dialog.open) {
      const member = activityAttendance.find(a => a.member_id === Number(memberId));
      if (!member) return;
      attendanceMember = {id:Number(memberId),name:member.full_name,page:1};
      $('#attendance-period').value = $('#activity-period').value;
      $('#attendance-title').textContent = `تردد ${member.full_name}`;
      dialog.showModal();
    }
    const requestId = ++attendanceRequest;
    const period = $('#attendance-period').value;
    $('#attendance-summary').textContent = 'در حال دریافت سوابق…';
    $('#attendance-range').textContent = '';
    $('#attendance-sync').textContent = '';
    $('#attendance-history').innerHTML = empty(3,'در حال دریافت سوابق…');
    $('#attendance-page').textContent = '';
    $('#attendance-previous').disabled = $('#attendance-next').disabled = true;
    dialog.setAttribute('aria-busy','true');
    try {
      const data = await api(`${apiRoot}/attendance/${attendanceMember.id}?${new URLSearchParams({page,period})}`);
      if (requestId !== attendanceRequest || !dialog.open) return;
      attendanceMember.page = data.page;
      $('#attendance-range').textContent = `${formatDate(data.start)} تا ${formatDate(data.end)} · ساعت تهران`;
      $('#attendance-summary').textContent = data.attendanceAvailable ? `${number(data.visitCount)} مراجعه ثبت‌شده` : 'سوابق حضور در دسترس نیست.';
      $('#attendance-sync').textContent = data.syncedAt ? `آخرین دریافت از باشگاه: ${formatDate(data.syncedAt)} · ${clock(data.syncedAt)}` : '';
      $('#attendance-history').innerHTML = data.attendance.map((a,i) => `<tr><td>${number((data.page-1)*data.pageSize+i+1)}</td><td>${html(stamp(a.checked_in_at))}</td><td>${a.checked_out_at ? html(stamp(a.checked_out_at)) : '<span class="status-badge active">داخل باشگاه</span>'}</td></tr>`).join('') || empty(3,data.attendanceAvailable ? 'در این بازه مراجعه‌ای ثبت نشده است.' : 'سوابق حضور هنوز دریافت نشده است.');
      $('#attendance-page').textContent = `صفحه ${number(data.page)} از ${number(Math.max(1,Math.ceil(data.visitCount/data.pageSize)))}`;
      $('#attendance-previous').disabled = data.page === 1;
      $('#attendance-next').disabled = !data.hasNext;
    } catch(e) {
      if(requestId !== attendanceRequest || !dialog.open)return;
      $('#attendance-summary').textContent = e.message;
      $('#attendance-history').innerHTML = empty(3,'دریافت سوابق ناموفق بود؛ دوباره تلاش کنید.');
    } finally {
      if(requestId === attendanceRequest)dialog.setAttribute('aria-busy','false');
    }
  }
  function prepareCanvas(canvas) {
    if (!canvas || !canvas.clientWidth) return null;
    const ratio = window.devicePixelRatio || 1;
    const width = canvas.clientWidth, height = canvas.clientHeight;
    canvas.width = Math.round(width*ratio); canvas.height = Math.round(height*ratio);
    const ctx = canvas.getContext('2d'); if (!ctx) return null;
    ctx.scale(ratio,ratio);
    const style = getComputedStyle(document.body);
    return {ctx,width,height,muted:style.getPropertyValue('--muted'),border:style.getPropertyValue('--border'),accent:style.getPropertyValue('--accent'),surface:style.getPropertyValue('--surface')};
  }
  function drawRevenue() {
    if (!overview || !isOwnerPanel) return;
    const days = Number($('#chart-period').value);
    const series = overview.series.slice(-days), values = series.map(d => d.payments || 0);
    const total = values.reduce((a,b) => a+b,0);
    $('#chart-total').textContent = overview.paymentsAvailable ? number(total) : '—';
    $('#revenue-empty').hidden = overview.paymentsAvailable && total > 0;
    $('#revenue-empty').textContent = overview.paymentsAvailable ? 'هنوز پرداختی در این بازه ثبت نشده است.' : 'سوابق پرداخت در دسترس نیست.';
    const canvas = $('#revenue-chart');
    canvas.setAttribute('aria-label',`پرداخت تمدید ${number(days)} روز اخیر: ${number(overview.paymentsAvailable ? total : null)} تومان. جزئیات در بخش پرداخت‌ها.`);
    const data = prepareCanvas(canvas); if (!data) return;
    const {ctx,width,height,muted,border,accent} = data;
    const left=48,right=14,top=24,bottom=30;
    const plotWidth=width-left-right,plotHeight=height-top-bottom;
    const maximum = Math.max(...values,1), unit = maximum >= 1000000 ? 1000000 : 1;
    const cap = Math.ceil(maximum/4/unit)*4*unit;
    ctx.font='10px OwnerVazirmatn'; ctx.textBaseline='middle';
    ctx.fillStyle=muted;ctx.textAlign='right';ctx.fillText(unit === 1000000 ? 'میلیون' : 'تومان',left-8,7);
    for(let i=0;i<=4;i++) {
      const y=top+i*plotHeight/4;
      ctx.strokeStyle=border; ctx.setLineDash([3,5]);ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(width-right,y);ctx.stroke();ctx.setLineDash([]);
      ctx.fillStyle=muted;ctx.textAlign='right';ctx.fillText(number(cap*(4-i)/4/unit),left-10,y);
    }
    const points=values.map((v,i)=>[left+i*plotWidth/Math.max(1,values.length-1),top+plotHeight*(1-v/cap)]);
    const gradient=ctx.createLinearGradient(0,top,0,height-bottom);
    gradient.addColorStop(0,'rgba(233,196,45,.22)');gradient.addColorStop(1,'rgba(233,196,45,0)');
    ctx.beginPath();ctx.moveTo(points[0][0],height-bottom);points.forEach(([x,y])=>ctx.lineTo(x,y));ctx.lineTo(points.at(-1)[0],height-bottom);ctx.closePath();ctx.fillStyle=gradient;ctx.fill();
    ctx.beginPath();points.forEach(([x,y],i)=>i?ctx.lineTo(x,y):ctx.moveTo(x,y));ctx.strokeStyle=accent;ctx.lineWidth=2.5;ctx.lineJoin='round';ctx.stroke();
    const last=points.at(-1);ctx.beginPath();ctx.arc(last[0],last[1],4,0,Math.PI*2);ctx.fillStyle=accent;ctx.fill();
    ctx.fillStyle=muted;ctx.textAlign='center';
    const count=Math.min(5,series.length);
    for(let i=0;i<count;i++){const index=Math.round(i*(series.length-1)/Math.max(1,count-1));const label=new Intl.DateTimeFormat('fa-IR',{day:'numeric',month:'short',timeZone:'Asia/Tehran'}).format(new Date(series[index].date+'T12:00:00+03:30'));ctx.fillText(label,points[index][0],height-10);}
  }
  function drawAttendance() {
    if (!overview) return;
    const canvas=$('#attendance-chart'),data=prepareCanvas(canvas);if(!data)return;
    const {ctx,width,height,muted,border,accent}=data,values=overview.hours;
    canvas.setAttribute('aria-label',overview.attendanceAvailable ? `ورودی امروز: ${number(overview.metrics.todayAttendance)} نفر. ${values.filter(v=>v.count).map(v=>`ساعت ${number(v.hour)}: ${number(v.count)} ورود`).join('، ')}` : 'اطلاعات حضور در دسترس نیست');
    const left=7,right=7,bottom=26,top=14,plotHeight=height-top-bottom,slot=(width-left-right)/values.length;
    const cap=Math.max(...values.map(v=>v.count),1);
    for(let i=0;i<3;i++){let y=top+i*plotHeight/2;ctx.strokeStyle=border;ctx.setLineDash([2,4]);ctx.beginPath();ctx.moveTo(left,y);ctx.lineTo(width-right,y);ctx.stroke();ctx.setLineDash([]);}
    values.forEach((v,i)=>{const h=v.count/cap*plotHeight;ctx.fillStyle=v.count===cap ? accent : 'rgba(233,196,45,.4)';ctx.beginPath();ctx.roundRect(left+i*slot+2,top+plotHeight-h,Math.max(2,slot-5),Math.max(h,2),3);ctx.fill();});
    ctx.font='9px OwnerVazirmatn';ctx.fillStyle=muted;ctx.textAlign='center';[0,4,8,12,17].forEach(i=>ctx.fillText(toFa(values[i].hour+':۰۰'),left+(i+.5)*slot,height-9));
  }
  function drawCharts(){drawRevenue();drawAttendance();}
  function navigate() {
    const key = window.location.hash.slice(1) || 'overview';
    const selected = views[key] && (isOwnerPanel || key !== 'plans') ? key : 'overview';
    $$('[data-view]').forEach(section=>section.hidden=section.id!==selected);
    $$('.side-nav a[href^="#"]').forEach(a=>{const active=a.getAttribute('href')===`#${selected}`;a.classList.toggle('active',active);if(active)a.setAttribute('aria-current','page');else a.removeAttribute('aria-current');});
    const [label,title,description]=views[selected];
    $('#view-label').textContent=label;$('#view-title').textContent=title;$('#view-description').textContent=description;
    document.title=`${label} | ${isOwnerPanel ? 'پنل مالک' : 'پنل ادمین'} لایف‌باکس`;
    setMenu(false);drawCharts();
  }
  function setMenu(open,returnFocus=false) {
    $('#owner-sidebar').classList.toggle('is-open',open);$('#sidebar-backdrop').hidden=!open;
    $('#owner-menu').setAttribute('aria-expanded',String(open));
    $('#owner-menu').setAttribute('aria-label',open?'بستن منو':'باز کردن منو');
    $('#owner-content').inert=open;
    if(open) $('.side-nav a').focus(); else if(returnFocus) $('#owner-menu').focus();
  }
  function applyTheme(theme) {
    document.body.dataset.theme=theme;
    $('#theme-owner').setAttribute('aria-label',theme==='dark'?'تغییر به حالت روشن':'تغییر به حالت تیره');
    $('#theme-owner .oi').dataset.icon=theme==='dark'?'sun':'moon';drawCharts();
  }
  function openMember(key) {
    editingMember=members.find(m=>m.key===key);if(!editingMember || editingMember.remotePending)return;
    const form=$('#member-form');
    ['firstName','lastName','mobile','nationalId','address','debt','payment'].forEach(k=>{if(form.elements[k])form.elements[k].value=editingMember[k]??'';});
    ['debt','payment'].forEach(k=>{if(form.elements[k])form.elements[k].disabled=!editingMember.gymId;});
    if(form.elements.planId)form.elements.planId.innerHTML='<option value="">بدون تغییر پلن</option>'+plans.filter(p=>p.isActive).map(p=>`<option value="${p.id}">${html(p.name)}</option>`).join('');
    $('#member-title').textContent=fullName(editingMember);
    let summary=$('#member-summary');
    if(!summary){summary=document.createElement('p');summary.id='member-summary';summary.className='admin-note';$('#member-title').after(summary);}
    summary.textContent=`${labels[editingMember.membershipStatus] || 'وضعیت نامشخص'} · پایان: ${formatDate(editingMember.expiresAt)} · آخرین مراجعه: ${formatDate(editingMember.lastVisit)} · ${number(editingMember.remainingSessions)} جلسه باقی‌مانده`;
    $('.form-result',form).textContent='';$('#member-dialog').showModal();
  }
  function openPlan(id) {
    if(!isOwnerPanel)return;
    editingPlan=plans.find(p=>p.id===Number(id));
    const form=$('#plan-form'),data=editingPlan || {name:'',price:0,sessionsPerMonth:12,gender:'all',isActive:true};
    Object.keys(data).forEach(k=>{if(form.elements[k])form.elements[k].value=String(data[k]);});
    $('#plan-title').textContent=editingPlan?'ویرایش پلن':'افزودن پلن';$('.form-result',form).textContent='';$('#plan-dialog').showModal();
  }
  async function submit(event,kind) {
    event.preventDefault();const form=event.target,button=$('button[type="submit"]',form),payload=Object.fromEntries(new FormData(form));button.disabled=true;
    try {
      let result;
      if(kind==='plan'){payload.price=Number(payload.price);payload.sessionsPerMonth=Number(payload.sessionsPerMonth);payload.isActive=payload.isActive==='true';result=await api(`/api/owner/plans${editingPlan?'/'+editingPlan.id:''}`,{method:editingPlan?'PATCH':'POST',body:JSON.stringify(payload)});}
      else result=await api(`${apiRoot}/members/${editingMember.key.replace(':','/')}`,{method:'PATCH',body:JSON.stringify(payload)});
      form.closest('dialog').close();await refresh();feedback(result.queued?'تغییر ذخیره شد؛ پس از اتصال پذیرش اعمال می‌شود.':'تغییرات با موفقیت ذخیره شد.');
    } catch(e){$('.form-result',form).textContent=e.message;}
    finally{button.disabled=false;}
  }
  function exportCsv(rows,name){
    const cell=v=>'"'+String(v??'').replace(/^(?:[=+@\-\t\r\n]|\s+[=+@\-])/,"'$&").replaceAll('"','""')+'"';
    const url=URL.createObjectURL(new Blob(['\ufeff'+rows.map(r=>r.map(cell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}));
    const a=document.createElement('a');a.href=url;a.download=name;document.body.append(a);a.click();a.remove();setTimeout(()=>URL.revokeObjectURL(url),1000);
  }
  document.addEventListener('DOMContentLoaded',async()=>{
    let storedTheme;try{storedTheme=localStorage.getItem('lifebox-owner-theme');}catch{}
    applyTheme(storedTheme || (matchMedia('(prefers-color-scheme: dark)').matches?'dark':'light'));
    $('#owner-date').textContent=new Intl.DateTimeFormat('fa-IR',{weekday:'long',day:'numeric',month:'long',year:'numeric',timeZone:'Asia/Tehran'}).format(new Date());
    navigate();
    const user=await protectPage(isOwnerPanel ? 'owner' : 'admin');if(!user)return;
    $('#owner-name').textContent=user.fullName;$('#owner-initial').textContent=user.fullName?.[0] || 'م';$('[data-owner]').classList.add('is-ready');
    $('#owner-search').addEventListener('input',()=>{memberPage=1;renderMembers();});
    $('#previous-members').addEventListener('click',()=>{memberPage--;renderMembers();});
    $('#next-members').addEventListener('click',()=>{memberPage++;renderMembers();});
    $('#refresh-owner').addEventListener('click',refresh);$('#activity-period').addEventListener('change',refresh);
    $('#activity-search').addEventListener('input',()=>{clearTimeout(activitySearchTimer);activitySearchTimer=setTimeout(refresh,300);});
    $('#attendance-previous').addEventListener('click',()=>openAttendance(attendanceMember.id,attendanceMember.page-1));
    $('#attendance-next').addEventListener('click',()=>openAttendance(attendanceMember.id,attendanceMember.page+1));
    $('#attendance-period').addEventListener('change',()=>openAttendance(attendanceMember.id,1));
    $('#attendance-dialog').addEventListener('close',()=>{attendanceRequest++;$('#attendance-dialog').setAttribute('aria-busy','false');});
    $('#chart-period')?.addEventListener('change',drawRevenue);$('#new-plan')?.addEventListener('click',()=>openPlan());
    $('#member-form').addEventListener('submit',e=>submit(e,'member'));$('#plan-form')?.addEventListener('submit',e=>submit(e,'plan'));
    $$('[data-close]').forEach(b=>b.addEventListener('click',()=>b.closest('dialog').close()));
    $$('[data-member-filter]').forEach(b=>b.addEventListener('click',()=>setFilter(b.dataset.memberFilter)));
    $$('[data-followup]').forEach(b=>b.addEventListener('click',()=>{followupFilter=b.dataset.followup;$$('[data-followup]').forEach(t=>{const active=t===b;t.classList.toggle('active',active);t.setAttribute('aria-pressed',String(active));});renderFollowups();}));
    document.addEventListener('click',async e=>{
      if(e.target.closest('.side-nav a[href^="#"]')) setMenu(false);
      const filter=e.target.closest('[data-filter-link]');if(filter){$('#owner-search').value='';setFilter(filter.dataset.filterLink);navigate();}
      const edit=e.target.closest('[data-edit-member]');if(edit)return openMember(edit.dataset.editMember);
      const attendance=e.target.closest('[data-attendance-member]');if(attendance)return openAttendance(attendance.dataset.attendanceMember);
      const plan=e.target.closest('[data-edit-plan]');if(plan)return openPlan(plan.dataset.editPlan);
      const b=e.target.closest('[data-status-member]');if(!b)return;
      b.disabled=true;try{await api(`/api/admin/users/${b.dataset.statusMember}/status`,{method:'PATCH',body:JSON.stringify({status:b.dataset.status})});await refresh();}catch(e){feedback(e.message,true);}finally{b.disabled=false;}
    });
    $('#theme-owner').addEventListener('click',()=>{const theme=document.body.dataset.theme==='dark'?'light':'dark';applyTheme(theme);try{localStorage.setItem('lifebox-owner-theme',theme);}catch{}});
    $('#owner-menu').addEventListener('click',()=>setMenu(true));$('#sidebar-backdrop').addEventListener('click',()=>setMenu(false,true));
    $('.owner-skip').addEventListener('click',e=>{e.preventDefault();$('#owner-content').focus();});
    window.addEventListener('hashchange',navigate);
    document.addEventListener('keydown',e=>{
      if(!$('#owner-sidebar').classList.contains('is-open'))return;
      if(e.key==='Escape')setMenu(false,true);
      if(e.key==='Tab'){const controls=$$('a,button', $('#owner-sidebar'));if(e.shiftKey && document.activeElement===controls[0]){e.preventDefault();controls.at(-1).focus();}else if(!e.shiftKey && document.activeElement===controls.at(-1)){e.preventDefault();controls[0].focus();}}
    });
    const resizeObserver=new ResizeObserver(()=>{if(window.innerWidth>760 && $('#owner-sidebar').classList.contains('is-open'))setMenu(false);drawCharts();});resizeObserver.observe($('#owner-content'));
    $('#export-members').addEventListener('click',()=>exportCsv([['نام','نام خانوادگی','موبایل','پلن','وضعیت عضویت','بدهی',...(isOwnerPanel ? ['پرداخت'] : [])],...visibleMembers().map(m=>[m.firstName,m.lastName,m.mobile,m.plan,labels[m.membershipStatus],m.debt,...(isOwnerPanel ? [m.payment] : [])])],'lifebox-members.csv'));
    $('#export-payments').addEventListener('click',()=>exportCsv([['عضو','پلن','مبلغ','تاریخ','مرجع پرداخت'],...overview.payments.map(p=>[p.name,p.plan,p.amount,p.at,p.reference])],'lifebox-renewal-payments.csv'));
    await document.fonts.ready;await refresh();
    setInterval(()=>{if(!document.hidden && !$('dialog[open]'))refresh();},30000);
  });
})();
