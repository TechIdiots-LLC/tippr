# Releases

A release is built by `.github/workflows/release.yml` and consists of:

| | |
|---|---|
| Docker image | on Docker Hub as `IMAGE:VERSION`; `IMAGE:MAJOR.MINOR` and `IMAGE:latest` also point to it (pre-releases like `1.2.0-rc1` get only their own tag) |
| `tippr-VERSION-compose.tar.gz` | `docker-compose.yml`, `Caddyfile`, `.env.example` (set to this image and version) and a README; see [docker/README.md](../docker/README.md) |
| `tippr-VERSION-installer.tar.gz` | tippr, i18n, websockets and activity at this release's versions, with static files, translations and Cython modules built; unpack into `/home/tippr/src` and run `tippr/install-tippr.sh`, which then doesn't need to clone anything |
| `SHA256SUMS` | checksums of the two archives |

Before anything is published, the workflow builds the image and starts the
whole compose stack from it. `docker/smoke-test.sh` then checks:

- that setup completes and the main pages answer over HTTPS;
- that media is served;
- that the admin can log in and post, and the post reaches its listing
  and search (the queue consumers and indexer work);
- that GeoIP lookups work;
- that no background container logs an error.

## Making a release

1. **Push your commits, and any in the companion repositories.** The image
   clones `tippr-i18n`, `tippr-service-websockets` and
   `tippr-service-activity` from GitHub, at the branches set in the
   workflow's `env` (`master`). Change those to tags to pin them.
2. **Tag and push:**

   ```bash
   git tag v1.0.0
   git push origin v1.0.0
   ```

3. Watch the run under **Actions → Release**. When it passes, the GitHub
   release appears with the files attached and generated release notes.

To test without publishing, choose **Actions → Release → Run workflow**.
Leave **publish** unticked: it builds and smoke-tests, and keeps the
bundles as a workflow artifact.

## Setup (once)

In the repository's **Settings → Secrets and variables → Actions**:

- secret `DOCKERHUB_USERNAME`: the Docker Hub account;
- secret `DOCKERHUB_TOKEN`: a Docker Hub access token with read and write
  access;
- variable `DOCKERHUB_IMAGE` (optional): the repository to push to.
  Default: `DOCKERHUB_USERNAME/tippr`. Set it if the image belongs to a
  Docker Hub organisation (e.g. `techidiots/tippr`); the compose files'
  default `TIPPR_IMAGE` should match it.

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
