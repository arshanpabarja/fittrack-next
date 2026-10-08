# LifeBox Coach Panel

The Persian, right-to-left workspace is served at `/coach-panel`. It uses the existing LifeBox yellow accent, bundled Vazirmatn font and Tabler icons. No frontend packages or build step are required.

## Available workflows

- Dashboard with four coaching metrics, a program shortcut and the client directory.
- Searchable client directory with program goal, training style, new membership, program, attendance and remaining-session filters.
- Client profiles with membership information, current program and previous versions, sessions and device attendance.
- Structured program editor with alphabetically sorted Persian client names, Persian calendar start/end dates and one training day by default. Days can be added up to seven; exercises contain only name, sets and repetitions. Editing or replacing preserves the previous version; duplication lets the coach choose another client. Archiving preserves history.
- Existing session history, cancellation, no-show and completion. Calendar and booking have been removed from the UI and the session collection accepts GET only. Existing session records remain available.
- Session mode with editable weights/repetitions, saved set completion and skipped or added exercises. Closed sessions cannot be rewritten.
- Shared exercise library plus coach-private custom exercises, instructions, common mistakes and optional HTTPS media links.
- Coach profile and own performance metrics. Commission fields are omitted because this app has no commission source.
- Mobile navigation, keyboard-accessible dialogs, loading/error/empty states and light/dark appearance.

## Data and permissions

Client access follows the existing LifeBox policy: active site members with an active application in the coach's permitted plans. A plan withdrawn from new signup remains accessible to its permitted coaches; removing it from a coach's permissions immediately hides its clients and their records. This is plan-based access, not a new individual assignment system. Reception's existing account provisioning links gym members to site accounts.

Programs, sessions and custom exercises belong to their authoring coach. Shared access to a membership plan does not grant access to another coach's training records. APIs require an active coach account, retain Django CSRF protection and return `no-store` responses.

Assessments, training profiles, progress charts and coach notes have been removed from the workspace. Assessment/note endpoints are unregistered, and client details are read-only. Existing database tables and historical fields are retained for migration compatibility; none of their assessment/profile/note data is exposed by the coach APIs, including notes inside old program snapshots and exercise logs. No data deletion migration is required. The client goal now comes from the current program; the new-client filter uses the first 30 days of membership.

The program editor sends Persian dates with `dateCalendar: "persian"`. The API validates month lengths and leap days using the existing gym calendar conversion, then stores Gregorian database dates. Existing API clients that omit the calendar parameter retain ISO date support. Dates displayed in the coach workspace use the Persian calendar.

Client serializers expose training-relevant fields only. They exclude mobile numbers, identity numbers, family details, address, authentication data, biometric data and payments. The face-registration field is a boolean. The coach may edit their own name, specialty and biography.

Attendance is read from the configured reception SQLite database or synchronized attendance records. It cannot be entered manually in this panel. Missing attendance is shown as unavailable and is not used as evidence of inactivity. Attendance history shows the latest 100 visits with the total count. Alerts use 7/14 days of recorded absence and a decrease of more than half between consecutive two-week periods with at least three prior visits.

Workout logs never alter reception attendance or membership session allowances. Session counters on the dashboard count individual workout records, including individual records within a semi-private group. Programs need attention within seven days of their end date. Clients without a current program appear in the program filter.

Performance sessions cover the current Gregorian month through today. Weekly attendance is the percentage of active clients who visited within seven days. Membership continuity is the percentage of clients who joined before this month and still have active membership. These definitions appear in the interface.

## Rollout

Back up the configured database, then apply the additive migrations on the target environment before starting the updated application:

```powershell
.\.venv\Scripts\python.exe web_portal/manage.py migrate --noinput
```

Migrations `0011_coach_workspace` and `0012_exercise_library` add the training models, program metadata and ten shared exercise entries. They do not change reception member records. Existing text programs remain readable and can be edited through the new program builder. The release builder includes `coach.js`, `coach.css` and all migrations.

## Verification

The coaching tests cover client data allowlists, authorization/revocation, retired-feature removal and historical-field privacy, Persian date validation/conversion, minimal program exercises, disabled booking, CSRF, immutable session completion, program history and separation from attendance/session allowances.

```powershell
.\.venv\Scripts\python.exe web_portal/manage.py test members.test_coaching members.tests.CoachPanelFlowTests --noinput
node --check lifebox-landing/coach.js
```

Browser QA uses a separate preview database with fictional clients under ignored `state/coach-panel-preview`. The simplified program workflow is checked through the real form, including client sorting, the one-day default, Persian date validation, saving and reopening a program. It is not production data.
