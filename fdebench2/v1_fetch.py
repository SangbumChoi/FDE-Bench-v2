"""Fetch FDE-Bench v1 as an optional external benchmark into external/fde-bench-v1.

v1 (Baidu AI Cloud, CC BY-NC-ND 4.0) is never committed to this repository. This
module downloads it on demand: the case protocols by a sparse git checkout of
baidubce/FM-Agent at a pinned commit (only FDE-Bench/case and its license and
data manifest; no FM-Agent code is installed or imported), and the business
data from the v1 data release, verified against the manifest's sha256 sums.
"""

from __future__ import annotations

import hashlib
import json
import shutil
import subprocess
import tarfile
import tempfile
import urllib.request
from pathlib import Path

CHUNK = 1 << 20


def _sha256(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        while block := f.read(CHUNK):
            h.update(block)
    return h.hexdigest()


def _download(url: str, dest: Path, sha256: str) -> None:
    if dest.is_file() and _sha256(dest) == sha256:
        return
    tmp = dest.with_suffix(dest.suffix + ".part")
    print(f"downloading {url}")
    with urllib.request.urlopen(url, timeout=120) as resp, tmp.open("wb") as out:
        shutil.copyfileobj(resp, out, CHUNK)
    if _sha256(tmp) != sha256:
        tmp.unlink()
        raise RuntimeError(f"checksum mismatch for {url}")
    tmp.replace(dest)


def _safe_members(tar: tarfile.TarFile):
    for m in tar.getmembers():
        p = Path(m.name)
        if p.is_absolute() or ".." in p.parts or not p.parts or p.parts[0] != "case" or "data" not in p.parts:
            raise RuntimeError(f"unexpected path in archive: {m.name}")
        if not (m.isfile() or m.isdir()):
            raise RuntimeError(f"unexpected member type in archive: {m.name}")
        yield m


V1_REPO = "https://github.com/baidubce/FM-Agent.git"
V1_COMMIT = "f3d8d7ab8e1847243aecf7b2f48cc37d9d81391a"


def fetch_protocols(root: Path) -> None:
    """Sparse-checkout FDE-Bench/case (+ LICENSE-DATA, data manifest) at the pinned commit into `root`."""
    if (root / "data-manifest.json").is_file():
        return
    with tempfile.TemporaryDirectory() as tmp:
        repo = Path(tmp) / "fm"
        git = ["git", "-C", str(repo)]
        subprocess.run(["git", "clone", "--quiet", "--filter=blob:none", "--no-checkout", "--sparse", V1_REPO,
                        str(repo)], check=True)
        subprocess.run([*git, "sparse-checkout", "set", "--no-cone", "/FDE-Bench/case/",
                        "/FDE-Bench/LICENSE-DATA", "/FDE-Bench/data-manifest.json"], check=True)
        subprocess.run([*git, "checkout", "--quiet", V1_COMMIT], check=True)
        root.mkdir(parents=True, exist_ok=True)
        for name in ("case", "LICENSE-DATA", "data-manifest.json"):
            src = repo / "FDE-Bench" / name
            (shutil.copytree if src.is_dir() else shutil.copy2)(src, root / name)


def fetch(root: Path, cache: Path, cases: set[str] | None = None) -> None:
    """Fetch protocols, then download and extract the data archives for `cases` (all if None)."""
    fetch_protocols(root)
    cases_dir = root / "case"
    manifest = json.loads((root / "data-manifest.json").read_text(encoding="utf-8"))
    base = f"https://github.com/{manifest['repository']}/releases/download/{manifest['release_tag']}"
    cache.mkdir(parents=True, exist_ok=True)
    wanted = {a["name"] for a in manifest["assets"]} if cases is None else {
        f["asset"] for f in manifest["files"] if f["path"].split("/")[1] in cases}
    for asset in manifest["assets"]:
        if asset["name"] not in wanted:
            continue
        archive = cache / asset["name"]
        if not (archive.is_file() and _sha256(archive) == asset["sha256"]):
            parts = asset.get("parts") or [{"name": asset["name"], "sha256": asset["sha256"]}]
            for part in parts:
                _download(f"{base}/{part['name']}", cache / part["name"], part["sha256"])
            if len(parts) > 1:
                with archive.open("wb") as out:
                    for part in parts:
                        with (cache / part["name"]).open("rb") as src:
                            shutil.copyfileobj(src, out, CHUNK)
                if _sha256(archive) != asset["sha256"]:
                    raise RuntimeError(f"reassembled {asset['name']} fails its checksum")
        print(f"extracting {asset['name']}")
        staging = cache / "staging"
        shutil.rmtree(staging, ignore_errors=True)
        with tarfile.open(archive) as tar:
            tar.extractall(staging, members=_safe_members(tar), filter="data")
        for src in (staging / "case").rglob("*"):
            if src.is_file():
                rel = src.relative_to(staging / "case")
                if cases is not None and rel.parts[0] not in cases:
                    continue
                dest = cases_dir / rel
                dest.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(src), dest)
        shutil.rmtree(staging, ignore_errors=True)


def check(root: Path, cases: set[str] | None = None) -> list[str]:
    """Return the manifest files that are missing or fail their checksum."""
    cases_dir = root / "case"
    manifest = json.loads((root / "data-manifest.json").read_text(encoding="utf-8"))
    bad = []
    for f in manifest["files"]:
        case_id = f["path"].split("/")[1]
        if cases is not None and case_id not in cases:
            continue
        p = cases_dir / Path(f["path"]).relative_to("case")
        if not p.is_file() or p.stat().st_size != f["bytes"] or _sha256(p) != f["sha256"]:
            bad.append(f["path"])
    return bad
