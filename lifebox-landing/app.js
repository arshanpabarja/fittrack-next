const $ = (selector, scope = document) => scope.querySelector(selector);
const $$ = (selector, scope = document) => [...scope.querySelectorAll(selector)];
const latinDigits = (value) => String(value ?? "").replace(/[۰-۹٠-٩]/g, (digit) => "۰۱۲۳۴۵۶۷۸۹٠١٢٣٤٥٦٧٨٩".indexOf(digit) % 10);
const normalizeDigits = (value) => latinDigits(value).replace(/\s/g, "");

const toFa = (value) => String(value ?? "").replace(/\d/g, (digit) => "۰۱۲۳۴۵۶۷۸۹"[digit]);
const JALALI_MONTHS = ["فروردین", "اردیبهشت", "خرداد", "تیر", "مرداد", "شهریور", "مهر", "آبان", "آذر", "دی", "بهمن", "اسفند"];

const formatDate = (value) => {
  if (!value) return "—";
  const normalized = latinDigits(value).trim();
  const jalali = normalized.match(/^(1[34]\d{2})[-_/](\d{1,2})[-_/](\d{1,2})(?:$|[ T_])/);
  if (jalali) {
    const year = Number(jalali[1]);
    const month = Number(jalali[2]);
    const day = Number(jalali[3]);
    const maximumDay = month <= 6 ? 31 : 30;
    if (month >= 1 && month <= 12 && day >= 1 && day <= maximumDay) {
      return `${toFa(day)} ${JALALI_MONTHS[month - 1]} ${toFa(year)}`;
    }
  }
  if (/^1[34]\d{2}[-_/]/.test(normalized)) {
    return toFa(normalized.split(/[ T]/)[0].replaceAll("_", "-"));
  }
  try {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "—";
    return new Intl.DateTimeFormat("fa-IR", { year: "numeric", month: "long", day: "numeric" }).format(date);
  } catch {
    return "—";
  }
};

function cookie(name) {
  return document.cookie.split("; ").find((item) => item.startsWith(`${name}=`))?.split("=").slice(1).join("=") || "";
}

async function api(path, options = {}) {
  const method = (options.method || "GET").toUpperCase();
  const csrfToken = cookie("csrftoken");
  const response = await fetch(path, {
    credentials: "same-origin",
    headers: {
      "Content-Type": "application/json",
      ...(method !== "GET" && csrfToken ? { "X-CSRFToken": decodeURIComponent(csrfToken) } : {}),
      ...(options.headers || {}),
    },
    ...options,
  });
  let result = {};
  try {
    result = await response.json();
  } catch {
    result = { message: "پاسخ سرور قابل خواندن نیست." };
  }
  if (!response.ok) {
    const error = new Error(result.message || "درخواست انجام نشد.");
    error.status = response.status;
    error.field = result.field;
    throw error;
  }
  return result;
}

function setFormMessage(form, message = "", type = "error") {
  const box = $("[data-form-message]", form);
  if (!box) return;
  box.textContent = message;
  box.className = `form-message ${message ? "is-visible" : ""} ${type}`;
}

function clearFieldErrors(form) {
  $$(".field-error", form).forEach((element) => (element.textContent = ""));
  $$(".field-input", form).forEach((element) => element.removeAttribute("aria-invalid"));
}

function setFieldError(form, field, message) {
  const input = form.elements[field];
  const error = $(`[data-error-for="${field}"]`, form);
  if (input) {
    input.setAttribute("aria-invalid", "true");
    input.focus();
  }
  if (error) error.textContent = message;
}

function setBusy(button, busy, busyText = "در حال بررسی...") {
  if (!button) return;
  if (busy) {
    button.dataset.originalText = button.innerHTML;
    button.textContent = busyText;
    button.disabled = true;
  } else {
    button.innerHTML = button.dataset.originalText || button.innerHTML;
    button.disabled = false;
  }
}

