#!/usr/bin/env python3
"""
Generate a CycloneDX SBOM from a public Docker image and upload it to Codacy.

Requirements: docker, syft (https://github.com/anchore/syft)
No third-party Python packages required.
"""

import json
import os
import shutil
import subprocess
import sys
import tempfile
import urllib.error
import urllib.parse
import urllib.request
from getpass import getpass
from pathlib import Path

CONFIG_FILE = Path.home() / ".config" / "sbom-codacy" / "config.json"

# ── ANSI colours ────────────────────────────────────────────────────────────
_NO_COLOUR = not sys.stdout.isatty()

def _c(code: str, text: str) -> str:
    return text if _NO_COLOUR else f"{code}{text}\033[0m"

def bold(t):   return _c("\033[1m", t)
def green(t):  return _c("\033[92m", t)
def yellow(t): return _c("\033[93m", t)
def red(t):    return _c("\033[91m", t)
def cyan(t):   return _c("\033[96m", t)

def step(msg: str):  print(f"\n{bold(cyan('==>'))}{bold(f' {msg}')}")
def ok(msg: str):    print(f"  {green('✔')} {msg}")
def warn(msg: str):  print(f"  {yellow('⚠')}  {msg}")
def err(msg: str):   print(f"  {red('✖')} {msg}", file=sys.stderr)

# ── Config persistence ───────────────────────────────────────────────────────

def load_config() -> dict:
    if CONFIG_FILE.exists():
        try:
            return json.loads(CONFIG_FILE.read_text())
        except (json.JSONDecodeError, OSError):
            pass
    return {}


def save_config(cfg: dict):
    CONFIG_FILE.parent.mkdir(parents=True, exist_ok=True)
    CONFIG_FILE.write_text(json.dumps(cfg, indent=2))
    CONFIG_FILE.chmod(0o600)   # token is stored here — keep it private
    ok(f"Config saved to {CONFIG_FILE}")

# ── Prompts ──────────────────────────────────────────────────────────────────

def ask(label: str, default: str = "") -> str:
    hint = f" [{default}]" if default else ""
    try:
        value = input(f"  {label}{hint}: ").strip()
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(0)
    return value or default


def ask_secret(label: str, has_saved: bool) -> str:
    hint = " [saved — press Enter to keep]" if has_saved else ""
    try:
        value = getpass(f"  {label}{hint}: ")
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(0)
    return value


def ask_choice(label: str, choices: list, default: str) -> str:
    display = "/".join(bold(c) if c == default else c for c in choices)
    while True:
        raw = ask(f"{label} ({display})", default)
        if raw in choices:
            return raw
        warn(f"Please enter one of: {', '.join(choices)}")


def ask_yes_no(label: str, default: bool = True) -> bool:
    hint = "Y/n" if default else "y/N"
    try:
        raw = input(f"  {label} [{hint}]: ").strip().lower()
    except (KeyboardInterrupt, EOFError):
        print()
        sys.exit(0)
    if raw == "":
        return default
    return raw == "y"

# ── Prerequisites ────────────────────────────────────────────────────────────

