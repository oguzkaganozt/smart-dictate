#!/usr/bin/env bash
# Download the latest smart-dictate release bundle and run its installer.

set -Eeuo pipefail

REPO="${SMART_DICTATE_REPO:-oguzkaganozt/smart-dictate}"
VERSION="${SMART_DICTATE_VERSION:-latest}"
TMPDIR="$(mktemp -d)"

cleanup() {
  rm -rf "$TMPDIR"
}
trap cleanup EXIT

if ! command -v python3 >/dev/null 2>&1; then
  echo "bootstrap: python3 is required" >&2
  exit 1
fi

echo "Downloading smart-dictate ${VERSION} from ${REPO}..."
python3 - "$REPO" "$VERSION" "$TMPDIR" <<'PY'
import hashlib
import json
import os
import subprocess
import sys
import urllib.request
from pathlib import Path

repo, version, tmp = sys.argv[1:4]
tmpdir = Path(tmp)

headers = {"User-Agent": "smart-dictate-bootstrap"}
token = os.environ.get("GITHUB_TOKEN")
if not token:
    try:
        r = subprocess.run(
            ["gh", "auth", "token"],
            capture_output=True,
            text=True,
            timeout=5.0,
        )
        if r.returncode == 0:
            token = r.stdout.strip()
    except Exception:
        token = None
if token:
    headers["Authorization"] = f"Bearer {token}"

if version == "latest":
    url = f"https://api.github.com/repos/{repo}/releases/latest"
else:
    tag = version if version.startswith("v") else f"v{version}"
    url = f"https://api.github.com/repos/{repo}/releases/tags/{tag}"

req = urllib.request.Request(url, headers=headers)
with urllib.request.urlopen(req, timeout=20) as response:
    release = json.load(response)

tar_asset = None
sums_asset = None
for asset in release.get("assets", []):
    name = asset.get("name", "")
    if name.startswith("smart-dictate-") and name.endswith(".tar.gz"):
        tar_asset = asset
    elif name == "SHA256SUMS":
        sums_asset = asset

if tar_asset is None or sums_asset is None:
    raise SystemExit("release is missing smart-dictate tarball or SHA256SUMS")

def download(asset):
    dest = tmpdir / asset["name"]
    req = urllib.request.Request(asset["browser_download_url"], headers=headers)
    with urllib.request.urlopen(req, timeout=60) as response:
        dest.write_bytes(response.read())
    return dest

tarball = download(tar_asset)
sums = download(sums_asset)

expected = None
for line in sums.read_text(encoding="utf-8").splitlines():
    parts = line.split()
    if len(parts) == 2 and parts[1] == tarball.name:
        expected = parts[0]
        break
if expected is None:
    raise SystemExit(f"SHA256SUMS does not contain {tarball.name}")

actual = hashlib.sha256(tarball.read_bytes()).hexdigest()
if actual != expected:
    raise SystemExit(f"checksum mismatch for {tarball.name}")

tag = release["tag_name"]
(tmpdir / "TAG").write_text(tag, encoding="utf-8")
print(f"Downloaded {tarball.name} ({tag})")
PY

TAG="$(tr -d '\n' < "$TMPDIR/TAG")"
TARBALL="$TMPDIR/smart-dictate-$TAG.tar.gz"
tar -xzf "$TARBALL" -C "$TMPDIR"
exec bash "$TMPDIR/smart-dictate-$TAG/install.sh" "$@"
