# Database operations

Local initialization uses `deploy/init-db.sh` to create a non-owner `crm_runtime`
identity, revoke public schema creation, and install `pg_trgm`/`btree_gist`.
Run migrations with the separate owner credential in `MIGRATION_DATABASE_URL`:

```sh
uv run alembic upgrade head
uv run alembic check
```

The initial migration creates six tables and adds circular created/updated/deleted-by
references only after users exists. It grants runtime CRUD without business DELETE,
audit SELECT/INSERT with sequence access, and token/challenge cleanup privileges.
The runtime role cannot update/delete/truncate audit or delete/truncate business rows.
Role creation is an operator responsibility before migrations; if provisioning a remote
database, create the role and revoke inherited/public privileges there too. Never use
the schema owner in `DATABASE_URL` or give the runtime role ownership/membership in it.

The migration never creates accounts. Bootstrap the Supervisor only after migration.
For a failed production deployment, stop the API, retain the database, and use a forward
fix or restore a verified backup. Downgrade destroys schema/data and is appropriate
only in disposable test environments. Normal delete APIs must retain business rows.

Docker containers read `.env`; production should inject secrets from a deployment secret
store. Do not print `docker compose config` or connection strings into shared logs.
# POS database and file storage

See [POS management](pos.md) for the eleven-table migration, runtime privileges,
seeded global thresholds, and bounded import settings. Provision
`IMPORT_STORAGE_DIR` on persistent private storage and back it up with PostgreSQL.
Apply migrations using the owner connection before restarting the updated API.
