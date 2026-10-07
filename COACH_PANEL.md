# LifeBox Coach Panel

The Persian, right-to-left workspace is served at `/coach-panel`. It uses the existing LifeBox yellow accent, bundled Vazirmatn font and Tabler icons. No frontend packages or build step are required.

## Available workflows

- Dashboard with seven coaching metrics, today's sessions, prioritized alerts and quick actions.
- Searchable client directory with goal, training style, assessment, program, attendance and remaining-session filters.
- Client profiles with training information, current program and previous versions, assessments, progress, sessions, device attendance and private notes.
- Structured program editor with one to seven training days and exercise sets, repetitions, weight, rest, RPE, RIR, tempo and notes. Editing or replacing preserves the previous version; duplication lets the coach choose another client. Archiving preserves history.
- Append-only assessments, chronological comparisons and body/performance charts. Other exercise progress comes from the maximum completed-set weight in completed sessions; it is not an estimated one-rep max.
- Private and semi-private bookings, daily/weekly schedules, cancellation, no-show and completion. A group has an individual workout record per participant. Overlapping private bookings are rejected.
- Session mode with editable weights/repetitions, saved set completion, skipped or added exercises, private quick notes and end-of-session notes. Closed sessions cannot be rewritten.
- Shared exercise library plus coach-private custom exercises, instructions, common mistakes and optional HTTPS media links.
- Coach profile and own performance metrics. Commission fields are omitted because this app has no commission source.
- Mobile navigation, keyboard-accessible dialogs, loading/error/empty states and light/dark appearance.

## Data and permissions

Client access follows the existing LifeBox policy: active site members with an active application in the coach's permitted plans. A plan withdrawn from new signup remains accessible to its permitted coaches; removing it from a coach's permissions immediately hides its clients and their records. This is plan-based access, not a new individual assignment system. Reception's existing account provisioning links gym members to site accounts.

Training profiles, assessments, programs, sessions, custom exercises and notes belong to their authoring coach. Shared access to a membership plan does not grant access to another coach's training records. APIs require an active coach account, retain Django CSRF protection and return `no-store` responses.

Client serializers expose training-relevant fields only. They exclude mobile numbers, identity numbers, family details, address, authentication data, biometric data and payments. The face-registration field is a boolean. The coach may edit their own name, specialty and biography.

Attendance is read from the configured reception SQLite database or synchronized attendance records. It cannot be entered manually in this panel. Missing attendance is shown as unavailable and is not used as evidence of inactivity. Attendance history shows the latest 100 visits with the total count. Alerts use 7/14 days of recorded absence and a decrease of more than half between consecutive two-week periods with at least three prior visits.

Workout logs never alter reception attendance or membership session allowances. Session counters on the dashboard count individual workout records, including individual records within a semi-private group. Assessments become due after 30 days; programs need attention within seven days of their end date. New clients need an initial assessment and a program.

Performance sessions cover the current Gregorian month through today. Weekly attendance is the percentage of active clients who visited within seven days. Membership continuity is the percentage of clients who joined before this month and still have active membership. These definitions appear in the interface.

## Rollout

Back up the configured database, then apply the additive migrations on the target environment before starting the updated application:

```powershell
.\.venv\Scripts\python.exe web_portal/manage.py migrate --noinput
```

Migrations `0011_coach_workspace` and `0012_exercise_library` add the training models, program metadata and ten shared exercise entries. They do not change reception member records. Existing text programs remain readable and can be edited through the new program builder. The release builder includes `coach.js`, `coach.css` and all migrations.

## Verification

The coaching tests cover client data allowlists, authorization/revocation, private records, input validation, CSRF, immutable session completion, comparisons, program history, group booking, coach booking conflicts, and separation from attendance/session allowances.

```powershell
.\.venv\Scripts\python.exe web_portal/manage.py test members.test_coaching members.tests.CoachPanelFlowTests --noinput
node --check lifebox-landing/coach.js
```

Browser QA uses a separate preview database with fictional clients under ignored `state/coach-panel-preview`. It checks the main navigation screens, writes through the real API, exercises session completion and group booking, and verifies mobile layout and light/dark themes. It is not production data.
