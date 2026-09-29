#!/bin/bash
# scripts/backup.sh
set -e

# Run pg_dump from within the db container
# The pgvector extension data is inherently backed up because it uses standard Postgres types.
echo "Taking backup of helpdesk database..."
docker exec helpdesk-db-1 pg_dump -U postgres -d helpdesk -F c -f /tmp/helpdesk_backup.dump

echo "Copying backup file from container to local machine..."
docker cp helpdesk-db-1:/tmp/helpdesk_backup.dump ./helpdesk_backup.dump

echo "Backup successful! Saved as ./helpdesk_backup.dump"
