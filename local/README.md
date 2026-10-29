# Local script

Generates a CycloneDX SBOM from any public Docker image using [Syft](https://github.com/anchore/syft) and uploads it to [Codacy](https://www.codacy.com). It runs interactively on your machine, which makes it useful for testing.

## How it works

```
Docker Hub / public registry
         │
         ▼
   docker pull
         │
         ▼
        Syft  ──CycloneDX JSON──►  Codacy API
```

1. Checks that `docker` is installed and the daemon is running.
2. Checks that `syft` is installed and offers to install it if not.
3. Prompts for the image name and Codacy credentials (optionally saved to `~/.config/sbom-codacy/config.json`).
4. Pulls the image and generates a CycloneDX JSON SBOM across all layers.
5. Saves a copy of the SBOM in the current directory as `sbom-<image>-<tag>.json`.
6. Uploads the SBOM to Codacy.

### Tags

The image and tag are taken from the image string you enter: `python:3.12-slim` is image `python` with tag `3.12-slim`, and an image with no tag uses `latest`. The script sends the tag to Codacy as the `tag` field and names the SBOM `image:tag` (`syft --source-name`). Codacy requires these to match.

## Prerequisites

- **Docker Desktop** running locally — [install](https://www.docker.com/products/docker-desktop)
- **Python 3.9+** — no third-party packages needed (stdlib only)
- **syft** — the script offers to install it on first run
- A **Codacy API token** — generate one under **Your account > Access management > API tokens**
- The target repository must already be **added to your Codacy organization**

## Usage

```bash
python3 sbom_to_codacy.py
```

You will be prompted for:

| Prompt | Example |
|---|---|
| Docker image | `nginx:latest`, `python:3.12-slim`, `alpine:3.19` |
| Codacy API token | _(hidden input)_ |
| Git provider | `gh` (GitHub) / `gl` (GitLab) / `bb` (Bitbucket) |
| Codacy organization | `my-org` |
| Codacy repository | `my-service` |

If you choose to save your Codacy settings, they are written to `~/.config/sbom-codacy/config.json` (mode `0600`) and only the image is prompted for on later runs.

## Troubleshooting

**`docker pull` fails**
Confirm the image name is correct and publicly accessible. Try `docker pull <image>` in your terminal first.

**syft install fails**
Install it manually — [syft installation docs](https://github.com/anchore/syft#installation). Then re-run the script.

**HTTP 401 from Codacy**
The API token is wrong or expired. Generate a new one in Codacy and delete `~/.config/sbom-codacy/config.json` to reset saved credentials.

**HTTP 404 from Codacy**
The provider, organization, or repository name doesn't match what Codacy has on record. Check the URL `https://app.codacy.com/{provider}/{org}/{repo}` in your browser.

**HTTP 400 `SBOM tag mismatch` from Codacy**
The tag sent to Codacy doesn't match the tag in the SBOM's `metadata.component.name`. The script sets both from the same image string, so this usually means the SBOM was generated outside the script.

**HTTP 409 from Codacy**
An SBOM for this image and tag already exists.

**HTTP 422 from Codacy**
The SBOM payload was rejected. This can happen if the image has no detectable packages (e.g., a bare `scratch` image).
