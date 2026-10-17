# Releases

A release is built by `.github/workflows/release.yml` and consists of:

| | |
|---|---|
| Docker image | on Docker Hub as `IMAGE:VERSION`; `IMAGE:MAJOR.MINOR` and `IMAGE:latest` also point to it (pre-releases like `1.2.0-rc1` get only their own tag) |
| `tippr-VERSION-compose.tar.gz` | `docker-compose.yml`, `Caddyfile`, `.env.example` (set to this image and version) and a README; see [docker/README.md](../docker/README.md) |
| `tippr-VERSION-installer.tar.gz` | tippr, i18n, websockets and activity at this release's versions, with static files, translations and Cython modules built; unpack into `/home/tippr/src` and run `tippr/install-tippr.sh`, which then doesn't need to clone anything |
| `tippr-VERSION-proxmox-amd64.tar.zst` | a Proxmox LXC template with the whole site installed, set up for its domain on first boot ([PROXMOX.md](PROXMOX.md)) |
| `SHA256SUMS` | checksums of the files |

Before anything is published, the workflow builds the image and starts the
whole compose stack from it. `docker/smoke-test.sh` then checks:

- that setup completes and the main pages answer over HTTPS;
- that media is served;
- that the admin can log in and post, and the post reaches its listing
  and search (the queue consumers and indexer work);
- that GeoIP lookups work;
- that no background container logs an error.

A second job builds the Proxmox template from the installer tarball
(`proxmox/build-template.sh`). It then boots it the way a new container
starts, with a test domain, and checks that the first boot sets the site
up with new credentials (`proxmox/test-template.sh`). That takes about an
hour.

## Making a release

The version is in `VERSION`, and what changed is in `CHANGELOG.md` under
`## master`. Add a line there with each change worth mentioning.

1. **Push your commits, and any in the companion repositories.** The image
   clones `tippr-i18n`, `tippr-service-websockets` and
   `tippr-service-activity` from GitHub, at the branches set in the
   workflow's `env` (`master`). Change those to tags to pin them.
2. **Actions → Create bump version PR → Run workflow.** Choose the bump
   (patch, minor, major, or a pre-release such as `prerelease` with `rc`).
   It updates `VERSION`, renames `## master` in `CHANGELOG.md` to the new
   version, starts a fresh `## master`, and opens a pull request.
3. **Review and merge the pull request.** The push to `master` starts
   **Release**. It sees that `VERSION` has no GitHub release yet, then
   builds, tests and publishes it, with the changelog section as the
   release notes. Pushes where `VERSION` is already released do nothing.

To test without publishing, choose **Actions → Release → Run workflow**
with **dry run** ticked. It builds and tests everything as
`VERSION-dev.COMMIT` and keeps the files as workflow artifacts.

`tools/bump_version.py` does the bump; you can also run it locally
(`python tools/bump_version.py patch`) and commit the result yourself.

## Setup (once)

1. **Docker Hub:** create the repository `techidiotsllc/tippr` (public), and
   a personal access token with *Read & Write* access (*Account settings →
   Personal access tokens*). Use the token rather than the account
   password: it can be revoked on its own.
2. **GitHub, Settings → Environments → New environment** `release`, with
   the secrets:
   - `DOCKERHUB_USERNAME`: `techidiotsllc`;
   - `DOCKERHUB_TOKEN`: the access token.

   Optionally, limit the environment to the `master` branch, or require a
   reviewer before each release.
3. **GitHub, Settings → Actions → General → Workflow permissions:** tick
   *Allow GitHub Actions to create and approve pull requests*, so "Create
   bump version PR" can open its pull request.

To push to a different Docker Hub repository, set the repository variable
`DOCKERHUB_IMAGE` (e.g. `someone/tippr`), and change `TIPPR_IMAGE` in
`docker/.env.example` to match.

## Building the image yourself

From the repository root:

```bash
docker build -f docker/Dockerfile -t tippr .
```

To use local checkouts of the companion repositories instead of cloning
them, pass them as build contexts:

```bash
docker build -f docker/Dockerfile -t tippr \
    --build-context i18n=../tippr-i18n \
    --build-context websockets=../tippr-service-websockets .
```

On Windows, build from a checkout made with `core.symlinks=true` (or inside
WSL). A Windows checkout turns the repository's symlinked images into text
files, which breaks the sprite build.

The Python packages are pinned in `docker/requirements.txt` and installed
exactly as listed (`--no-deps`). To update them, upgrade a working install
and freeze it again, as the file's header explains. Then check the image
with `docker/smoke-test.sh`.
