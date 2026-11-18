from __future__ import annotations

import argparse
import hashlib
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CONFIG = json.loads((ROOT / "model_config.json").read_text(encoding="utf-8"))
MODEL_DIR = ROOT / "models"
CHUNK_SIZE = 1024 * 1024


def digest_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(CHUNK_SIZE), b""):
            digest.update(chunk)
    return digest.hexdigest()


def download_asset(filename: str, metadata: dict, force: bool = False) -> None:
    target = MODEL_DIR / filename
    MODEL_DIR.mkdir(parents=True, exist_ok=True)
    if target.exists() and not force:
        if target.stat().st_size == metadata["size_bytes"] and digest_file(target) == metadata["sha256"]:
            print(f"[OK] {filename} sudah tersedia dan checksum valid.")
            return
        raise RuntimeError(f"{filename} sudah ada tetapi checksum tidak valid. Hapus atau gunakan --force.")

    temp = target.with_suffix(target.suffix + ".download")
    request = urllib.request.Request(
        metadata["url"],
        headers={"User-Agent": "IDS-Pretrained-Model-Downloader/1.0", "Accept": "application/octet-stream"},
    )
    print(f"Mengunduh {filename}...")
    try:
        with urllib.request.urlopen(request, timeout=120) as response, temp.open("wb") as output:
            while True:
                chunk = response.read(CHUNK_SIZE)
                if not chunk:
                    break
                output.write(chunk)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        if temp.exists():
            temp.unlink()
        raise RuntimeError(f"Gagal mengunduh {filename}: {exc}") from exc

    size = temp.stat().st_size
    sha = digest_file(temp)
    if size != metadata["size_bytes"] or sha != metadata["sha256"]:
        preview = temp.read_bytes()[:120]
        temp.unlink(missing_ok=True)
        if b"git-lfs.github.com/spec/v1" in preview:
            detail = "Server mengembalikan pointer Git LFS, bukan file model sebenarnya."
        else:
            detail = "Ukuran atau SHA-256 tidak cocok dengan metadata Git LFS."
        raise RuntimeError(f"Verifikasi {filename} gagal. {detail} File ditolak.")

    temp.replace(target)
    print(f"[OK] {filename} selesai. SHA-256 valid.")


def main() -> int:
    parser = argparse.ArgumentParser(description="Unduh dan verifikasi model RF pretrained CICIDS2017.")
    parser.add_argument("--force", action="store_true", help="Unduh ulang dan timpa artifact yang ada.")
    args = parser.parse_args()
    try:
        for filename, metadata in CONFIG["artifacts"].items():
            download_asset(filename, metadata, force=args.force)
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    print("Semua artifact tersedia dan lolos verifikasi SHA-256.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
