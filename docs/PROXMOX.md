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

## Behind HAProxy on pfSense (or another proxy)

If HAProxy on pfSense (or another proxy) handles TLS for the domain, put
its address on this network in `firstboot.env` before the first start:

```bash
TIPPR_EXTERNAL_PROXY=192.168.1.1
```

The container then serves plain HTTP on port 80 with no certificate of its
own, and takes visitors' addresses from the proxy's `X-Forwarded-For`. On
pfSense:

- the frontend has the certificate (the ACME package can get it), and
  redirects port 80 to HTTPS;
- the backend is the container's address, port 80, with *forwardfor* on;
- set the backend's tunnel timeout to an hour or so, for websockets.

With Cloudflare in front of pfSense, add `TIPPR_BEHIND_CLOUDFLARE=1` too.
For a container already set up, add the setting to `firstboot.env` and run
`tippr-firstboot DOMAIN` again. See [INSTALL_tippr.md](INSTALL_tippr.md#behind-another-proxy).

## Changing the domain later

Run the first-boot script again with the new domain. Your data and
passwords are kept:

```bash
pct exec 210 -- tippr-firstboot new.example.com
```

## Moving to more containers

A container made from the template holds everything, which suits most
sites. To spread a site over several containers later:

- **App containers** (web, consumers and jobs) are interchangeable. Run
  several behind a load balancer (HAProxy, or an nginx container) to
  share the load, with `TIPPR_EXTERNAL_PROXY` set to its address.
  Scheduled jobs take a ZooKeeper lock first (`scripts/run-locked`), so
  each still runs on one container at a time.
- **The data stores** scale their own way: PostgreSQL with replicas,
  Cassandra and OpenSearch by adding nodes to their clusters.
  memcached, RabbitMQ and ZooKeeper are small and can share one container.

[ARCHITECTURE.md](ARCHITECTURE.md) has the full table of roles. To move
the data, export from the all-in-one container with `--offline` and import
and restore on the new app container ([BACKUP.md](BACKUP.md)). Restore
writes to wherever the new container's ini points.

## Notes

- The template is built by `proxmox/build-template.sh`, which runs the
  installer in a container booted with systemd and exports its filesystem.
  `proxmox/test-template.sh` boots the result and checks the first boot.
  Both run in the release workflow.
- Unprivileged containers are fine. If Cassandra or OpenSearch won't
  start, check `vm.max_map_count` on the node first.