function initPasswordToggles() {
  $$('[data-toggle-password]').forEach((button) => {
    button.addEventListener("click", () => {
      const input = document.getElementById(button.dataset.togglePassword);
      if (!input) return;
      const visible = input.type === "text";
      input.type = visible ? "password" : "text";
      button.textContent = visible ? "نمایش" : "پنهان";
      button.setAttribute("aria-pressed", String(!visible));
    });
  });
}

function initMobileNavigation() {
  const toggle = $("[data-nav-toggle]");
  const nav = $("[data-mobile-nav]");
  const backdrop = $("[data-nav-backdrop]");
  if (!toggle || !nav) return;

  const setOpen = (open, returnFocus = false) => {
    nav.classList.toggle("is-open", open);
    backdrop?.classList.toggle("is-visible", open);
    document.body.classList.toggle("nav-open", open);
    toggle.setAttribute("aria-expanded", String(open));
    toggle.setAttribute("aria-label", open ? "\u0628\u0633\u062a\u0646 \u0645\u0646\u0648" : "\u0628\u0627\u0632\u06a9\u0631\u062f\u0646 \u0645\u0646\u0648");
    if (open) $("a", nav)?.focus();
    if (!open && returnFocus) toggle.focus();
  };

  toggle.addEventListener("click", () => setOpen(!nav.classList.contains("is-open")));
  backdrop?.addEventListener("click", () => setOpen(false, true));
  $$("a", nav).forEach((link) => link.addEventListener("click", () => setOpen(false)));
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && nav.classList.contains("is-open")) setOpen(false, true);
  });
  window.addEventListener("resize", () => {
    if (window.innerWidth > 760 && nav.classList.contains("is-open")) setOpen(false);
  });
}

function accountDestination(user) {
  if (user.role === "admin") return "admin.html";
  if (user.role === "coach") return "coach-panel.html";
  return user.status === "pending" ? "pending.html" : "dashboard.html";
}

async function initLogin() {
  const form = $("#login-form");
  if (!form) return;
  try {
    const current = await api("/api/me");
    window.location.replace(accountDestination(current.user));
    return;
  } catch {
    // No active session; keep the login form available.
  }
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearFieldErrors(form);
    setFormMessage(form);
    const button = $("button[type='submit']", form);
    const mobile = normalizeDigits(form.mobile.value);
    form.mobile.value = mobile;
    const password = form.password.value;
    if (!/^09\d{9}$/.test(mobile)) {
      setFieldError(form, "mobile", "شماره موبایل باید ۱۱ رقم و با ۰۹ شروع شود.");
      return;
    }
    if (!password) {
      setFieldError(form, "password", "رمز عبور را وارد کنید.");
      return;
    }
    setBusy(button, true);
    try {
      const result = await api("/api/login", { method: "POST", body: JSON.stringify({ mobile, password }) });
      window.location.href = accountDestination(result.user);
    } catch (error) {
      setFormMessage(form, error.message);
    } finally {
      setBusy(button, false);
    }
  });
}

