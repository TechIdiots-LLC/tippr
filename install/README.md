# Installer scripts

The scripts `../install-tippr.sh` runs to set up tippr on Ubuntu 24.04. To
install a site, see [docs/INSTALL_tippr.md](../docs/INSTALL_tippr.md); this
is for working on the installer itself.

- `install.cfg`: the settings and their defaults (the `TIPPR_*` variables).
- `tippr.sh`: the main installer, run as root by `install-tippr.sh`; it
  calls the others.
- `install_apt.sh`, `install_services.sh`, `install_cassandra.sh`,
  `install_zookeeper.sh`, `install_opensearch.sh`: packages and services.
- `setup_postgres.sh`, `setup_cassandra.sh`, `setup_rabbitmq.sh`,
  `setup_mcrouter.sh`, `postgres_functions.sql`: the data stores.
- `done.sh`: the summary printed at the end.

Re-running the installer must stay safe: it keeps generated passwords and
secrets (`/etc/tippr/secrets.env`) and the site's data, and regenerates the
config and systemd units.

If you add a file here, add it to `NEEDED` in `../install-tippr.sh`, which
checks they're all present before starting.

## Testing changes

The `ci-install-tippr.yml` workflow (and the GitLab pipeline) run the whole
installer on a fresh Ubuntu 24.04 runner. Before that, try it on a fresh VM
or container, with a `.local` domain for a development install:

```bash
TIPPR_USER=tippr TIPPR_DOMAIN=tippr.local TIPPR_YES=1 ./install-tippr.sh
```

and once more on the same machine, to check a re-run (an upgrade) works.
