# LifeBox member panel

The member workspace lives at `/dashboard`, in the existing Persian RTL Django site. Its styling and script are isolated in `lifebox-landing/member.css` and `lifebox-landing/member.js`.

## Installation

Run the migrations against the same configured database used by the Django service before serving the new panel:

```powershell
.\.venv\Scripts\python.exe web_portal/manage.py migrate
```

Migration `0013_member_panel` creates three new tables for personal workout logs, support requests, and member preferences. It does not change existing membership, attendance, or biometric data. The web release builder includes the new assets and migration.

## Member experience

- Dashboard: remaining sessions, validity, last visit, monthly attendance, training day, program, coach, and next session.
- Membership: the reception plan and calendar rules, session usage, renewal records, and face registration status.
- Program: a read-only list of movement names, set counts, and repetitions, grouped by training day.
- Workout: resume the current training day, see movement names, set counts, and prescribed repetitions, then finish the workout. No individual set inputs, personal notes, or manual save action appear. Finishing records the end time without fabricating weight or repetition results and does not consume a reception attendance session.
- Attendance: only the linked member's device records, with a Saturday-based week and Jalali month totals.
- Coach and sessions: assigned coach information, program link, session dates and statuses. No coach guidance panel, next-session card in the coach view, or scheduling request appears.
- Payments: the member's reception payment records, outstanding balance, and downloadable plain-text receipts.
- Notifications: membership limits, program changes, payment registration, next session, and coach contact replies; read state is saved.
- Profile: registration information and notification badge preferences.
- Assessments, body measurements, assessment notifications, and the progress view are excluded from the member workspace and its startup data.
- Renewal, payment follow-up, plan changes, membership freezes, identity changes, password changes, other-device logout, and the support page have been removed from the member interface. Existing server records and API compatibility are preserved.

Both themes honor the system preference and offer a manual toggle. Mobile navigation supports keyboard focus, Escape, and a drawer. Only the theme preference is stored in the browser; personal records remain on the server.

Startup data is embedded with Django's escaped JSON serializer on the authenticated, uncached page. A compressed WOFF2 version of the original variable font preserves its complete character set. Member HTML, CSS, JavaScript, and workspace JSON use Django's standard gzip implementation when supported by the browser.

## Reception and coach review

The owner can review requests, update status, and write replies through the existing Django admin's **Member requests** model. A request never applies a membership freeze, renewal, identity change, or scheduling change automatically.

Coaches can review completed member workout results in **Clients → member → Sessions**, alongside their own scheduled sessions. Access remains limited by the existing coach/client permissions.

## Integration boundaries

Online payment and direct messaging are not configured in this repository. The remaining coach contact action submits a reception/contact request; its reply appears in notifications. No payment is simulated. Historical payment methods are labeled as reception records because the stored data does not identify a gateway or card method. Receipts reflect recorded amounts, not an independently verified gateway response.

The coach model has no profile photograph field; the interface uses a name-based identity rather than an unrelated portrait. Historical membership dates use the recorded membership start when available and the same one-Jalali-month reception rule. Lists show up to 100 workout logs, requests and recent visits, and 200 scheduled session records. Missing source data is labeled as unavailable.

## Verification

The member tests cover active-account authorization, member record isolation, biometric exclusion, preservation of coach prescriptions, valid set results, workout resumption, coach review, receipts, requests, preferences, password changes, and CSRF. Run:

```powershell
.\.venv\Scripts\python.exe run_web_tests.py
```

The runner uses a temporary file database so the account provisioning and SQLite backup tests can run alongside the other web tests. It does not migrate or provision the configured gym database.

Browser QA uses an isolated synthetic database. The simplified interface was checked across the seven edited tabs, including finishing a workout without set logging. The preview script covers the 10 remaining sections at desktop and mobile widths in both themes, receipt download, settings persistence, and keyboard navigation. Its sample records do not modify the gym database.
