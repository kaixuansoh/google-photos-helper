# embed-sidecar-metadata

Writes the metadata from each JSON sidecar (`*.supplemental-metadata.json`) back into the media file itself, so files carry their original timestamps wherever they go next.

## The problem

Some photo export tools ship your media with a JSON sidecar holding the original taken time, instead of embedding it in the file. Move those files anywhere else and the "date taken" shows up as the copy or import date, so your whole library sorts wrong.

## What it writes

- **Images** (JPG, PNG, HEIC, ...): EXIF `DateTimeOriginal` / `CreateDate` in local time, with timezone offset tags
- **Videos** (MP4, MOV, ...): QuickTime create/modify dates in UTC, per spec
- **GPS coordinates** from `geoData`, when present
- **File modified time** set to the taken time, as a fallback for formats without a date tag (e.g. GIF)

It also handles common sidecar naming quirks: truncated JSON filenames, duplicate counters (`IMG(1).JPG` → `IMG.JPG.supplemental-metadata(1).json`), and `-edited` variants that share the original's sidecar.

## Usage

```bash
# Preview what would change (modifies nothing)
python3 embed_sidecar_metadata.py /path/to/photos --dry-run

# Write fixed copies to /path/to/photos-merged (originals untouched)
python3 embed_sidecar_metadata.py /path/to/photos

# Same, but to a folder of your choosing
python3 embed_sidecar_metadata.py /path/to/photos --output /path/to/fixed

# Edit the original files in place instead of writing copies
python3 embed_sidecar_metadata.py /path/to/photos --in-place

# Also print a log line for every successfully updated file
python3 embed_sidecar_metadata.py /path/to/photos --info
```

Point it at the folder holding your media and sidecars; it recurses into subfolders. By default it prints a line for each skipped or failed file plus a final summary; pass `--info` to also log every successfully updated file. The fixed files go to a sibling `<folder>-merged` directory, mirroring the source structure (JSON sidecars are not copied). Note the copies roughly double the disk usage; use `--in-place` if space is tight and you still have the original archive as backup.

Skipped files (no usable JSON sidecar) and failed files (exiftool error) are copied — together with their sidecar, when one exists — into sibling `<folder>-skipped` and `<folder>-failed` directories so you can review or retry them. These folders are only created when there is something to put in them, and failed files are removed from the `-merged` tree so it only ever contains successes.

After running, the photo and video files (not the JSONs) are ready to be stored or uploaded wherever you like.
