#!/usr/bin/env python3
"""Sync filesystem dates to the date-taken already embedded in each file.

Reads the capture timestamp from each media file's own embedded metadata
(EXIF DateTimeOriginal/CreateDate for images, QuickTime CreateDate for
videos) and sets the file's creation and modification dates to match.
The files themselves are not rewritten -- only filesystem timestamps change.

Files without any embedded capture date are skipped and reported.

With --targetDate, the embedded tags themselves are rewritten instead:
every media file gets the given date written to its date-taken tags
(DateTimeOriginal/CreateDate for images, CreateDate/MediaCreateDate for
videos) and its filesystem dates set to match.

Usage:
    python3 sync_file_dates.py <folder> [more folders...] [--dry-run]
    python3 sync_file_dates.py <folder> --info   # per-file log lines
    python3 sync_file_dates.py <folder> --targetDate "2019-07-14 15:30:00"

Requires exiftool (brew install exiftool). Setting the creation date on
macOS additionally needs the Xcode command-line tools' `setfile`, which
exiftool uses under the hood.
"""

import argparse
import json
import os
import subprocess
import sys
from datetime import datetime
from pathlib import Path

IMAGE_EXTS = {".jpg", ".jpeg", ".png", ".heic", ".heif", ".tif", ".tiff", ".webp", ".dng"}
VIDEO_EXTS = {".mp4", ".mov", ".m4v", ".3gp", ".avi", ".mpg", ".mpeg"}
MEDIA_EXTS = IMAGE_EXTS | VIDEO_EXTS

# Tags to try, in priority order (first present wins)
DATE_TAGS = [
    "DateTimeOriginal",   # EXIF: moment the shutter fired
    "CreateDate",         # EXIF digitized time / QuickTime creation time
    "MediaCreateDate",    # QuickTime per-media fallback
]


def read_taken_times(folder: Path) -> dict[Path, int]:
    """Read embedded capture dates for all media under folder in one exiftool pass.

    Returns a map of file path -> epoch seconds. Files with no usable
    date tag are absent from the map.
    """
    result = subprocess.run(
        [
            "exiftool", "-json", "-r", "-q", "-m",
            "-api", "QuickTimeUTC=1",   # QuickTime dates are UTC by spec
            "-d", "%s",                 # render dates as epoch seconds (local tz for naive EXIF)
            *(f"-{tag}" for tag in DATE_TAGS),
            str(folder),
        ],
        capture_output=True, text=True,
    )
    if result.returncode not in (0, 1):  # exiftool exits 1 if some files had errors
        print(f"error: exiftool failed on {folder}: {result.stderr.strip()}", file=sys.stderr)
        return {}

    times: dict[Path, int] = {}
    for entry in json.loads(result.stdout or "[]"):
        path = Path(entry["SourceFile"])
        if path.suffix.lower() not in MEDIA_EXTS:
            continue
        for tag in DATE_TAGS:
            value = entry.get(tag)
            # exiftool renders missing/zero dates as absent or "0000:00:00..."
            if value and str(value).lstrip("-").isdigit() and int(value) > 0:
                times[path] = int(value)
                break
    return times


def parse_target_date(value: str) -> int:
    """Parse --targetDate into epoch seconds (local timezone)."""
    for fmt in ("%Y-%m-%d %H:%M:%S", "%Y-%m-%d"):
        try:
            return int(datetime.strptime(value, fmt).timestamp())
        except ValueError:
            continue
    raise argparse.ArgumentTypeError(
        f"invalid date {value!r}; expected 'YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS'"
    )


def file_date_stamp(ts: int) -> str:
    """Format epoch seconds the way exiftool expects for File* pseudo-tags."""
    stamp = datetime.fromtimestamp(ts).astimezone().strftime("%Y:%m:%d %H:%M:%S%z")
    return stamp[:-2] + ":" + stamp[-2:]  # +0800 -> +08:00


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("folders", nargs="+", type=Path, help="Folder(s) to process (recursive)")
    parser.add_argument("--dry-run", action="store_true", help="Show what would be done without modifying files")
    parser.add_argument(
        "--info", action="store_true",
        help="Print a log line per file (default: only skips, failures, and the final summary)",
    )
    parser.add_argument(
        "--targetDate", dest="target_date", type=parse_target_date, metavar="DATE",
        help="Write this date ('YYYY-MM-DD' or 'YYYY-MM-DD HH:MM:SS') into every file's "
             "embedded date-taken tags and filesystem dates, instead of reading dates from the files",
    )
    opts = parser.parse_args()

    media_files: list[Path] = []
    taken_times: dict[Path, int] = {}
    for folder in opts.folders:
        if not folder.is_dir():
            parser.error(f"not a directory: {folder}")
        if opts.target_date is None:
            taken_times.update(read_taken_times(folder))
        media_files += [
            p for p in sorted(folder.rglob("*"))
            if p.is_file() and p.suffix.lower() in MEDIA_EXTS
        ]

    done = skipped = failed = 0
    # SKIP/FAIL always print; OK/DRY lines only with --info
    log = print if opts.info else (lambda *a, **k: None)
    for media in media_files:
        if opts.target_date is not None:
            ts = opts.target_date
        else:
            ts = taken_times.get(media)
            if ts is None:
                print(f"SKIP  {media.name}: no embedded date taken found")
                skipped += 1
                continue

        taken = datetime.fromtimestamp(ts).strftime("%Y-%m-%d %H:%M:%S")
        what = "tags + created/modified" if opts.target_date is not None else "created/modified"
        if opts.dry_run:
            log(f"DRY   {media.name}: would set {what} -> {taken}")
            done += 1
            continue

        stamp = file_date_stamp(ts)
        tag_args: list[str] = []
        if opts.target_date is not None:
            exif_stamp = datetime.fromtimestamp(ts).strftime("%Y:%m:%d %H:%M:%S")
            if media.suffix.lower() in VIDEO_EXTS:
                tag_args = [f"-CreateDate={exif_stamp}", f"-MediaCreateDate={exif_stamp}"]
            else:
                tag_args = [f"-DateTimeOriginal={exif_stamp}", f"-CreateDate={exif_stamp}"]
        result = subprocess.run(
            [
                "exiftool", "-overwrite_original", "-m", "-q",
                "-api", "QuickTimeUTC=1",   # write local time as UTC into QuickTime tags
                *tag_args,
                f"-FileCreateDate={stamp}",
                f"-FileModifyDate={stamp}",
                str(media),
            ],
            capture_output=True, text=True,
        )
        if result.returncode != 0:
            print(f"FAIL  {media.name}: {result.stderr.strip()}")
            failed += 1
            continue
        # belt and braces: make sure mtime is exactly the taken time
        os.utime(media, (ts, ts))
        log(f"OK    {media.name}: {what} -> {taken}")
        done += 1

    print(f"\n{done} updated, {skipped} skipped, {failed} failed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