function initSignup() {
  const form = $("#signup-form");
  if (!form) return;
  const planSelect = form.elements.planId;
  const otpButton = $("[data-send-otp]", form);
  const otpStatus = $("[data-otp-status]", form);
  let otpCountdown;

  const startOtpCountdown = (seconds) => {
    window.clearInterval(otpCountdown);
    let remaining = Math.max(1, Number(seconds) || 60);
    const render = () => {
      otpButton.disabled = remaining > 0;
      otpButton.textContent = remaining > 0 ? `ارسال دوباره (${toFa(remaining)})` : "ارسال دوباره";
    };
    render();
    otpCountdown = window.setInterval(() => {
      remaining -= 1;
      render();
      if (remaining <= 0) window.clearInterval(otpCountdown);
    }, 1000);
  };

  otpButton.addEventListener("click", async () => {
    clearFieldErrors(form);
    setFormMessage(form);
    otpStatus.textContent = "";
    const mobile = normalizeDigits(form.mobile.value);
    form.mobile.value = mobile;
    if (!/^09\d{9}$/.test(mobile)) {
      setFieldError(form, "mobile", "شماره موبایل باید ۱۱ رقم و با ۰۹ شروع شود.");
      return;
    }
    setBusy(otpButton, true, "در حال ارسال...");
    try {
      const result = await api("/api/signup/otp/send", { method: "POST", body: JSON.stringify({ mobile }) });
      otpStatus.textContent = result.message;
      setFormMessage(form, result.message, "success");
      form.otpCode.focus();
      startOtpCountdown(result.resendAfter);
    } catch (error) {
      if (error.field) setFieldError(form, error.field, error.message);
      else setFormMessage(form, error.message);
      setBusy(otpButton, false);
    }
  });

  api("/api/plans")
    .then(({ plans }) => {
      planSelect.innerHTML = '<option value="">یک پلن را انتخاب کنید</option>';
      plans.forEach((plan) => {
        const option = document.createElement("option");
        option.value = plan.id;
        option.textContent = `${plan.name} — ${toFa(Number(plan.price).toLocaleString("fa-IR"))} تومان`;
        planSelect.appendChild(option);
      });
    })
    .catch(() => {
      planSelect.innerHTML = '<option value="">دریافت پلن‌ها ناموفق بود؛ صفحه را تازه کنید</option>';
    });
  form.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearFieldErrors(form);
    setFormMessage(form);
    const button = $("button[type='submit']", form);
    const data = {
      fullName: form.fullName.value.trim(),
      mobile: normalizeDigits(form.mobile.value),
      otpCode: normalizeDigits(form.otpCode.value),
      nationalId: normalizeDigits(form.nationalId.value),
      address: form.address.value.trim(),
      planId: form.planId.value,
      password: form.password.value,
    };
    if (data.fullName.length < 3) {
      setFieldError(form, "fullName", "نام و نام خانوادگی را کامل وارد کنید.");
      return;
    }
    if (!/^09\d{9}$/.test(data.mobile)) {
      setFieldError(form, "mobile", "شماره موبایل باید ۱۱ رقم و با ۰۹ شروع شود.");
      return;
    }
    if (!/^\d{5}$/.test(data.otpCode)) {
      setFieldError(form, "otpCode", "کد تأیید پنج‌رقمی را وارد کنید.");
      return;
    }
    if (!/^\d{10}$/.test(data.nationalId)) {
      setFieldError(form, "nationalId", "کد ملی باید دقیقاً ۱۰ رقم باشد.");
      return;
    }
    if (data.address.length < 8) {
      setFieldError(form, "address", "آدرس کامل محل سکونت را وارد کنید.");
      return;
    }
    if (!data.planId) {
      setFieldError(form, "planId", "یکی از پلن‌های عضویت را انتخاب کنید.");
      return;
    }
    if (data.password.length < 10 || !/[A-Za-z]/.test(data.password) || !/\d/.test(data.password)) {
      setFieldError(form, "password", "حداقل ۱۰ کاراکتر و ترکیبی از حرف و عدد انتخاب کنید.");
      return;
    }
    if (data.password !== form.confirmPassword.value) {
      setFieldError(form, "confirmPassword", "تکرار رمز عبور یکسان نیست.");
      return;
    }
    if (!form.terms.checked) {
      setFieldError(form, "terms", "برای ساخت حساب، قوانین باشگاه را بپذیرید.");
      return;
    }
    setBusy(button, true, "در حال ساخت حساب...");
    try {
      const result = await api("/api/signup", { method: "POST", body: JSON.stringify(data) });
      window.location.href = result.user.status === "active" ? "dashboard.html" : "pending.html";
    } catch (error) {
      if (error.field) setFieldError(form, error.field, error.message);
      else setFormMessage(form, error.message);
    } finally {
      setBusy(button, false);
    }
  });
}

