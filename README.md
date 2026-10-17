# Tippr

Tippr is a community site built on the classic reddit codebase, updated
for Python 3 and current Linux, and aimed at self-hosting in production.

## About

This project is based on the open-source reddit codebase, originally
released under the Common Public Attribution License (CPAL). The original
code is at https://github.com/reddit-archive/reddit.

What's different:

- **Python 3.12 on Ubuntu 24.04.** The code is ported from Python 2, with
  current dependencies and packaging.
- **One-command install.** It sets up the app and every service it needs,
  with TLS, generated passwords, systemd units, and production or
  development settings.
- **Search** with OpenSearch.
- **AI content labels:** each post is marked human-made, AI-assisted or
  AI-generated. Vaults can restrict them, and users can hide them.
- **A welcoming default community:** starter vaults leaning toward
  technology, science, making things and fun, including LGBTQ+. The
  content policy explicitly bans hate based on sexual orientation and
  gender identity.
- **Admin pages** for email, Google AdSense and backups, without editing
  config files.
- **Backups and server moves:** export the whole site, copy it to another
  server over HTTPS, and restore it there.
- A new look: teal theme, Noto Sans, the tippr bot.

Developed by TechIdiots LLC.

## License

This project is licensed under the Common Public Attribution License
Version 1.0 (CPAL), the same license as the original reddit code. See the
[LICENSE](LICENSE) file.

**Attribution:** Based on reddit open-source code. Original code © 2006-2015
reddit Inc.

---

## Quickstart (Ubuntu 24.04)

On a fresh server or VM, as root:

```bash
useradd -m -s /bin/bash tippr
git clone https://github.com/TechIdiots-LLC/tippr.git /opt/tippr
cd /opt/tippr
TIPPR_USER=tippr TIPPR_DOMAIN=example.com ./install-tippr.sh
```

A domain ending in `.local`, `.localhost` or `.test` gets a development
install; any other domain gets production settings. For a test site, map
the name to the server in your hosts file (`192.168.1.50 tippr.local`)
and browse to `https://tippr.local`.

The admin account is `tippr`; its password is `TIPPR_ADMIN_PASSWORD` in
`/etc/tippr/secrets.env`. See [docs/INSTALL_tippr.md](docs/INSTALL_tippr.md)
for every option (TLS, Cloudflare, firewall, site name) and what to do
after installing.

## Managing a site

```bash
tippr-start | tippr-stop | tippr-restart     # the whole stack
journalctl -u tippr-paster -f                # web app logs
systemctl list-units 'tippr*'                # service status
sudo tippr-backup export --offline           # back up the site
```

## Documentation

| | |
|---|---|
| [docs/INSTALL_tippr.md](docs/INSTALL_tippr.md) | installing, options, what gets installed, AdSense |
| [docs/ARCHITECTURE.md](docs/ARCHITECTURE.md) | how the pieces fit together and where data lives |
| [docs/BACKUP.md](docs/BACKUP.md) | backups, moving to new servers, restoring |
| [docs/ADMIN_FEATURES.md](docs/ADMIN_FEATURES.md) | admin mode and admin pages |
| [docs/EMAIL.md](docs/EMAIL.md) | outgoing email (SMTP or Gmail) |
| [docs/SEARCH.md](docs/SEARCH.md) | OpenSearch |
| [docs/CONTENT.md](docs/CONTENT.md) | starter vaults and AI content labels |
| [docs/PRIVACY_FEATURES.md](docs/PRIVACY_FEATURES.md) | data export and account deletion |
| [docs/ROADMAP.md](docs/ROADMAP.md) | what's planned |
| [docs/policies/](docs/policies/) | content policy, terms, privacy policy, moderator guidelines |

## Contributing

Contributions are welcome. Please open an issue or a pull request.

## Credits

- **Original code:** reddit Inc. (2006-2015)
- **Python 3 migration and modernization:** TechIdiots LLC (2024-2026)
