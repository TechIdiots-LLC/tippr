# Media storage

tippr stores uploaded media (thumbnails, vault images and stylesheets, the
site logo, favicon and share image, ad images) in one of two places:

- **On the server** (the default): `/srv/www/media`, served by nginx at
  `https://<your site>/media/`. Nothing to set up; right for a site on one
  server.
- **In an S3-compatible bucket**: Garage, SeaweedFS, MinIO, Ceph, Amazon S3,
  Backblaze B2, Cloudflare R2, Wasabi … Media is still served at
  `https://<your site>/media/` (nginx fetches it from the bucket), so links
  don't change. Use this once you run more than one frontend server (they
  all need the same files), when media outgrows the server's disk, or before
  photo and video posts.

Nothing changes unless you choose the bucket: an install or upgrade without
the settings below keeps media on the server exactly as before.

## Setting up Garage on Proxmox

[Garage](https://garagehq.deuxfleurs.fr/) is a small S3-compatible server
made for self-hosting. One node is enough to start; you can add nodes in
other places later for redundancy.

1. **A container for it.** Create a Debian 12 LXC (1–2 cores, 1 GB RAM) on
   the storage network. Give it a ZFS dataset for the data, mounted at
   `/var/lib/garage` (for example `mp0`). Large files suit a big record size:

       zfs create -o recordsize=1M -o compression=lz4 tank/garage

2. **Install Garage** (a single static binary; pick the current release from
   [its download page](https://garagehq.deuxfleurs.fr/download/)):

       curl -Lo /usr/local/bin/garage \
         https://garagehq.deuxfleurs.fr/_releases/v2.1.0/x86_64-unknown-linux-musl/garage
       chmod +x /usr/local/bin/garage
       mkdir -p /var/lib/garage/meta /var/lib/garage/data

3. **Configure it**, in `/etc/garage.toml`:

       metadata_dir = "/var/lib/garage/meta"
       data_dir = "/var/lib/garage/data"
       db_engine = "sqlite"
       replication_factor = 1
       rpc_bind_addr = "[::]:3901"
       rpc_public_addr = "<this container's IP>:3901"
       rpc_secret = "<output of: openssl rand -hex 32>"

       [s3_api]
       s3_region = "garage"
       api_bind_addr = "[::]:3900"
       root_domain = ".s3.garage"

       [s3_web]
       bind_addr = "[::]:3902"
       root_domain = ".web.garage"
       index = "index.html"

   And a service, `/etc/systemd/system/garage.service`:

       [Unit]
       Description=Garage object storage
       After=network-online.target
       Wants=network-online.target

       [Service]
       ExecStart=/usr/local/bin/garage -c /etc/garage.toml server
       Restart=always
       StateDirectory=garage

       [Install]
       WantedBy=multi-user.target

   Then `systemctl daemon-reload && systemctl enable --now garage`.

4. **Give it its storage and make the bucket**:

       garage status                                  # note the node ID
       garage layout assign -z dc1 -c 10T <node ID>   # the space to use
       garage layout apply --version 1
       garage key create tippr                        # note the Key ID and Secret key
       garage bucket create tippr-media
       garage bucket allow --read --write --owner tippr-media --key tippr
       garage bucket website --allow tippr-media      # lets nginx read it without a key

   Garage doesn't serve files anonymously through its S3 API (port 3900);
   public files come from its website endpoint (port 3902), which picks the
   bucket from the Host header: `tippr-media.web.garage` with the
   `root_domain` above.

5. **Firewall**: only tippr's servers need to reach ports 3900 and 3902.
   Browsers never talk to Garage directly: uploads go through
   `https://<your site>/s3/` and downloads through `/media/`.

## Pointing tippr at it

Give the installer the bucket's settings (they're remembered in
`/etc/tippr/secrets.env`, like the passwords, for later runs):

| setting | for Garage |
|---|---|
| `TIPPR_S3_ENDPOINT` | `http://<garage IP>:3900` |
| `TIPPR_S3_REGION` | `garage` |
| `TIPPR_S3_KEY_ID`, `TIPPR_S3_SECRET` | the key from `garage key create` |
| `TIPPR_S3_MEDIA_BUCKET` | `tippr-media` |
| `TIPPR_MEDIA_ORIGIN` | `http://<garage IP>:3902/` (where nginx reads files) |
| `TIPPR_MEDIA_ORIGIN_HOST` | `tippr-media.web.garage` |
| `TIPPR_MEDIA_STORAGE` | `s3` (step 3 below) |

Also: `TIPPR_S3_UPLOADS_BUCKET` (for ad images; default: the media bucket)
and `TIPPR_S3_USE_ACLS` (`true` for Amazon S3, which is the default when no
endpoint is given). See `install/install.cfg`.

### Moving existing media

Do it in this order, so the site keeps working throughout:

1. **Connect, but keep media on the server.** Re-run the installer with the
   connection settings and *without* `TIPPR_MEDIA_STORAGE`:

       sudo TIPPR_S3_ENDPOINT=http://172.16.1.60:3900 TIPPR_S3_REGION=garage \
            TIPPR_S3_KEY_ID=GK... TIPPR_S3_SECRET=... \
            TIPPR_S3_MEDIA_BUCKET=tippr-media \
            TIPPR_MEDIA_ORIGIN=http://172.16.1.60:3902/ \
            TIPPR_MEDIA_ORIGIN_HOST=tippr-media.web.garage \
            ./install-tippr.sh

2. **Copy the files.** A dry run first (it checks the bucket can be written,
   and counts), then the copy:

       sudo env MEDIA_BUCKET=tippr-media tippr-run /home/tippr/src/tippr/scripts/migrate_media_to_s3.py
       sudo env MEDIA_BUCKET=tippr-media TIPPR_ALLOW_MUTATE=1 tippr-run /home/tippr/src/tippr/scripts/migrate_media_to_s3.py

3. **Switch.** Re-run the installer with `TIPPR_MEDIA_STORAGE=s3` (the other
   settings are remembered):

       sudo TIPPR_MEDIA_STORAGE=s3 ./install-tippr.sh

   nginx now serves `/media/` from the bucket, and new uploads go there.

4. **Copy again**, for anything uploaded between steps 2 and 3 (files
   already copied are skipped):

       sudo env MEDIA_BUCKET=tippr-media TIPPR_ALLOW_MUTATE=1 tippr-run /home/tippr/src/tippr/scripts/migrate_media_to_s3.py

5. **Check it.** This saves a test file the way uploads are saved, checks
   it's in the bucket and not on the disk, fetches it from `/media/`
   through nginx, then deletes it:

       sudo tippr-run /home/tippr/src/tippr/scripts/check_media_storage.py

Check a few images on the site, then `/srv/www/media` can be archived.

### Going back

Re-run the installer with `TIPPR_MEDIA_STORAGE=filesystem`, after copying
the bucket's files back into `/srv/www/media` (with
[rclone](https://rclone.org/) or `aws s3 sync`): the addresses are the same
either way.

## Other services

- **Amazon S3**: leave `TIPPR_S3_ENDPOINT` blank; give the key and bucket,
  and set `TIPPR_MEDIA_ORIGIN` to `https://<bucket>.s3.amazonaws.com/`. Objects
  are uploaded public-read.
- **MinIO, SeaweedFS, Ceph RGW**: give the endpoint; make the bucket
  publicly readable (a read-only bucket policy) and leave
  `TIPPR_MEDIA_ORIGIN` blank (it defaults to `<endpoint>/<bucket>/`).
- **Backblaze B2, Cloudflare R2, Wasabi**: their S3 endpoint and region, a
  public bucket, and `TIPPR_MEDIA_ORIGIN` set to the bucket's public address.

A CDN (Cloudflare, for example) in front of the site can cache `/media/`:
nginx sends media with long cache lifetimes, and most files get a new name
when they change (thumbnails, vault images, the site's images). Ad images
keep their name when replaced, so a cached copy can linger after an
advertiser changes theirs.

## Backups

The bucket isn't part of tippr's own backups (`/admin/backups` covers the
databases and settings). Back it up off the storage server: `rclone sync`
to another bucket (Backblaze B2 is inexpensive), or `zfs send` of the
dataset to another machine.
