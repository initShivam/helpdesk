#!/usr/bin/env bash
set -Eeuo pipefail
umask 077

repo_root="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$repo_root"
compose_file="${COMPOSE_FILE:-docker-compose.yml}"
backup_dir="${1:-$repo_root/backups}"
timestamp="$(date -u +%Y%m%dT%H%M%SZ)"
prefix="helpdesk_${timestamp}"

mkdir -p "$backup_dir"
dump_tmp="$backup_dir/.${prefix}.dump.tmp"
media_tmp="$backup_dir/.${prefix}.media.tar.gz.tmp"
trap 'rm -f "$dump_tmp" "$media_tmp"' EXIT

docker compose -f "$compose_file" exec -T db \
  sh -ec 'pg_dump -U "$POSTGRES_USER" -d "$POSTGRES_DB" --format=custom' > "$dump_tmp"
docker compose -f "$compose_file" run --rm --no-deps --entrypoint sh celery \
  -ec 'tar -czf - -C /app/media .' > "$media_tmp"

mv "$dump_tmp" "$backup_dir/${prefix}.dump"
mv "$media_tmp" "$backup_dir/${prefix}.media.tar.gz"
(
  cd "$backup_dir"
  sha256sum "${prefix}.dump" "${prefix}.media.tar.gz" > "${prefix}.sha256"
)

trap - EXIT
printf 'Backup created: %s\n' "$backup_dir/$prefix"
