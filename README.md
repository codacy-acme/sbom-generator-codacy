# SBOM Generator for Docker Images

A tool for generating a Software Bill of Materials (SBOM) from a Docker image using [Syft](https://github.com/anchore/syft) and uploading it to [Codacy](https://www.codacy.com):

| Tool | Use case |
|---|---|
| `sbom_to_codacy.py` | Local script — works with any public Docker image, interactive prompts |
| `.github/workflows/ecr-sbom.yml` | GitHub Actions — pulls from a private AWS ECR registry on a schedule or manually |

---

## Local script (`sbom_to_codacy.py`)

### How it works

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
2. Checks that `syft` is installed — offers to install it automatically if not.
3. Prompts for the image name and Codacy credentials (saved to `~/.config/sbom-codacy/config.json` after first run).
4. Pulls the image, generates a CycloneDX JSON SBOM across all layers, and uploads it to Codacy.

### Prerequisites

- **Docker Desktop** running locally — [install](https://www.docker.com/products/docker-desktop)
- **Python 3.9+** — no third-party packages needed (stdlib only)
- **syft** — the script will offer to install it for you on first run
- A **Codacy API token** — generate one under **Your account > Access management > API tokens**
- The target repository must already be **added to your Codacy organization**

### Usage

```bash
python3 sbom_to_codacy.py
```

On first run you will be prompted for:

| Prompt | Example |
|---|---|
| Docker image | `nginx:latest`, `python:3.12-slim`, `alpine:3.19` |
| Codacy API token | _(hidden input)_ |
| Git provider | `gh` (GitHub) / `gl` (GitLab) / `bb` (Bitbucket) |
| Codacy organization | `my-org` |
| Codacy repository | `my-service` |

Codacy settings are saved to `~/.config/sbom-codacy/config.json` (mode `0600`) after the first run so only the image is prompted on subsequent runs.

### Troubleshooting (local script)

**`docker pull` fails**
Confirm the image name is correct and publicly accessible. Try `docker pull <image>` in your terminal first.

**syft install fails**
Install it manually — [syft installation docs](https://github.com/anchore/syft#installation). Then re-run the script.

**HTTP 401 from Codacy**
The API token is wrong or expired. Generate a new one in Codacy and delete `~/.config/sbom-codacy/config.json` to reset saved credentials.

**HTTP 404 from Codacy**
The provider, organization, or repository name doesn't match what Codacy has on record. Check the URL `https://app.codacy.com/{provider}/{org}/{repo}` in your browser.

**HTTP 422 from Codacy**
The SBOM payload was rejected. This can happen if the image has no detectable packages (e.g., a bare `scratch` image).

