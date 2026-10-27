#!/usr/bin/env python3
"""Merge metadata JSON sidecars back into photo/video files.

Writes the original "photo taken time" (and GPS, if present) from each
`*.supplemental-metadata.json` into the media file's embedded metadata
(EXIF for images, QuickTime tags for videos), and sets the filesystem
modification time to match, so the files carry their original timestamps
wherever they go next.

By default the originals are left untouched: fixed copies are written to a
sibling folder named "<folder>-merged" (or the folder given via --output),
mirroring the source structure. Use --in-place to edit the originals instead.

Skipped and failed files are copied (together with their metadata JSON,
when one exists) into sibling folders named "<folder>-skipped" and
"<folder>-failed" so they can be reviewed or retried separately.

Usage:
    python3 embed_sidecar_metadata.py <folder> [more folders...] [--dry-run]
    python3 embed_sidecar_metadata.py <folder> --output <folder>
    python3 embed_sidecar_metadata.py <folder> --in-place
    python3 embed_sidecar_metadata.py <folder> --info   # per-file log lines

Requires exiftool (brew install exiftool).
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".webp", ".dng"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".3gp", ".avi", ".mpg", ".mpeg"}
OTHER_EXTS = {".gif"}  # no reliable embedded date tag; file mtime only
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS | OTHER_EXTS

JSON_MARKERS = (".supplemental-metadata", ".supplemental-met", ".suppl", ".json")


def find_json_for(media: Path, json_names: dict[str, Path]) -> Path | None:
    """Locate the JSON sidecar for a media file.

    Handles the common sidecar naming quirks: normal sidecars, truncated
    JSON filenames (some exporters cap them at ~51 chars), duplicate-counter sidecars
    (IMG(1).JPG -> IMG.JPG.supplemental-metadata(1).json), and -edited
    variants which share the original's sidecar.
    """
    name = media.name

    # 1. Exact sidecar: IMG_0001.JPG.supplemental-metadata.json
    exact = f"{name}.supplemental-metadata.json".lower()
    if exact in json_names:
        return json_names[exact]

    # 2. -edited variant uses the original's sidecar
    stem, ext = media.stem, media.suffix
    if stem.lower().endswith("-edited"):
        return find_json_for(media.with_name(stem[:-7] + ext), json_names)

    # 3. Duplicate counter: IMG(1).JPG -> IMG.JPG.supplemental-metadata(1).json
    if stem.endswith(")") and "(" in stem:
        base, _, counter = stem.rpartition("(")
        counter = "(" + counter  # e.g. "(1)"
        candidate = f"{base}{ext}.supplemental-metadata{counter}.json".lower()
        if candidate in json_names:
            return json_names[candidate]

    # 4. Truncated JSON filename: match any sidecar that starts with the
    #    media filename (or a truncation of it) and ends with .json
    lower = name.lower()
    for jname, jpath in json_names.items():
        root = jname
        for marker in JSON_MARKERS:
            idx = root.find(marker)
            if idx != -1:
                root = root[:idx]
                break
        if root and (lower.startswith(root) or root.startswith(lower)):
            return jpath
    return None


def exiftool_args(media: Path, ts: int, geo: dict) -> list[str]:
    """Build the per-file exiftool tag assignments."""
    args = []
    ext = media.suffix.lower()

    if ext in IMAGE_EXTS:
        # EXIF stores naive local time; use the local timezone's rendering
        local = datetime.fromtimestamp(ts)
        stamp = local.strftime("%Y:%m:%d %H:%M:%S")
        offset = local.astimezone().strftime("%z")
        offset = offset[:3] + ":" + offset[3:]  # +0800 -> +08:00
        args += [
            f"-EXIF:DateTimeOriginal={stamp}",
            f"-EXIF:CreateDate={stamp}",
            f"-EXIF:ModifyDate={stamp}",
            f"-EXIF:OffsetTimeOriginal={offset}",
            f"-EXIF:OffsetTimeDigitized={offset}",
            f"-EXIF:OffsetTime={offset}",
            # OffsetTime* tags require EXIF 2.31; older files often carry 0220/0221
            "-EXIF:ExifVersion=0232",
        ]
        if ext == ".png":
            args.append(f"-PNG:CreationTime={stamp}{offset}")
    elif ext in VIDEO_EXTS:
        # QuickTime dates are UTC by spec
        stamp = datetime.fromtimestamp(ts, timezone.utc).strftime("%Y:%m:%d %H:%M:%S")
        args += [
            f"-QuickTime:CreateDate={stamp}",
            f"-QuickTime:ModifyDate={stamp}",
            f"-QuickTime:TrackCreateDate={stamp}",
            f"-QuickTime:TrackModifyDate={stamp}",
            f"-QuickTime:MediaCreateDate={stamp}",
            f"-QuickTime:MediaModifyDate={stamp}",
        ]

    lat = geo.get("latitude", 0.0)
    lon = geo.get("longitude", 0.0)
    if lat or lon:
        args += [
            f"-GPSLatitude={abs(lat)}",
            f"-GPSLatitudeRef={'N' if lat >= 0 else 'S'}",
            f"-GPSLongitude={abs(lon)}",
            f"-GPSLongitudeRef={'E' if lon >= 0 else 'W'}",
        ]
        alt = geo.get("altitude", 0.0)
        if alt:
            args += [f"-GPSAltitude={abs(alt)}", f"-GPSAltitudeRef={'0' if alt >= 0 else '1'}"]
        if ext in VIDEO_EXTS:
            args.append(f"-QuickTime:GPSCoordinates={lat}, {lon}")

    # File modified time = taken time (fallback for formats without a date tag)
    file_stamp = datetime.fromtimestamp(ts).astimezone().strftime("%Y:%m:%d %H:%M:%S%z")
    file_stamp = file_stamp[:-2] + ":" + file_stamp[-2:]
    args.append(f"-FileModifyDate={file_stamp}")
    return args


def copy_aside(media: Path, sidecar: Path | None, root: Path, suffix: str) -> None:
    """Copy a media file (and its JSON sidecar, if any) into '<root>-<suffix>'."""
    out_root = root.parent / (root.name + "-" + suffix)
    target = out_root / media.relative_to(root)
    target.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy2(media, target)
    if sidecar is not None:
        shutil.copy2(sidecar, target.parent / sidecar.name)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", nargs="+", type=Path, help="Folder(s) to process (recursive)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without modifying files")
    parser.add_argument(
        "-o", "--output", type=Path, default=None,
        help="Folder to write fixed copies into (default: '<folder>-merged' next to each input folder)",
    )
    parser.add_argument(
        "--in-place", action="store_true",
        help="Edit the original files instead of writing copies",
    )
    parser.add_argument(
        "--info", action="store_true",
        help="Print a log line per file (default: only the final summary)",
    )
    opts = parser.parse_args()
    if opts.output and opts.in_place:
        parser.error("--output and --in-place are mutually exclusive")
    if opts.output and opts.output.exists() and not opts.output.is_dir():
        parser.error(f"--output is not a directory: {opts.output}")

    media_files: list[tuple[Path, Path]] = []  # (file, its input root folder)
    jsons_by_dir: dict[Path, dict[str, Path]] = {}
    for folder in opts.folders:
        if not folder.is_dir():
            parser.error(f"not a directory: {folder}")
        for path in sorted(folder.rglob("*")):
            if path.is_file():
                if path.suffix.lower() in MEDIA_EXTS:
                    media_files.append((path, folder))
                elif path.suffix.lower() == ".json":
                    jsons_by_dir.setdefault(path.parent, {})[path.name.lower()] = path

    done = skipped = failed = 0
    # SKIP/FAIL always print; OK/DRY lines only with --info
    log = print if opts.info else (lambda *a, **k: None)
    for media, root in media_files:
        sidecar = find_json_for(media, jsons_by_dir.get(media.parent, {}))
        if sidecar is None:
            print(f"SKIP  {media.name}: no metadata JSON found")
            if not opts.dry_run:
                copy_aside(media, None, root, "skipped")
            skipped += 1
            continue
        try:
            meta = json.loads(sidecar.read_text(encoding="utf-8"))
            ts = int(meta["photoTakenTime"]["timestamp"])
        except (OSError, ValueError, KeyError) as e:
            print(f"SKIP  {media.name}: cannot read photoTakenTime from {sidecar.name} ({e})")
            if not opts.dry_run:
                copy_aside(media, sidecar, root, "skipped")
            skipped += 1
            continue

        args = exiftool_args(media, ts, meta.get("geoData", {}))
        taken = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        if opts.in_place:
            target = media
        else:
            out_root = opts.output or root.parent / (root.name + "-merged")
            target = out_root / media.relative_to(root)
        if opts.dry_run:
            where = "" if opts.in_place else f" -> {target}"
            log(f"DRY   {media.name}: would set taken time -> {taken}{where}")
            done += 1
            continue

        if not opts.in_place:
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(media, target)

        result = subprocess.run(
            ["exiftool", "-overwrite_original", "-m", "-q", *args, str(target)],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"FAIL  {media.name}: {result.stderr.strip()}")
            copy_aside(media, sidecar, root, "failed")
            # drop the half-processed copy so the merged tree only holds successes
            if not opts.in_place:
                target.unlink(missing_ok=True)
            failed += 1
            continue
        # exiftool resets mtime of files it rewrites; re-apply via os.utime
        os.utime(target, (ts, ts))
        log(f"OK    {media.name}: taken time -> {taken}")
        done += 1

    print(f"\n{done} updated, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
