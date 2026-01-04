# Tippr

Tippr is a modern fork of the classic reddit codebase, updated for Python 3 and current Linux distributions.

## About

This project is based on the open-source reddit codebase originally released under the Common Public Attribution License (CPAL). The original code is available at https://github.com/reddit-archive/reddit.

**Key Updates:**
- **Python 3:** Fully migrated to Python 3.12 from the original Python 2 codebase
- **Modern Platform:** Targeted for Ubuntu 24.04 LTS (Noble Numbat)
- **Updated Dependencies:** Modernized install scripts, compatibility shims, and build tooling for current packaging systems
- **Active Development:** Ongoing improvements and feature development by TechIdiots LLC

This fork is intended for local development, experimentation, and educational purposes.

## License

This project is licensed under the Common Public Attribution License Version 1.0 (CPAL), the same license as the original reddit code. See the [LICENSE](LICENSE) file for details.

**Attribution:** Based on reddit open-source code. Original code © 2006-2015 tippr Inc.

---

## Quickstart (Ubuntu 24.04)

The following steps produce a development-ready environment on Ubuntu 24.04.

### 1. Create the runtime user
```bash
useradd -m -s /bin/bash tippr
```

### 2. Clone the repository
```bash
git clone https://github.com/TechIdiots-LLC/tippr.git /opt/tippr
cd /opt/tippr
```

### 3. Run the installer

Run as root, specifying the user and domain:
```bash
TIPPR_USER=tippr TIPPR_DOMAIN=tippr.local ./install-tippr.sh
```

The installer will:
- Install system dependencies
- Set up a Python virtual environment at `/home/tippr/venv`
- Configure databases (PostgreSQL, Cassandra)
- Install and configure supporting services (memcached, RabbitMQ, Zookeeper)
- Create systemd service units for the application stack

### 4. Configure DNS

Add the domain to your hosts file (on the host machine if using a VM):
```bash
echo "127.0.0.1 tippr.local" >> /etc/hosts
```

### 5. Access the site

After installation completes and services start, visit `https://tippr.local` in your browser.

## Configuration Options

Customize the installation by setting environment variables before running the installer:

| Variable | Default | Description |
|----------|---------|-------------|
| `TIPPR_USER` | (required) | User to run tippr as |
| `TIPPR_DOMAIN` | `tippr.local` | Domain for the site (must contain a dot) |
| `TIPPR_HOME` | `/home/$TIPPR_USER` | Base directory for install |
| `TIPPR_VENV` | `/home/$TIPPR_USER/venv` | Python virtual environment location |
| `TIPPR_PLUGINS` | `about gold` | Space-separated list of plugins to install |
| `PYTHON_VERSION` | `3.12` | Python version to use |

Example with custom settings:
```bash
TIPPR_USER=myuser TIPPR_DOMAIN=dev.tippr.local TIPPR_PLUGINS="about gold myaddon" ./install-tippr.sh
```

## Troubleshooting

### Locale Errors

If you encounter locale errors during PostgreSQL database creation:
```bash
localedef -i en_US -f UTF-8 en_US.UTF-8
```

### Domain Requirements

The domain must contain a dot (e.g., `tippr.local`) as browsers don't support cookies for dotless domains like `tippr` or `localhost`.

### Service Management

Check service status:
```bash
systemctl status tippr-serve
systemctl status tippr-websockets
systemctl status tippr-activity
```

View logs:
```bash
journalctl -u tippr-serve -f
```

## Documentation

For detailed installation information, see [INSTALL_tippr.md](INSTALL_tippr.md).

## Contributing

Contributions are welcome! Please feel free to submit issues or pull requests.

## Credits

- **Original Code:** reddit Inc. (2006-2015)
- **Python 3 Migration & Modernization:** TechIdiots LLC (2024-2026)

---

**Note:** This is a development/experimental fork. For the original reddit codebase and historical documentation, see https://github.com/reddit-archive/reddit
