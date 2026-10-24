# tippr on Proxmox

Each release includes `tippr-VERSION-proxmox-amd64.tar.zst`. It's a
Proxmox LXC template: Ubuntu 24.04 with the whole site installed (the
single-server layout from [INSTALL_tippr.md](INSTALL_tippr.md)). A
container made from it sets itself up on its first boot. It takes its
domain, makes its own passwords and secrets, a new admin password and a
certificate, then starts.

## Before you start

On the **Proxmox node** (not in the container), raise the memory map limit
OpenSearch needs, and keep it across reboots:

```bash
echo 'vm.max_map_count = 262144' > /etc/sysctl.d/90-tippr.conf
sysctl --system
```

Give the container 4 cores, 8 GB of RAM and 32 GB of disk or more.
Cassandra and OpenSearch use most of the memory.

## Creating the container

1. Download the template into the node's template storage:

   ```bash
   cd /var/lib/vz/template/cache
   wget https://github.com/TechIdiots-LLC/tippr/releases/download/vVERSION/tippr-VERSION-proxmox-amd64.tar.zst
   ```

   (Or upload it on the web UI: *local → CT Templates → Upload*.)

2. Create the container. Its hostname is the site's domain:

   ```bash
   pct create 210 local:vztmpl/tippr-VERSION-proxmox-amd64.tar.zst \
       --hostname forum.example.com --ostype ubuntu --unprivileged 1 \
       --features nesting=1 --cores 4 --memory 8192 --swap 2048 \
       --rootfs local-lvm:32 \
       --net0 name=eth0,bridge=vmbr0,ip=dhcp --onboot 1
   ```

   On the web UI, *Create CT* works the same way: enter the domain as the
   hostname and tick *Nesting* under *Options → Features*.
   `nesting=1` lets systemd run its services' sandboxing in the container.

3. **Optional:** set first-boot settings *before* the first start, for
   example a Let's Encrypt certificate (the domain must already point at
   the container, with ports 80 and 443 reachable) or the site name:

   ```bash
   pct mount 210
   nano /var/lib/lxc/210/rootfs/etc/tippr/firstboot.env
   pct unmount 210
   ```

   Uncomment the lines you need: `TIPPR_DOMAIN` (if it differs from the
   hostname), `TIPPR_LETSENCRYPT_EMAIL`, `TIPPR_SITE_NAME`, or
   `TIPPR_EXTERNAL_PROXY` (below). Any other installer setting works there
   too.

4. Start it and watch the first boot. It re-runs the installer with the
   real settings, which takes about 10–20 minutes:

   ```bash
   pct start 210
   pct exec 210 -- journalctl -u tippr-firstboot -f
   ```

5. Get the admin login when it's done:

   ```bash
   pct exec 210 -- cat /root/tippr-first-login.txt
   ```

Then log in on `https://forum.example.com/` and set up two-factor
authentication; admin mode needs it. After that, use `/admin/site`,
`/admin/email` and `/admin/backups`.

If the hostname isn't a full domain (no dot), the first boot sets up a
development site at `HOSTNAME.local`.

## Behind HAProxy on OPNsense or pfSense (or another proxy)

If HAProxy on the firewall (or another proxy) handles TLS for the domain,
put its address on the container's network in `firstboot.env` before the
first start:

```bash
TIPPR_EXTERNAL_PROXY=192.168.1.1
```

For an HA pair with CARP, list both firewalls' own addresses on that
network and the CARP VIP. HAProxy connects from the active node's own
address, so the VIP alone isn't enough:

```bash
TIPPR_EXTERNAL_PROXY="172.16.1.2 172.16.1.3 172.16.1.1"
```

The container then serves plain HTTP on port 80 with no certificate of its
own, and takes visitors' addresses from the proxy's `X-Forwarded-For`. In
HAProxy:

- the frontend has the certificate (the ACME plugin can get it), and
  redirects port 80 to HTTPS;
- the backend is the container's address, port 80, with *forwardfor*
  (X-Forwarded-For) on;
- set the backend's tunnel timeout to an hour or so, for websockets;
- optionally, health-check `GET /health`.

