# SBOM Generator for Docker Images

Examples for generating a Software Bill of Materials (SBOM) from a Docker image and uploading it to [Codacy](https://www.codacy.com).

The default method uses the **Codacy CLI v2**, which generates the SBOM from your image and uploads it in a single command. The folders below show it in different CI systems and with private registries.

| Folder | Contents |
|---|---|
| [`github-actions/`](github-actions/) | GitHub Actions workflow |
| [`circleci/`](circleci/) | CircleCI config |
| [`bitbucket/`](bitbucket/) | Bitbucket Pipelines config |
| [`jenkins/`](jenkins/) | Jenkinsfile |
| [`registries/`](registries/) | Logging in to Amazon ECR, Azure ACR and authenticated Docker Hub |
| [`local/`](local/) | Interactive Python script (Syft) for running and testing on your own machine |

## Setup

1. Create a Codacy account API token under **Your account > Access management > API tokens**.
2. Store it in your pipeline as a secret named `CODACY_API_TOKEN`.
3. Make sure the pipeline can run Docker and `curl`.

## Install the CLI

Run this once per pipeline run:

```bash
curl -fsSL https://raw.githubusercontent.com/codacy/codacy-cli-v2/main/codacy-cli.sh -o codacy-cli.sh
chmod +x codacy-cli.sh
./codacy-cli.sh init
```

`upload-sbom` reads the Codacy configuration that `init` creates in the working directory. Without it the upload stops with `No configuration file was found, execute init command first.`

## Placeholders

| Placeholder | Description |
|---|---|
| `CODACY_API_TOKEN` | Account API token used to authenticate on Codacy |
| `-p` | Git provider hosting the organization: `gh` (GitHub Cloud), `gl` (GitLab Cloud) or `bb` (Bitbucket Cloud) |
| `ORGANIZATION_NAME` | Name of the organization on the Git provider, for example `codacy` |
| `IMAGE_NAME` | Name of the container image, without a tag, for example `myapp` |
| `IMAGE_VERSION` | The tag your pipeline built, such as `1.4.2`. Only used by the per-release example |
| `REPOSITORY_NAME` | Optional. Repository to associate the image with, so findings link back to it |
| `-e` | Optional. Environment where the image is deployed, such as `production`. It appears in the tag list |

## One list, kept up to date

Point a rolling tag at the image you just built and upload that:

```bash
docker tag "${IMAGE_NAME}:${IMAGE_VERSION}" "${IMAGE_NAME}:prod"

./codacy-cli.sh upload-sbom \
  -a "${CODACY_API_TOKEN}" \
  -p gh \
  -o "${ORGANIZATION_NAME}" \
  -r "${REPOSITORY_NAME}" \
  -e production \
  "${IMAGE_NAME}:prod"
```

The `docker tag` alias stays on the build machine and is never pushed. Without it the CLI resolves `prod` against your registry and scans whatever that tag points at there, rather than the image your pipeline just built.

## A separate list per release

Delete the tags you no longer need, then upload the release tag:

```bash
npm install -g "@codacy/codacy-cloud-cli"

# Keep the 10 most recently uploaded tags, delete the rest
codacy image gh "${ORGANIZATION_NAME}" "${IMAGE_NAME}" \
  --delete --keep-latest 10 --skip-confirmation

./codacy-cli.sh upload-sbom \
  -a "${CODACY_API_TOKEN}" \
  -p gh \
  -o "${ORGANIZATION_NAME}" \
  -r "${REPOSITORY_NAME}" \
  -e production \
  "${IMAGE_NAME}:${IMAGE_VERSION}"
```

Every release adds an image tag, so clean up on every run to stay under your organization limit. Put the cleanup before the upload: at the limit the upload is rejected, so a pipeline that uploads first and cleans up later can't make progress. Add `--dry-run` to see which tags would go without deleting anything.

The Codacy Cloud CLI reads the same `CODACY_API_TOKEN` and needs version 1.12.1 or later.

## If your pipeline already produces an SBOM

If you already generate an SBOM in CycloneDX or SPDX format, upload that file directly with the Codacy Cloud CLI (version 1.12.1 or later, reads `CODACY_API_TOKEN`):

```bash
npm install -g "@codacy/codacy-cloud-cli"
```

To keep one list of findings, upload every release to the same tag:

```bash
codacy image gh "${ORGANIZATION_NAME}" "${IMAGE_NAME}" \
  --tag prod \
  --upload "${SBOM_FILE}" \
  --environment production \
  --repository "${REPOSITORY_NAME}"
```

To keep a separate list per release, clean up first and then upload under the release tag:

```bash
codacy image gh "${ORGANIZATION_NAME}" "${IMAGE_NAME}" \
  --delete --keep-latest 10 --skip-confirmation

codacy image gh "${ORGANIZATION_NAME}" "${IMAGE_NAME}" \
  --tag "${IMAGE_VERSION}" \
  --upload "${SBOM_FILE}" \
  --environment production \
  --repository "${REPOSITORY_NAME}"
```

This path never resolves the image itself, so it needs no `docker tag` alias: it attaches the SBOM file you name to the tag you name.
