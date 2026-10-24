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
- that ordinary members can use the site in a browser (the browser test,
  below);
- that no background container logs an error.

The browser test (`docker/visual-test.mjs`, with accounts from
`docker/visual-seed.py`) drives Chrome as four ordinary members, not
admins: one posts through the submit form, the others reply to each other
four levels down a thread, and they all vote on the post and the comments,
changing and undoing votes. The arrows must show each person's vote at once
and after reloading, and the scores must follow once the vote queues have
counted them. Every page they see is checked for JavaScript errors, failed
requests, sideways scrolling at phone width and text that can't be read on
its background, and saved as a screenshot at desktop and phone width, in
the light and the night theme. The screenshots are kept with the run (the
`screenshots-VERSION` artifact) to look through before publishing;
`report.json` there lists what failed, and faint text as warnings. To run it
against a local stack: `VISUAL_TEST=1 PLAYWRIGHT=<playwright-core dir>
bash docker/smoke-test.sh`.

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

## On GitLab

`.gitlab-ci.yml` does the same on a GitLab server (GitLab ignores
`.github/`), for a repository kept on GitLab and mirrored to GitHub, where
the workflows above keep running:

- **CI:** merge requests and pushes to `master` run the unit tests and the
  installer smoke test, each in an Ubuntu 24.04 container with systemd
  (`.gitlab/scripts/systemd-box.sh`).
- **Release:** a push to `master` whose `VERSION` has no GitLab release
  builds and tests the same files as above. It creates the release, with
  the files in the project's generic package registry and the image in its
  container registry. **Build → Pipelines → New pipeline** with
  `RELEASE_DRY_RUN` set to `true` builds and tests without publishing.
- **Bump:** **Build → Pipelines → New pipeline** with `BUMP_VERSION` set
  opens the merge request that "Create bump version PR" would.

It needs:

- a Linux runner tagged `linux` and `docker`, registered with
  `--privileged` (for Docker-in-Docker and the systemd containers), with
  the disk for a Proxmox template build (~20 GB);
- a Windows runner tagged `windows` for the small jobs (the release check,
  publishing and the bump), which need PowerShell and, for the bump, Python
  and git;
- a runner maximum job timeout of at least 5 hours, for the release build;
- a generic package size limit that fits the Proxmox template
  (**Admin → Settings → CI/CD**);
- the protected variable `CI_PUSH_TOKEN` (a project access token with the
  Maintainer role and the `api` and `write_repository` scopes) for the
  bump, in the environment scope `release/master`.

Docker Hub is optional there. The GitLab pipeline pushes to Docker Hub only
when `DOCKERHUB_USERNAME` and `DOCKERHUB_TOKEN` are set. Leave them unset
while the GitHub mirror's **Release** still pushes the image, or both will.

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

The Python packages are pinned in `install/requirements.txt` and installed
exactly as listed (`--no-deps`), by the image and by the installer alike, so
every install of a release runs the versions it was tested with. To update
them, upgrade a working install and freeze it again, as the file's header
explains. Then check the image with `docker/smoke-test.sh`.