With Cloudflare in front of the firewall, add `TIPPR_BEHIND_CLOUDFLARE=1`
too. nginx then follows `X-Forwarded-For` back through both Cloudflare and
the firewall to the visitor.
For a container already set up, add the setting to `firstboot.env` and run
`pct exec 210 -- /usr/local/sbin/tippr-firstboot forum.example.com` again. See [INSTALL_tippr.md](INSTALL_tippr.md#behind-another-proxy).

## Changing the domain later

Run the first-boot script again with the new domain. Your data and
passwords are kept:

```bash
pct exec 210 -- /usr/local/sbin/tippr-firstboot new.example.com
```

## Upgrading to a new release

An existing container can be upgraded in place. The site's data isn't in
the source tree: posts and accounts are in PostgreSQL and Cassandra, site
settings in ZooKeeper, uploads in `/srv/www/media`, passwords and secrets
in `/etc/tippr/secrets.env`. So an upgrade replaces the code with the new
release's installer tarball and re-runs the installer. A re-run keeps all
of those; ZooKeeper is only reset on the very first boot. Settings in
`firstboot.env` (such as `TIPPR_EXTERNAL_PROXY`) still apply.

1. **On the node, save a copy first:**

   ```bash
   pct snapshot 210 before-upgrade
   ```

   If the container has a mount point on storage that can't snapshot,
   back up the root disk instead (mount points with `backup=0` are left
   out):

   ```bash
   vzdump 210 --mode snapshot --storage local
   ```

2. **Open a login shell in the container.** Type these one at a time and
   wait for each prompt. Pasted together, the second line is lost while
   the shell starts, and `pct enter` alone has a PATH without
   `/usr/local/bin`:

   ```bash
   pct enter 210
   su -
   ```

3. **Replace the code and re-run the installer** (set `VER` to the new
   release):

   ```bash
   VER=0.4.0
   cd /root
   wget -q https://github.com/TechIdiots-LLC/tippr/releases/download/v$VER/tippr-$VER-installer.tar.gz \
           https://github.com/TechIdiots-LLC/tippr/releases/download/v$VER/SHA256SUMS
   sha256sum --ignore-missing -c SHA256SUMS       # must say OK

   systemctl stop tippr.target
   mv /home/tippr/src /home/tippr/src.old          # kept for rolling back
   install -d -o tippr -g tippr /home/tippr/src
   tar -xzf tippr-$VER-installer.tar.gz -C /home/tippr/src
   chown -R tippr:tippr /home/tippr/src

   install -m 0755 /home/tippr/src/tippr/proxmox/tippr-firstboot /usr/local/sbin/tippr-firstboot
   /usr/local/sbin/tippr-firstboot forum.example.com   # your domain
   ```

   This takes 5–10 minutes and ends with `tippr-firstboot: done`.

4. **Check it:**

   ```bash
   systemctl is-active tippr-paster tippr-websockets nginx
   curl -s -o /dev/null -w '%{http_code}\n' -H 'Host: forum.example.com' http://127.0.0.1/   # 200
   ```

   Then log in and look around. Once you're happy, remove the old code
   (`rm -rf /home/tippr/src.old` in the container) and the snapshot
   (`pct delsnapshot 210 before-upgrade` on the node).

**Rolling back:** `pct rollback 210 before-upgrade` (or restore the
vzdump backup) returns the container, data included, to the moment of the
copy. To go back to the old code only, keeping data written since, put
`/home/tippr/src.old` back in place of `/home/tippr/src` and run
`/usr/local/sbin/tippr-firstboot forum.example.com` again.

Read the release's CHANGELOG entry before upgrading: anything that needs
doing by hand is noted there.

### Updating from /admin/servers

The same steps can be started from the site: /admin/servers shows the
newest release and which servers run an older one. Choose a release and
**update the servers**. On each server, within a minute, `tippr-update`
(run by `tippr-update.timer`, as root):

1. waits while another server is updating (one at a time);
2. downloads the release's installer tarball and `SHA256SUMS` from GitHub
   and checks the tarball against them;
3. makes a site backup (`tippr-backup export`), if the box was ticked;
4. stops the site, keeps the old code as `/home/tippr/src.old`, unpacks the
   new code and runs `tippr-firstboot <domain>`, as in step 3 above;
5. checks that the site answers. If it doesn't, it puts the old code back
   and runs the installer again (the new code is left in
   `/home/tippr/src.failed`).

Each server's card shows how it's going, with the end of
`/var/log/tippr-update.log`. Take a snapshot first (step 1 above) all the
same: going back to it is quicker than anything the updater can do.

The web app only asks (through ZooKeeper); it can't run anything as root.
The updater is root's own copy (`/usr/local/sbin/tippr-update`, with the
system Python), and the repository it downloads from is in root's
`/etc/tippr/updates.conf` (the installer's `TIPPR_RELEASE_REPO`). To turn
updating from the page off, re-run the installer with
`TIPPR_WEB_UPDATES=0`. Only installs with `tippr-firstboot` can be updated
this way; others say so on their card and are upgraded by hand.

`sudo tippr-update --status` shows the request and this server's state.

## Moving to more containers

A container made from the template holds everything, which suits most
sites. The same template also makes a **backend** container (the
databases, queue, cache, queue processors and jobs) and any number of
**frontend** containers (the pages), with `TIPPR_ROLE` in each one's
`firstboot.env`: [SERVERS.md](SERVERS.md) has the steps. Media has to be
in S3-compatible storage first, e.g. Garage in its own container
([STORAGE.md](STORAGE.md)).

To move an all-in-one site's data to a new backend, export from the old
container with `--offline` and import and restore on the backend
([BACKUP.md](BACKUP.md)).

## Notes

- `pct enter` and `pct exec` start with a short PATH that leaves out
  `/usr/local/bin` and `/usr/local/sbin`, where `tippr-run`,
  `tippr-shell`, `tippr-backup` and `tippr-firstboot` live. Run `su -`
  after `pct enter` to get a normal login shell, or call them by their full
  paths.
- The template is built by `proxmox/build-template.sh`, which runs the
  installer in a container booted with systemd and exports its filesystem.
  `proxmox/test-template.sh` boots the result and checks the first boot.
  Both run in the release workflow.
- Unprivileged containers are fine. If Cassandra or OpenSearch won't
  start, check `vm.max_map_count` on the node first.
