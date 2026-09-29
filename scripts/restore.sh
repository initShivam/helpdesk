#!/bin/bash
# scripts/restore.sh
set -e

if [ ! -f "./helpdesk_backup.dump" ]; then
  echo "Backup file ./helpdesk_backup.dump not found!"
  exit 1
fi

echo "Copying backup file to db container..."
docker cp ./helpdesk_backup.dump helpdesk-db-1:/tmp/helpdesk_backup.dump

echo "Restoring database from backup..."
# Drop and recreate schema, or clean existing tables using pg_restore options
docker exec helpdesk-db-1 pg_restore -U postgres -d helpdesk --clean --if-exists /tmp/helpdesk_backup.dump

echo "Restore completed successfully!"
