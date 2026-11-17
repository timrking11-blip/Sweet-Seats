# PowerShell version of scripts/apply-migrations.sh, for the owner's Windows machine.
# Applies supabase/migrations in filename order, each file in its own transaction,
# recording what was applied so a re-run applies only new files. Needs psql on PATH.
#
#   $env:SWEET_SEATS_MIGRATION_URL = "postgresql://..."   # never commit or echo it
#   .\scripts\apply-migrations.ps1 -DryRun
#   .\scripts\apply-migrations.ps1
#
# Run from the repository root. A file already recorded with different contents stops
# the run: applied migrations are never edited.
param([switch]$DryRun)
$ErrorActionPreference = "Stop"

$url = $env:SWEET_SEATS_MIGRATION_URL
if (-not ($url -match '^postgres(ql)?://')) {
  Write-Error "SWEET_SEATS_MIGRATION_URL must be a postgres:// or postgresql:// URL"
  exit 2
}

function Invoke-Psql([string]$Sql) {
  $out = $Sql | & psql $url -v ON_ERROR_STOP=1 -X -q -t -A
  if ($LASTEXITCODE -ne 0) { throw "psql failed" }
  return $out
}

Invoke-Psql @"
set client_min_messages = warning;
create schema if not exists sweet_seats_ops;
create table if not exists sweet_seats_ops.applied_migrations (
  filename text primary key, sha256 text not null, applied_at timestamptz not null default now());
revoke all on schema sweet_seats_ops from public;
"@ | Out-Null

$applied = 0
foreach ($file in Get-ChildItem supabase/migrations -Filter *.sql | Sort-Object Name) {
  $name = $file.Name
  $sum = (Get-FileHash $file.FullName -Algorithm SHA256).Hash.ToLower()
  $recorded = Invoke-Psql "select sha256 from sweet_seats_ops.applied_migrations where filename = '$name';"
  if ($recorded) {
    if ($recorded.Trim() -ne $sum) {
      Write-Error "STOP $name changed after it was applied (recorded $recorded)"
      exit 3
    }
    continue
  }
  if ($DryRun) { Write-Output "would apply $name"; continue }
  Write-Output "applying $name"
  $body = Get-Content $file.FullName -Raw
  Invoke-Psql @"
begin;
select pg_advisory_xact_lock(hashtext('sweet_seats_migrations'));
$body
insert into sweet_seats_ops.applied_migrations (filename, sha256) values ('$name', '$sum');
commit;
"@ | Out-Null
  $applied++
}
Write-Output "$applied migration(s) applied"
