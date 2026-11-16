#!/bin/sh
set -eu
psql --username "$POSTGRES_USER" --dbname "$POSTGRES_DB" --set ON_ERROR_STOP=1 <<'SQL'
\getenv runtime_password RUNTIME_DB_PASSWORD
CREATE ROLE crm_runtime LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOINHERIT;
SELECT format('ALTER ROLE crm_runtime PASSWORD %L', :'runtime_password') \gexec
REVOKE CREATE ON SCHEMA public FROM PUBLIC;
GRANT USAGE ON SCHEMA public TO crm_runtime;
CREATE EXTENSION IF NOT EXISTS pg_trgm;
CREATE EXTENSION IF NOT EXISTS btree_gist;
SQL