function initNumericInputs() {
  $$('input[inputmode="numeric"], input[type="tel"]').forEach((input) => {
    input.addEventListener("input", () => {
      const normalized = normalizeDigits(input.value).replace(/\D/g, "");
      if (input.value !== normalized) input.value = normalized;
    });
  });
}

async function initAuthLink() {
  const link = $('.quiet-link[href="login.html"]');
  if (!link) return;
  try {
    const result = await api("/api/me");
    link.href = accountDestination(result.user);
    link.textContent = "پنل من";
  } catch {
    // Anonymous visitors keep the normal login link.
  }
}

async function logout() {
  try {
    await api("/api/logout", { method: "POST", body: "{}" });
  } finally {
    window.location.href = "login.html";
  }
}

function initLogout() {
  $$('[data-logout]').forEach((button) => button.addEventListener("click", logout));
}

async function protectPage(role) {
  try {
    const result = await api("/api/me");
    if (role && result.user.role !== role) {
      window.location.replace(accountDestination(result.user));
      return null;
    }
    if (!role && result.user.status === "pending" && !document.querySelector("[data-pending]")) {
      window.location.replace("pending.html");
      return null;
    }
    return result.user;
  } catch {
    window.location.replace("login.html");
    return null;
  }
}

async function initPending() {
  const root = $("[data-pending]");
  if (!root) return;
  const refresh = async () => {
    try {
      const result = await api("/api/me");
      if (result.user.role !== "member") return window.location.replace(accountDestination(result.user));
      if (result.user.status === "active") return window.location.replace("dashboard.html");
      $("[data-pending-name]").textContent = result.user.fullName;
      $("[data-pending-mobile]").textContent = toFa(result.user.mobile);
      $("[data-pending-plan]").textContent = result.user.plan;
    } catch {
      window.location.replace("login.html");
    }
  };
  $("[data-refresh-status]")?.addEventListener("click", refresh);
  await refresh();
  window.setInterval(refresh, 15000);
}

async function initDashboard() {
  const root = $("[data-dashboard]");
  if (!root) return;
  const user = await protectPage("member");
  if (!user) return;
  $("[data-user-name]").textContent = user.fullName;
  $("[data-user-first-name]").textContent = user.fullName.split(" ")[0];
  $("[data-user-mobile]").textContent = toFa(user.mobile);
  $("[data-user-plan]").textContent = user.plan;
  $("[data-user-joined]").textContent = formatDate(user.joinedAt);
  $("[data-sessions-used]").textContent = toFa(user.sessionsUsed);
  const progress = Math.min((user.sessionsUsed / 12) * 100, 100);
  const bar = $("[data-session-progress]");
  if (bar) bar.style.width = `${progress}%`;
  try {
    const result = await api("/api/member/program");
    const program = result.program;
    const lines = $("[data-member-workout-lines]");
    lines.innerHTML = "";
    if (!program) {
      $("[data-member-program-title]").textContent = "هنوز برنامه‌ای ثبت نشده است.";
      $("[data-member-program-coach]").textContent = "پس از ثبت برنامه توسط مربی، این بخش خودکار به‌روز می‌شود.";
      $("[data-member-workout-heading]").textContent = "بدون برنامه فعال";
      const empty = document.createElement("p");
      empty.className = "member-program-empty";
      empty.textContent = "مربی هنوز برنامه تمرینی برای شما ثبت نکرده است.";
      lines.appendChild(empty);
    } else {
      $("[data-member-program-title]").textContent = program.title;
      $("[data-member-program-coach]").textContent = `مربی: ${program.coachName}`;
      $("[data-member-workout-heading]").textContent = program.title;
      const days = Array.isArray(program.days) ? program.days : [];
      const durationText = `${toFa(program.durationWeeks || 4)} هفته`;
      const daysText = days.length ? `${toFa(days.length)} روز در هفته` : "برنامه تمرینی";
      $("[data-member-workout-meta]").textContent = `${durationText} · ${daysText} · مربی ${program.coachName} · به‌روزرسانی ${formatDate(program.updatedAt)}`;
      days.forEach((day) => {
        const section = document.createElement("section");
        section.className = "member-workout-day";
        const heading = document.createElement("h3");
        heading.className = "member-workout-day-title";
        heading.textContent = day.label || "روز تمرین";
        section.appendChild(heading);
        (day.movements || []).forEach((movement, index) => {
          const row = document.createElement("div");
          row.className = "workout-row member-workout-row";
          const number = document.createElement("span");
          number.textContent = toFa(index + 1);
          const text = document.createElement("strong");
          text.textContent = movement;
          row.append(number, text);
          section.appendChild(row);
        });
        lines.appendChild(section);
      });
    }
  } catch {
    $("[data-member-workout-lines]").innerHTML = '<p class="member-program-empty">دریافت برنامه تمرینی انجام نشد؛ صفحه را دوباره باز کنید.</p>';
  }
  root.classList.add("is-ready");
}