def check_docker():
    if not shutil.which("docker"):
        err("docker is not installed or not in PATH.")
        err("Install Docker Desktop: https://www.docker.com/products/docker-desktop")
        sys.exit(1)
    # Make sure the daemon is running
    result = subprocess.run(
        ["docker", "info"],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    if result.returncode != 0:
        err("Docker daemon is not running. Please start Docker and try again.")
        sys.exit(1)
    ok("docker")


def ensure_syft():
    if shutil.which("syft"):
        ok("syft")
        return
    warn("syft not found.")
    if not ask_yes_no("Install syft now via the official script?"):
        err("syft is required. Install it from https://github.com/anchore/syft#installation")
        sys.exit(1)
    print()
    # The installer writes to /usr/local/bin by default; may need sudo
    result = subprocess.run(
        "curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sh -s -- -b /usr/local/bin",
        shell=True,
    )
    if result.returncode != 0 or not shutil.which("syft"):
        warn("Install without sudo failed. Retrying with sudo...")
        result = subprocess.run(
            "curl -sSfL https://raw.githubusercontent.com/anchore/syft/main/install.sh | sudo sh -s -- -b /usr/local/bin",
            shell=True,
        )
        if result.returncode != 0:
            err("Could not install syft. Install it manually: https://github.com/anchore/syft#installation")
            sys.exit(1)
    ok("syft installed")

# ── Core steps ───────────────────────────────────────────────────────────────

def pull_image(image: str):
    step(f"Pulling image  {bold(image)}")
    result = subprocess.run(["docker", "pull", image])
    if result.returncode != 0:
        err(f"docker pull failed for: {image}")
        sys.exit(1)
    ok("Image ready.")


def generate_sbom(image: str, sbom_path: str):
    step("Generating SBOM with Syft")
    result = subprocess.run([
        "syft", image,
        "--output", f"cyclonedx-json={sbom_path}",
        "--scope", "all-layers",
    ])
    if result.returncode != 0:
        err("Syft failed to generate the SBOM.")
        sys.exit(1)
    size_kb = Path(sbom_path).stat().st_size / 1024
    ok(f"SBOM written ({size_kb:.1f} KB, CycloneDX JSON)")


def parse_image_input(image: str) -> tuple[str, str]:
    """Split a user-supplied image string into (base_name, tag)."""
    image = image.split("@")[0]
    for prefix in ("docker.io/library/", "docker.io/", "index.docker.io/library/", "index.docker.io/"):
        if image.startswith(prefix):
            image = image[len(prefix):]
            break
    if ":" in image.split("/")[-1]:
        return image.rsplit(":", 1)
    return image, "latest"


def patch_sbom_name(sbom_path: str, base_name: str, tag: str) -> bytes:
    """Return SBOM bytes with metadata.component.name set to 'base_name:tag'.

    Codacy reads the tag it will store from metadata.component.name:
    - strips the base name (before ':') for the imageName comparison
    - uses the suffix after ':' as the tag

    Syft writes only the bare image name (no tag), so without this patch
    every upload would be stored as 'imageName:latest'.
    """
    with open(sbom_path) as f:
        doc = json.load(f)
    doc["metadata"]["component"]["name"] = f"{base_name}:{tag}"
    return json.dumps(doc, separators=(",", ":")).encode()


def _form_field(boundary: str, name: str, value: str) -> bytes:
    return (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="{name}"\r\n'
        f"\r\n"
        f"{value}\r\n"
    ).encode()


def upload_to_codacy(sbom_path: str, image_name: str, image_tag: str, cfg: dict):
    step("Uploading SBOM to Codacy")

    provider = cfg["codacy_provider"]
    org = urllib.parse.quote(cfg["codacy_org"], safe="")
    url = f"https://app.codacy.com/api/v3/organizations/{provider}/{org}/image-sboms"

    print(f"  URL:        {url}")
    print(f"  imageName:  {image_name}")
    print(f"  tag:        {image_tag}")
    if cfg.get("codacy_repo"):
        print(f"  repository: {cfg['codacy_repo']}")

    boundary  = "SBOMUploadBoundary7a2f9e"
    # Patch metadata.component.name to 'image_name:image_tag' so Codacy stores
    # the SBOM under the correct specific tag rather than defaulting to 'latest'.
    sbom_bytes = patch_sbom_name(sbom_path, image_name, image_tag)

    # Build multipart body: required text fields + file field
    body = _form_field(boundary, "imageName", image_name)
    body += _form_field(boundary, "tag", image_tag)
    if cfg.get("codacy_repo"):
        body += _form_field(boundary, "repositoryName", cfg["codacy_repo"])
    body += (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="sbom"; filename="sbom.json"\r\n'
        f"Content-Type: application/json\r\n\r\n"
    ).encode() + sbom_bytes + f"\r\n--{boundary}--\r\n".encode()

    req = urllib.request.Request(
        url,
        data=body,
        headers={
            "api-token": cfg["codacy_token"],
            "Content-Type": f"multipart/form-data; boundary={boundary}",
        },
        method="POST",
    )

    try:
        with urllib.request.urlopen(req) as resp:
            ok(f"Uploaded successfully (HTTP {resp.status})")
    except urllib.error.HTTPError as exc:
        body_text = exc.read().decode(errors="replace")
        err(f"Codacy API returned HTTP {exc.code}")
        if body_text.strip():
            err(f"Response body: {body_text[:600]}")
        if exc.code == 401:
            err("→ Token is missing or invalid. Generate a new one under:")
            err("  Account → Access management → API tokens")
        elif exc.code == 404:
            err("→ Organization not found. Check provider and org name (case-sensitive).")
            err(f"  Expected: https://app.codacy.com/{cfg['codacy_provider']}/{cfg['codacy_org']}")
        elif exc.code == 400:
            err("→ Bad request — imageName or tag may be malformed.")
        elif exc.code == 409:
            err("→ Conflict — an SBOM for this image/tag already exists.")
        sys.exit(1)
    except urllib.error.URLError as exc:
        err(f"Network error: {exc.reason}")
        sys.exit(1)

# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    print(f"\n{bold('SBOM Generator → Codacy')}")
    print("Pulls a public Docker image, generates a CycloneDX SBOM with Syft,")
    print("and uploads it to your Codacy repository.\n")

    # ── Prerequisites
    step("Checking prerequisites")
    check_docker()
    ensure_syft()

    # ── Image
    print(f"\n{bold('Which image would you like to scan?')}")
    image = ask("Docker image (e.g. nginx:latest, python:3.12-slim)")
    if not image:
        err("No image provided.")
        sys.exit(1)

    # ── Codacy credentials
    saved = load_config()
    has_saved = bool(saved)

    print(f"\n{bold('Codacy connection')}")
    if has_saved:
        print("  Saved values shown in brackets — press Enter to keep them.\n")
    else:
        print("  Find your API token under: Account → Access management → API tokens\n")

    new_token = ask_secret("Codacy API token", has_saved=bool(saved.get("codacy_token")))
    codacy_token = new_token or saved.get("codacy_token", "")

    codacy_provider = ask_choice(
        "Git provider",
        choices=["gh", "gl", "bb"],
        default=saved.get("codacy_provider", "gh"),
    )
    codacy_org  = ask("Codacy organization / username", saved.get("codacy_org", ""))
    codacy_repo = ask("Codacy repository name (optional — links SBOM to a repo)", saved.get("codacy_repo", ""))

    missing = [k for k, v in [
        ("API token", codacy_token),
        ("organization", codacy_org),
    ] if not v]
    if missing:
        err(f"Missing required values: {', '.join(missing)}")
        sys.exit(1)

    cfg = {
        "codacy_token":    codacy_token,
        "codacy_provider": codacy_provider,
        "codacy_org":      codacy_org,
        "codacy_repo":     codacy_repo,
    }

    # ── Optionally persist config
    print()
    if ask_yes_no("Save these Codacy settings for next time?"):
        save_config(cfg)

    # ── Main pipeline
    image_name, image_tag = parse_image_input(image)
    pull_image(image)

    with tempfile.TemporaryDirectory() as tmpdir:
        sbom_path = os.path.join(tmpdir, "sbom.json")
        generate_sbom(image, sbom_path)

        safe_tag  = image_tag.replace("/", "-").replace(":", "-")
        local_sbom = Path(f"sbom-{image_name.split('/')[-1]}-{safe_tag}.json")
        import shutil as _shutil
        _shutil.copy(sbom_path, local_sbom)
        ok(f"SBOM saved locally → {local_sbom}")

        upload_to_codacy(sbom_path, image_name, image_tag, cfg)

    print(f"\n{bold(green('Done.'))}\n")


if __name__ == "__main__":
    main()
