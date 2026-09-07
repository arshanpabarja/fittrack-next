/* Owner operations use Django sessions and the existing CSRF helper. */
(() => {
  let members = [], plans = [], editingMember, editingPlan, refreshing = false, memberPage = 1;
  const html = escapeHtml;
  const number = value => new Intl.NumberFormat('fa-IR').format(value || 0);
  const stamp = value => value ? `${formatDate(value)} · ${toFa((value.split('T')[1] || value.split(' ')[1] || '').slice(0,5))}` : '—';
  const feedback = (message, failed = false) => { $('#owner-feedback').textContent = message; $('#owner-feedback').classList.toggle('error', failed); };
  const empty = (cols, message) => `<tr><td colspan="${cols}">${message}</td></tr>`;
  function visibleMembers() {
    const query = $('#owner-search').value.trim().toLocaleLowerCase();
    return members.filter(m => `${m.firstName} ${m.lastName}`.toLocaleLowerCase().includes(query) || normalizeDigits(m.mobile).includes(normalizeDigits(query)) || (m.nationalId || '').includes(normalizeDigits(query)));
  }
  function renderMembers() {
    const allRows = visibleMembers();
    const pageCount = Math.max(1, Math.ceil(allRows.length / 40));
    memberPage = Math.min(memberPage, pageCount);
    const rows = allRows.slice((memberPage-1)*40, memberPage*40);
    $('#member-page').textContent = `${number(memberPage)} / ${number(pageCount)}`;
    $('#previous-members').disabled = memberPage === 1;
    $('#next-members').disabled = memberPage === pageCount;
    $('#member-count').textContent = `${number(allRows.length)} حساب از ${number(members.length)} حساب و عضو حضوری`;
    $('#metric-members').textContent = number(members.filter(m => m.role === 'member').length);
    $('#owner-members').innerHTML = rows.map(m => `<tr><td><strong>${html(`${m.firstName} ${m.lastName}`)}</strong><small>${html(toFa(m.mobile))}</small></td><td>${html(m.plan || '—')}</td><td>${number(m.sessionsUsed)}</td><td>${number(m.debt)}</td><td>${html(m.status === 'gym' ? 'فقط حضوری' : statusLabel(m.status))}<small>${html(roleLabel(m.role))}</small></td><td><div class="owner-actions">${m.role === 'admin' ? '—' : `<button class="table-action" data-edit-member="${m.key}">ویرایش</button>${m.webId ? `<button class="table-action" data-status-member="${m.webId}" data-status="${m.status === 'suspended' ? 'active' : 'suspended'}">${m.status === 'suspended' ? 'فعال‌سازی سایت' : 'تعلیق سایت'}</button>` : ''}`}</div></td></tr>`).join('') || empty(6,'عضوی پیدا نشد.');
  }
  function renderPlans() {
    $('#owner-plans').innerHTML = plans.map(p => `<article class="owner-plan ${p.isActive ? '' : 'inactive'}"><span>${p.isActive ? 'فعال' : 'غیرفعال'} · ${{all:'همه',male:'آقایان',female:'بانوان'}[p.gender]}</span><h3>${html(p.name)}</h3><strong>${number(p.price)} <small>تومان</small></strong><p>${number(p.sessionsPerMonth)} جلسه در ماه</p><button class="table-action" data-edit-plan="${p.id}">ویرایش پلن</button></article>`).join('') || '<p>هنوز پلنی ثبت نشده است.</p>';
  }
  async function refresh() {
    if (refreshing) return;
    refreshing = true; $('#refresh-owner').disabled = true;
    try {
      const [directory, catalog, activity] = await Promise.all([api('/api/owner/members'), api('/api/owner/plans'), api(`/api/owner/activity?period=${$('#activity-period').value}`)]);
      members = directory.members; plans = catalog.plans; renderMembers(); renderPlans();
      $('#metric-inside').textContent = activity.attendanceAvailable ? number(activity.inside) : '—';
      $('#metric-visits').textContent = activity.attendanceAvailable ? number(activity.visitCount) : '—';
      $('#metric-visitors').textContent = activity.attendanceAvailable ? `${number(activity.visitors)} عضو یکتا` : 'اتصال حضور در دسترس نیست';
      $('#metric-logins').textContent = number(activity.loginCount);
      $('#metric-login-users').textContent = `${number(activity.loginUsers)} کاربر یکتا`;
      $('#activity-range').textContent = `${formatDate(activity.start)} تا ${formatDate(activity.end)} · ساعت محلی باشگاه (تهران)`;
      $('#attendance-warning').textContent = activity.attendanceAvailable ? '' : 'دیتابیس حضور برنامه باشگاه در دسترس نیست؛ آمار حضور قابل نمایش نیست.';
      $('#owner-attendance').innerHTML = activity.attendance.map(a => `<tr><td>${html(a.full_name)}<small>${html(toFa(a.mobile))}</small></td><td>${stamp(a.checked_in_at)}</td><td>${a.checked_out_at ? stamp(a.checked_out_at) : 'داخل باشگاه'}</td><td>${number(a.locker_id)}</td></tr>`).join('') || empty(4,activity.attendanceAvailable ? 'در این بازه مراجعه‌ای ثبت نشده است.' : 'اطلاعات حضور در دسترس نیست.');
      $('#owner-logins').innerHTML = activity.logins.map(l => `<tr><td>${html(l.name)}</td><td>${html(toFa(l.mobile))}</td><td>${stamp(new Date(l.at).toLocaleString('sv-SE',{timeZone:'Asia/Tehran'}))}</td></tr>`).join('') || empty(3,'در این بازه ورود به سایت ثبت نشده است.');
      $('#owner-audit').innerHTML = activity.audit.map(a => `<li><span>${html(a.action)}</span><small>${stamp(new Date(a.at).toLocaleString('sv-SE',{timeZone:'Asia/Tehran'}))}</small></li>`).join('') || '<li>هنوز تغییری ثبت نشده است.</li>';
      feedback(`آخرین به‌روزرسانی: ${new Date().toLocaleTimeString('fa-IR')} · دریافت خودکار هر ۳۰ ثانیه`);
    } catch(e) { feedback(e.message, true); }
    finally { refreshing = false; $('#refresh-owner').disabled = false; }
  }
  function openMember(key) {
    editingMember = members.find(m => m.key === key);
    const form = $('#member-form');
    ['firstName','lastName','mobile','nationalId','address','debt','payment'].forEach(k => form.elements[k].value = editingMember[k] ?? '');
    ['debt','payment'].forEach(k => form.elements[k].disabled = !editingMember.gymId);
    form.elements.planId.innerHTML = '<option value="">بدون تغییر پلن</option>' + plans.filter(p => p.isActive).map(p => `<option value="${p.id}">${html(p.name)}</option>`).join('');
    $('.form-result',form).textContent = ''; $('#member-dialog').showModal();
  }
  function openPlan(id) {
    editingPlan = plans.find(p => p.id === Number(id));
    const form = $('#plan-form');
    const data = editingPlan || {name:'',price:0,sessionsPerMonth:12,gender:'all',isActive:true};
    Object.keys(data).forEach(k => { if(form.elements[k]) form.elements[k].value = String(data[k]); });
    $('#plan-title').textContent = editingPlan ? 'ویرایش پلن' : 'افزودن پلن';
    $('.form-result',form).textContent = ''; $('#plan-dialog').showModal();
  }
  async function submit(event, kind) {
    event.preventDefault();
    const form = event.target, button = $('button[type="submit"]',form);
    const payload = Object.fromEntries(new FormData(form)); button.disabled = true;
    try {
      if(kind === 'plan') {
        payload.price = Number(payload.price); payload.sessionsPerMonth = Number(payload.sessionsPerMonth); payload.isActive = payload.isActive === 'true';
        await api(`/api/owner/plans${editingPlan ? '/'+editingPlan.id : ''}`, {method:editingPlan ? 'PATCH' : 'POST',body:JSON.stringify(payload)});
      } else {
        await api(`/api/owner/members/${editingMember.key.replace(':','/')}`, {method:'PATCH',body:JSON.stringify(payload)});
      }
      form.closest('dialog').close(); await refresh();
    } catch(e) { $('.form-result',form).textContent = e.message; }
    finally { button.disabled = false; }
  }
  document.addEventListener('DOMContentLoaded', async () => {
    const user = await protectPage('admin'); if (!user) return;
    $('#owner-name').textContent = user.fullName;
    $('[data-owner]').classList.add('is-ready');
    $('#owner-search').addEventListener('input',() => { memberPage = 1; renderMembers(); });
    $('#previous-members').addEventListener('click',() => { memberPage--; renderMembers(); });
    $('#next-members').addEventListener('click',() => { memberPage++; renderMembers(); });
    $('#refresh-owner').addEventListener('click',refresh);
    $('#activity-period').addEventListener('change',refresh);
    $('#new-plan').addEventListener('click',() => openPlan());
    $('#member-form').addEventListener('submit',e => submit(e,'member'));
    $('#plan-form').addEventListener('submit',e => submit(e,'plan'));
    $$('[data-close]').forEach(b => b.addEventListener('click',() => b.closest('dialog').close()));
    $('#owner-plans').addEventListener('click',e => { const b = e.target.closest('[data-edit-plan]'); if(b) openPlan(b.dataset.editPlan); });
    $('#owner-members').addEventListener('click',async e => {
      const edit = e.target.closest('[data-edit-member]'); if(edit) return openMember(edit.dataset.editMember);
      const b = e.target.closest('[data-status-member]'); if(!b) return;
      b.disabled = true;
      try { await api(`/api/admin/users/${b.dataset.statusMember}/status`,{method:'PATCH',body:JSON.stringify({status:b.dataset.status})}); await refresh(); }
      catch(e) { feedback(e.message,true); } finally { b.disabled = false; }
    });
    $('#export-members').addEventListener('click',() => {
      const cell = v => '"'+String(v ?? '').replace(/^[=+@\-\t\r]/,"'$&").replaceAll('"','""')+'"';
      const rows = [['نام','نام خانوادگی','موبایل','پلن','بدهی','پرداخت'], ...visibleMembers().map(m => [m.firstName,m.lastName,m.mobile,m.plan,m.debt,m.payment])];
      const url = URL.createObjectURL(new Blob(['\ufeff'+rows.map(r => r.map(cell).join(',')).join('\r\n')],{type:'text/csv;charset=utf-8'}));
      const a = document.createElement('a'); a.href = url; a.download = 'lifebox-members.csv'; a.click(); setTimeout(() => URL.revokeObjectURL(url),1000);
    });
    await refresh();
    setInterval(() => { if(!document.hidden && !$('dialog[open]')) refresh(); },30000);
  });
})();
