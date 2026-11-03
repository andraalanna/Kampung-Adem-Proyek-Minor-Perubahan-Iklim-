#!/bin/bash
# Runs once on first DB start: separate role + database for ChirpStack (requires pg_trgm).
set -euo pipefail
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" <<-EOSQL
  CREATE ROLE chirpstack WITH LOGIN PASSWORD '${CHIRPSTACK_DB_PASSWORD}';
  CREATE DATABASE chirpstack WITH OWNER chirpstack;
EOSQL
psql -v ON_ERROR_STOP=1 --username "$POSTGRES_USER" --dbname chirpstack <<-EOSQL
  CREATE EXTENSION IF NOT EXISTS pg_trgm;
EOSQL