const coachPanelState = { coach: null, members: [], programs: [] };
const WEEKDAYS = [
  ["saturday", "شنبه"],
  ["sunday", "یکشنبه"],
  ["monday", "دوشنبه"],
  ["tuesday", "سه‌شنبه"],
  ["wednesday", "چهارشنبه"],
  ["thursday", "پنج‌شنبه"],
  ["friday", "جمعه"],
];
const DEFAULT_TRAINING_DAYS = ["saturday", "monday", "wednesday"];

function blankMovements(count = 3) {
  return Array.from({ length: count }, () => "");
}

function collectWeeklyDays(form, includeEmpty = true) {
  return $$("[data-training-day]", form).map((card) => ({
    weekday: $("[data-weekday]", card)?.value || "",
    movements: $$("[data-movement]", card)
      .map((input) => input.value.trim())
      .filter((value) => includeEmpty || value),
  }));
}

function addMovementField(card, value = "") {
  const list = $("[data-movement-list]", card);
  if (!list || $$("[data-movement]", list).length >= 20) return;
  const row = document.createElement("div");
  row.className = "movement-field-row";
  const input = document.createElement("input");
  input.className = "field-input";
  input.type = "text";
  input.maxLength = 300;
  input.placeholder = "مثلاً اسکوات — ۳ ست × ۱۲ تکرار — ۹۰ ثانیه استراحت";
  input.setAttribute("data-movement", "");
  input.setAttribute("aria-label", `حرکت شماره ${$$("[data-movement]", list).length + 1}`);
  input.value = value;
  const remove = document.createElement("button");
  remove.className = "movement-remove";
  remove.type = "button";
  remove.textContent = "حذف";
  remove.setAttribute("aria-label", "حذف این حرکت");
  remove.addEventListener("click", () => {
    if ($$("[data-movement]", list).length > 1) row.remove();
    else input.value = "";
  });
  row.append(input, remove);
  list.appendChild(row);
}

