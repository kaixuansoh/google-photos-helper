# sync-file-dates

Syncs a file's filesystem creation/modified dates to the capture date already embedded in its metadata.

## When to use it

If your files already carry the correct capture date in their embedded metadata (e.g. straight off a camera) but the filesystem creation/modified dates show the copy date, this fixes just the filesystem side:

- Reads the capture time from each file's own metadata — EXIF `DateTimeOriginal` / `CreateDate` for images, QuickTime `CreateDate` / `MediaCreateDate` for videos (interpreted as UTC, per spec)
- Sets the file's **creation** and **modified** dates to that timestamp
- Never rewrites the media bytes — only filesystem timestamps change
- Files with no embedded capture date are skipped and reported

## Usage

```bash
# Preview what would change (modifies nothing)
python3 sync_file_dates.py /path/to/photos --dry-run

# Sync for real
python3 sync_file_dates.py /path/to/photos

# Also print a log line for every updated file
python3 sync_file_dates.py /path/to/photos --info
```

It recurses into subfolders and accepts multiple folders. Setting the creation date on macOS needs `setfile` from the Xcode command-line tools (exiftool uses it under the hood).

## Forcing a specific date with `--targetDate`

When files have no usable embedded date (or the wrong one) and you know when they were actually taken, pass `--targetDate` to stamp a date of your choosing onto **every** media file in the folder instead of reading dates from the files:

```bash
# Midnight local time on that day
python3 sync_file_dates.py /path/to/photos --targetDate 2019-07-14

# Or with an explicit time
python3 sync_file_dates.py /path/to/photos --targetDate "2019-07-14 15:30:00"
```

Unlike the default mode, this **rewrites the files** to embed the date in their metadata — `DateTimeOriginal` / `CreateDate` for images, `CreateDate` / `MediaCreateDate` (stored as UTC) for videos — and sets the filesystem creation/modified dates to match. `--dry-run` and `--info` work as usual. Use with care: it applies the same date to everything it finds, so point it at a folder that should genuinely share one date.
