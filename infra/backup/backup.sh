#!/usr/bin/env bash
# Daily encrypted pg_dump, off-site copy, 30 daily + 12 monthly retention (design doc 16.4).
# Cron (as root on the VPS):  15 2 * * * /opt/kampungadem/infra/backup/backup.sh
# Requires: docker, gpg with BACKUP_GPG_RECIPIENT's public key, rclone with BACKUP_REMOTE set up.
# Test a restore every month: see docs/deploy.md.
set -euo pipefail
cd "$(dirname "$0")/.."
set -a; source .env; set +a

DIR=/var/backups/kampungadem
mkdir -p "$DIR/daily" "$DIR/monthly"
STAMP=$(date +%F)
FILE="$DIR/daily/kampungadem-$STAMP.dump.gpg"

for db in kampungadem chirpstack; do
  docker compose -f docker-compose.yml exec -T db pg_dump -U kampungadem -Fc "$db" \
    | gpg --batch --yes --encrypt --recipient "$BACKUP_GPG_RECIPIENT" \
    > "${FILE/kampungadem-/$db-}"
done

if [ "$(date +%d)" = "01" ]; then
  cp "$DIR"/daily/*-"$STAMP".dump.gpg "$DIR/monthly/"
fi

find "$DIR/daily" -name '*.dump.gpg' -mtime +30 -delete
find "$DIR/monthly" -name '*.dump.gpg' -mtime +370 -delete

if [ -n "${BACKUP_REMOTE:-}" ]; then
  rclone sync "$DIR" "$BACKUP_REMOTE"
fi
echo "backup $STAMP ok"