function renderWeeklyDays(form, days) {
  const container = $("[data-training-days]", form);
  if (!container) return;
  container.innerHTML = "";
  days.forEach((day, dayIndex) => {
    const card = document.createElement("section");
    card.className = "training-day-card";
    card.setAttribute("data-training-day", "");
    const head = document.createElement("div");
    head.className = "training-day-head";
    const title = document.createElement("h3");
    title.textContent = `روز تمرین ${toFa(dayIndex + 1)}`;
    const weekdayField = document.createElement("div");
    weekdayField.className = "weekday-field";
    const label = document.createElement("label");
    const selectId = `program-weekday-${dayIndex}`;
    label.htmlFor = selectId;
    label.textContent = "روز هفته";
    const select = document.createElement("select");
    select.className = "field-input";
    select.id = selectId;
    select.setAttribute("data-weekday", "");
    select.innerHTML = '<option value="">انتخاب روز</option>' + WEEKDAYS.map(([value, text]) => `<option value="${value}">${text}</option>`).join("");
    select.value = day.weekday || "";
    weekdayField.append(label, select);
    head.append(title, weekdayField);
    const movementList = document.createElement("div");
    movementList.className = "movement-fields";
    movementList.setAttribute("data-movement-list", "");
    const addButton = document.createElement("button");
    addButton.className = "add-movement";
    addButton.type = "button";
    addButton.textContent = "+ افزودن حرکت دیگر";
    addButton.addEventListener("click", () => {
      addMovementField(card);
      const inputs = $$("[data-movement]", card);
      inputs[inputs.length - 1]?.focus();
    });
    card.append(head, movementList, addButton);
    container.appendChild(card);
    const movements = Array.isArray(day.movements) && day.movements.length ? day.movements : blankMovements();
    movements.forEach((movement) => addMovementField(card, movement));
  });
}

function setTrainingDayCount(form, requestedCount, sourceDays = null) {
  const count = Math.max(2, Math.min(7, Number(requestedCount) || 3));
  form.trainingDays.value = String(count);
  const current = sourceDays || collectWeeklyDays(form, true);
  const used = new Set(current.map((day) => day.weekday).filter(Boolean));
  const days = Array.from({ length: count }, (_, index) => {
    if (current[index]) return current[index];
    const preferred = DEFAULT_TRAINING_DAYS[index];
    const weekday = (!used.has(preferred) && preferred) || WEEKDAYS.find(([value]) => !used.has(value))?.[0] || "";
    used.add(weekday);
    return { weekday, movements: blankMovements() };
  });
  renderWeeklyDays(form, days);
}

function resetWeeklyProgramForm(form) {
  form.title.value = "";
  form.durationWeeks.value = "4";
  setTrainingDayCount(form, 3, DEFAULT_TRAINING_DAYS.map((weekday) => ({ weekday, movements: blankMovements() })));
}

