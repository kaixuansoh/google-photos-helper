#!/usr/bin/env python3
"""Rename mislabelled JPEG files to .JPG in place.

Some exported files carry the wrong extension (e.g. IMG_0001.HEIC whose
bytes are actually JPEG), which makes exiftool fail with errors like
"Not a valid HEIC". This script sniffs each file's magic bytes and, when
the content is JPEG but the extension says otherwise, renames the file
to .JPG in place. Any JSON sidecar that embeds the old filename (e.g.
IMG_0001.HEIC.supplemental-metadata.json) is renamed to match.

Usage:
    python3 fix_jpeg_extension.py <folder> [more folders...] [--dry-run]
"""

import argparse
import sys
from pathlib import Path

JPEG_MAGIC = b"\xff\xd8\xff"
JPEG_EXTS = {".jpg", ".jpeg"}


def is_jpeg(path: Path) -> bool:
    try:
        with open(path, "rb") as f:
            return f.read(3) == JPEG_MAGIC
    except OSError:
        return False


def unique_path(path: Path) -> Path:
    """Return path, or path with a numeric suffix if it already exists."""
    if not path.exists():
        return path
    for i in range(1, 1000):
        candidate = path.with_name(f"{path.stem}({i}){path.suffix}")
        if not candidate.exists():
            return candidate
    raise RuntimeError(f"could not find a free name for {path}")


def process_folder(folder: Path, dry_run: bool) -> tuple[int, int]:
    renamed = skipped = 0
    for path in sorted(folder.rglob("*")):
        if not path.is_file() or path.suffix.lower() in JPEG_EXTS | {".json"}:
            continue
        if not is_jpeg(path):
            continue

        old_name = path.name
        target = unique_path(path.with_suffix(".JPG"))
        print(f"{'[dry-run] ' if dry_run else ''}{path} -> {target.name}")
        if not dry_run:
            path.rename(target)
        renamed += 1

        # Rename sidecars that embed the old filename, e.g.
        # IMG.HEIC.supplemental-metadata.json -> IMG.JPG.supplemental-metadata.json
        for sidecar in path.parent.glob(f"{old_name}.*json"):
            new_sidecar = unique_path(
                sidecar.with_name(target.name + sidecar.name[len(old_name):])
            )
            print(f"{'[dry-run] ' if dry_run else ''}  {sidecar.name} -> {new_sidecar.name}")
            if not dry_run:
                sidecar.rename(new_sidecar)

    return renamed, skipped


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("folders", nargs="+", type=Path)
    parser.add_argument("--dry-run", action="store_true", help="show renames without doing them")
    args = parser.parse_args()

    total = 0
    for folder in args.folders:
        if not folder.is_dir():
            print(f"error: not a folder: {folder}", file=sys.stderr)
            return 1
        renamed, _ = process_folder(folder, args.dry_run)
        total += renamed

    print(f"\n{'Would rename' if args.dry_run else 'Renamed'} {total} file(s).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
