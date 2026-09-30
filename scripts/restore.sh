#!/usr/bin/env bash
set -Eeuo pipefail

if [[ $# -ne 1 ]]; then
  echo "Usage: $0 <backup-prefix-or-directory>" >&2
  echo "This restores to a new drill database and local media directory; it never overwrites the live database." >&2
  exit 2
fi

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
compose_file="${COMPOSE_FILE:-docker-compose.yml}"
input="$1"
if [[ -d "$input" ]]; then
  backup_dir="$input"
  prefix="$(basename "$input")"
else
  backup_dir="$(dirname "$input")"
  prefix="$(basename "$input")"
fi
backup_dir="$(cd "$backup_dir" && pwd)"
dump_file="$backup_dir/${prefix}.dump"
media_file="$backup_dir/${prefix}.media.tar.gz"
manifest_file="$backup_dir/${prefix}.sha256"

for file in "$dump_file" "$media_file" "$manifest_file"; do
  if [[ ! -f "$file" ]]; then
    echo "Required backup file missing: $file" >&2
    exit 1
  fi
done

(
  cd "$backup_dir"
  sha256sum --check "${prefix}.sha256"
)
docker compose -f "$compose_file" exec -T db \
  sh -ec 'pg_restore --list' < "$dump_file" > /dev/null
tar -tzf "$media_file" > /dev/null

restore_database="${RESTORE_DATABASE:-helpdesk_restore_drill_$(date -u +%Y%m%d%H%M%S)}"
if [[ ! "$restore_database" =~ ^[a-z][a-z0-9_]{0,62}$ ]]; then
  echo "RESTORE_DATABASE must be a lowercase PostgreSQL identifier." >&2
  exit 2
fi
restore_dir="$repo_root/restore-drill/$prefix"
mkdir -p "$restore_dir/media"

docker compose -f "$compose_file" exec -T -e RESTORE_DATABASE="$restore_database" db \
  sh -ec 'createdb -U "$POSTGRES_USER" "$RESTORE_DATABASE"'
docker compose -f "$compose_file" exec -T -e RESTORE_DATABASE="$restore_database" db \
  sh -ec 'pg_restore --exit-on-error --no-owner -U "$POSTGRES_USER" -d "$RESTORE_DATABASE"' \
  < "$dump_file"
tar -xzf "$media_file" -C "$restore_dir/media"

printf 'Restore drill complete. Database: %s; media: %s\n' "$restore_database" "$restore_dir/media"
printf 'Inspect the restored database, then remove it explicitly when the drill is complete.\n'