function renderCoachPrograms() {
  const body = $("[data-coach-programs-body]");
  const empty = $("[data-coach-programs-empty]");
  if (!body) return;
  body.innerHTML = "";
  empty.hidden = coachPanelState.programs.length > 0;
  coachPanelState.programs.forEach((program) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><strong>${escapeHtml(program.memberName)}</strong></td>
      <td>${escapeHtml(program.title)}</td>
      <td>${formatDate(program.updatedAt)}</td>
      <td><button class="table-action" type="button" data-edit-program="${program.id}">ویرایش</button> · <button class="table-action danger" type="button" data-delete-program="${program.id}">حذف</button></td>
    `;
    body.appendChild(row);
  });
  $$('[data-edit-program]', body).forEach((button) => button.addEventListener("click", () => {
    const program = coachPanelState.programs.find((item) => item.id === Number(button.dataset.editProgram));
    const form = $("[data-coach-program-form]");
    if (!program || !form) return;
    form.memberId.value = String(program.memberId);
    form.title.value = program.title;
    form.durationWeeks.value = String(program.durationWeeks || 4);
    const days = Array.isArray(program.days) && program.days.length ? program.days : DEFAULT_TRAINING_DAYS.map((weekday) => ({ weekday, movements: blankMovements() }));
    setTrainingDayCount(form, Math.max(2, days.length), days);
    document.getElementById("program-editor")?.scrollIntoView({ behavior: "smooth" });
  }));
  $$('[data-delete-program]', body).forEach((button) => button.addEventListener("click", async () => {
    const program = coachPanelState.programs.find((item) => item.id === Number(button.dataset.deleteProgram));
    if (!program || !window.confirm(`برنامه «${program.title}» حذف شود؟`)) return;
    button.disabled = true;
    try {
      await api(`/api/coach/programs/${program.id}`, { method: "DELETE", body: "{}" });
      await loadCoachPrograms();
    } catch (error) {
      alert(error.message);
      button.disabled = false;
    }
  }));
  $("[data-coach-program-count]").textContent = toFa(coachPanelState.programs.length);
}

async function loadCoachPrograms() {
  const result = await api("/api/coach/programs");
  coachPanelState.programs = result.programs;
  renderCoachPrograms();
}

async function initCoachPanel() {
  const root = $("[data-coach-panel]");
  if (!root) return;
  const user = await protectPage("coach");
  if (!user) return;
  const profileForm = $("[data-coach-profile-form]");
  const programForm = $("[data-coach-program-form]");
  setTrainingDayCount(programForm, 3, DEFAULT_TRAINING_DAYS.map((weekday) => ({ weekday, movements: blankMovements() })));
  programForm.trainingDays.addEventListener("input", () => {
    const requestedCount = Number(programForm.trainingDays.value);
    if (requestedCount >= 2 && requestedCount <= 7) setTrainingDayCount(programForm, requestedCount);
  });
  try {
    const [profileResult, membersResult, programsResult] = await Promise.all([
      api("/api/coach/profile"),
      api("/api/coach/members"),
      api("/api/coach/programs"),
    ]);
    coachPanelState.coach = profileResult.coach;
    coachPanelState.members = membersResult.members;
    coachPanelState.programs = programsResult.programs;
    $("[data-coach-name]").textContent = profileResult.coach.fullName || "پروفایل تکمیل نشده";
    $("[data-coach-mobile]").textContent = toFa(profileResult.coach.mobile);
    $("[data-coach-plan-count]").textContent = toFa(profileResult.coach.plans.length);
    $("[data-coach-member-count]").textContent = toFa(membersResult.members.length);
    profileForm.fullName.value = profileResult.coach.fullName || "";
    profileForm.specialty.value = profileResult.coach.specialty || "";
    profileForm.bio.value = profileResult.coach.bio || "";
    const planBox = $("[data-coach-plans]");
    planBox.innerHTML = "";
    profileResult.coach.plans.forEach((plan) => {
      const span = document.createElement("span");
      span.textContent = plan;
      planBox.appendChild(span);
    });
    const memberSelect = programForm.memberId;
    memberSelect.innerHTML = '<option value="">یک ورزشکار را انتخاب کنید</option>';
    membersResult.members.forEach((member) => {
      const option = document.createElement("option");
      option.value = member.id;
      option.textContent = `${member.fullName} — ${member.plan}`;
      memberSelect.appendChild(option);
    });
    renderCoachPrograms();
    root.classList.add("is-ready");
  } catch (error) {
    if (error.status === 403) window.location.replace(accountDestination(user));
    else alert(error.message);
    return;
  }

  profileForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearFieldErrors(profileForm);
    setFormMessage(profileForm);
    const button = $("button[type='submit']", profileForm);
    setBusy(button, true, "در حال ذخیره…");
    try {
      const result = await api("/api/coach/profile", {
        method: "PATCH",
        body: JSON.stringify({
          fullName: profileForm.fullName.value.trim(),
          specialty: profileForm.specialty.value.trim(),
          bio: profileForm.bio.value.trim(),
        }),
      });
      coachPanelState.coach = result.coach;
      $("[data-coach-name]").textContent = result.coach.fullName;
      setFormMessage(profileForm, "پروفایل با موفقیت ذخیره شد.", "success");
    } catch (error) {
      if (error.field) setFieldError(profileForm, error.field, error.message);
      else setFormMessage(profileForm, error.message);
    } finally {
      setBusy(button, false);
    }
  });

  programForm.addEventListener("submit", async (event) => {
    event.preventDefault();
    clearFieldErrors(programForm);
    setFormMessage(programForm);
    const button = $("button[type='submit']", programForm);
    setBusy(button, true, "در حال ذخیره…");
    try {
      await api("/api/coach/programs", {
        method: "POST",
        body: JSON.stringify({
          memberId: programForm.memberId.value,
          title: programForm.title.value.trim(),
          durationWeeks: programForm.durationWeeks.value,
          days: collectWeeklyDays(programForm, false),
        }),
      });
      setFormMessage(programForm, "برنامه تمرینی ذخیره و برای عضو قابل مشاهده شد.", "success");
      resetWeeklyProgramForm(programForm);
      await loadCoachPrograms();
    } catch (error) {
      if (error.field) setFieldError(programForm, error.field, error.message);
      else setFormMessage(programForm, error.message);
    } finally {
      setBusy(button, false);
    }
  });
}

function statusLabel(status) {
  return { active: "فعال", pending: "در انتظار مراجعه", suspended: "تعلیق‌شده" }[status] || status;
}

function roleLabel(role) {
  return { admin: "مدیر", staff: "پذیرش", coach: "مربی", member: "عضو" }[role] || role;
}

function renderUsers(users) {
  const body = $("[data-users-body]");
  const empty = $("[data-users-empty]");
  if (!body) return;
  body.innerHTML = "";
  empty.hidden = users.length > 0;
  users.forEach((user) => {
    const row = document.createElement("tr");
    row.innerHTML = `
      <td><strong>${escapeHtml(user.fullName)}</strong><small>${toFa(user.mobile)}</small></td>
      <td>${roleLabel(user.role)}</td>
      <td>${escapeHtml(user.plan)}</td>
      <td>${formatDate(user.joinedAt)}</td>
      <td><span class="status-text ${user.status === "active" ? "active" : "inactive"}"><i></i>${statusLabel(user.status)}</span></td>
      <td>${user.role === "admin" || !user.webLinked ? "—" : `<button class="table-action" type="button" data-status-user="${user.id}" data-next-status="${user.status === "active" ? "suspended" : "active"}">${user.status === "active" ? "تعلیق حساب" : "فعال‌کردن"}</button>`}</td>
    `;
    body.appendChild(row);
  });
  $$('[data-status-user]', body).forEach((button) => {
    button.addEventListener("click", async () => {
      button.disabled = true;
      try {
        await api(`/api/admin/users/${button.dataset.statusUser}/status`, {
          method: "PATCH",
          body: JSON.stringify({ status: button.dataset.nextStatus }),
        });
        await loadUsers();
      } catch (error) {
        alert(error.message);
      } finally {
        button.disabled = false;
      }
    });
  });
}

function escapeHtml(value) {
  const element = document.createElement("span");
  element.textContent = value ?? "";
  return element.innerHTML;
}

async function loadUsers(search = "") {
  const result = await api(`/api/admin/users${search ? `?search=${encodeURIComponent(search)}` : ""}`);
  renderUsers(result.users);
  $("[data-total-users]").textContent = toFa(result.users.length);
  $("[data-active-users]").textContent = toFa(result.users.filter((user) => user.status === "active").length);
  $("[data-new-users]").textContent = toFa(
    result.users.filter((user) => Date.now() - new Date(user.joinedAt).getTime() < 30 * 86400000).length,
  );
}

async function initAdmin() {
  const root = $("[data-admin]");
  if (!root) return;
  const user = await protectPage("admin");
  if (!user) return;
  $("[data-admin-name]").textContent = user.fullName;
  const search = $("[data-user-search]");
  let timer;
  search?.addEventListener("input", () => {
    clearTimeout(timer);
    timer = setTimeout(() => loadUsers(search.value.trim()), 250);
  });
  await loadUsers();
  root.classList.add("is-ready");
}

document.addEventListener("DOMContentLoaded", () => {
  initMobileNavigation();
  initNumericInputs();
  initAuthLink();
  initPasswordToggles();
  initLogin();
  initSignup();
  initLogout();
  initDashboard();
  initAdmin();
  initPending();
  initCoachPanel();
});
