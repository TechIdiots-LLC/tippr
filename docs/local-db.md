Local Postgres + Cassandra for development

This repository expects both Cassandra (primary datastore) and Postgres (relational/migration source).

Quick start (requires Docker):

PowerShell (Windows):

```powershell
# Start containers in background
docker compose -f docker-compose.local.yml up -d

# Wait until services accept connections
python .\tools\wait_for_dbs.py

# Connect examples
# Postgres: you'll be prompted for password 'tippr'
psql -h localhost -U tippr -d tippr

# Cassandra (CQL shell)
cqlsh localhost 9042

# Stop and remove containers + volumes when done
docker compose -f docker-compose.local.yml down -v
```

Bash (Linux/macOS):

```bash
docker compose -f docker-compose.local.yml up -d
python tools/wait_for_dbs.py
psql -h localhost -U tippr -d tippr
cqlsh localhost 9042
docker compose -f docker-compose.local.yml down -v
```

Notes:
- Cassandra may take a minute or two to finish initial startup; `tools/wait_for_dbs.py` polls TCP ports.
Bootstrap via app (auto-create tables)
- If you don't have `docker compose`, try `docker-compose`.
- Default Postgres creds: `tippr` / `tippr`.
- Example configuration keys are in `r2/example.ini` for connecting pools.

Next steps (optional):
- Initialize Postgres schema or load dumps from `scripts/migrate/`.
- Use `scripts/migrate/tuples_to_sstables.py` to produce sstables for Cassandra if migrating data.

Create keyspace / DB (one-off)
 
PowerShell:

```powershell
# Create Postgres DB and user (run as an admin account)
sudo -u postgres psql -c "CREATE USER tippr WITH PASSWORD 'tippr';"
sudo -u postgres psql -c "CREATE DATABASE tippr OWNER tippr;"

# Create Cassandra keyspace (when Cassandra is up). Adjust path if using local tarball.
# If using the docker compose above you can instead run `docker exec -it <cassandra> cqlsh`.
cqlsh localhost 9042 -e "CREATE KEYSPACE IF NOT EXISTS tippr WITH replication = {'class':'SimpleStrategy','replication_factor':'1'};"
```

Bash:

```bash
# Create Postgres DB/user
psql -h 127.0.0.1 -U postgres -c "CREATE USER tippr WITH PASSWORD 'tippr';"
psql -h 127.0.0.1 -U postgres -c "CREATE DATABASE tippr OWNER tippr;"

# Create Cassandra keyspace when CQL is available
cqlsh 127.0.0.1 9042 -e "CREATE KEYSPACE IF NOT EXISTS tippr WITH replication = {'class':'SimpleStrategy','replication_factor':'1'};"
```
