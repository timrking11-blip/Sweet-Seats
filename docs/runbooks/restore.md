# Restore drill (G-11)

**Status:** procedure written 18 Nov 2026; **not yet exercised.** The drill needs the
owner's Supabase project and a scratch project to restore into (SS-ADR-006
provisioning). G-11 closes only when a timed record below is filled in from a real run.

## What it proves

- **RPO**, how much data can be lost: the time between the last write that survived and the failure.
- **RTO**, how long recovery takes: the time from "restore started" to "the API answers from the restored database".

Targets are the owner's to set before the first drill. Proposed for the pilot: RPO 24 hours
(daily backups), RTO 2 hours.

## Before the drill

1. Note the production project's backup type (daily logical backups, or point-in-time
   recovery) and the time of the latest backup.
2. Create a **scratch** Supabase project. Never restore over production for a drill.
3. Write a marker row in production with the current time, so the drill can show which
   writes survived. Use the SQL editor as the owner:
   `insert into sweet_seats_ops.applied_migrations (filename, sha256) values ('drill-marker-<ISO time>', repeat('0', 64));`
   Delete the marker after the drill.

## Drill

1. Start the clock (**T0**).
2. Restore the latest backup into the scratch project, using the dashboard's
   Database › Backups, or `pg_restore` of a downloaded logical backup.
3. Run the migration script against the scratch project. It must report
   `0 migration(s) applied`. If it reports more, the backup predates a migration;
   record that.
   - On Linux or macOS: `SWEET_SEATS_MIGRATION_URL=<scratch URL> scripts/apply-migrations.sh --dry-run`.
   - On Windows, in PowerShell:
     ```powershell
     $env:SWEET_SEATS_MIGRATION_URL = "<scratch URL>"
     .\scripts\apply-migrations.ps1 -DryRun
     ```
4. Check the restored data:
   - row counts of `user_profiles`, `notification_subscriptions`, `consent_events`,
     `waitlist_signups` and `alerts` against production;
   - that `consent_events` still refuses an update. Expect `consent_events_are_append_only`.
5. Point a staging API at the scratch project and call `GET /api/health` and `GET /api/v1/events`.
   Stop the clock (**T1**).
6. Delete the scratch project.

## Record (one row per drill)

| Date | Backup time | Marker survived? | Latest surviving write | RPO measured | T0 → T1 (RTO) | Migrations needed | Counts match? | Run by | Notes |
|---|---|---|---|---|---|---|---|---|---|
| _not yet run_ | | | | | | | | | |
