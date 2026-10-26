# google-photos-helper

Merges the metadata JSON sidecars from a Google Photos Takeout export back into the image and video files themselves.

## The problem

Google Takeout exports your photos with a JSON sidecar (`*.supplemental-metadata.json`) holding the original taken time, instead of embedding it in the file. Move those files anywhere else and the "date taken" shows up as the copy or import date, so your whole library sorts wrong.

## The fix

`merge_metadata.py` writes the metadata from each JSON sidecar back into the media file itself:

- **Images** (JPG, PNG, HEIC, ...): EXIF `DateTimeOriginal` / `CreateDate` in local time, with timezone offset tags
- **Videos** (MP4, MOV, ...): QuickTime create/modify dates in UTC, per spec
- **GPS coordinates** from `geoData`, when present
- **File modified time** set to the taken time, as a fallback for formats without a date tag (e.g. GIF)

With the metadata embedded in the files themselves, they keep their original timestamps no matter where you move or upload them.

It also handles Takeout's sidecar naming quirks: truncated JSON filenames, duplicate counters (`IMG(1).JPG` → `IMG.JPG.supplemental-metadata(1).json`), and `-edited` variants that share the original's sidecar.

## Requirements

- Python 3.10+
- [exiftool](https://exiftool.org/): `brew install exiftool`

## Usage

```bash
# Preview what would change (modifies nothing)
python3 merge_metadata.py /path/to/Takeout --dry-run

# Write fixed copies to /path/to/Takeout-merged (originals untouched)
python3 merge_metadata.py /path/to/Takeout

# Same, but to a folder of your choosing
python3 merge_metadata.py /path/to/Takeout --output /path/to/fixed

# Edit the original files in place instead of writing copies
python3 merge_metadata.py /path/to/Takeout --in-place

# Also print a log line for every successfully updated file
python3 merge_metadata.py /path/to/Takeout --info
```

Point it at your extracted Takeout folder; it recurses into subfolders. By default it prints a line for each skipped or failed file plus a final summary; pass `--info` to also log every successfully updated file. The fixed files go to a sibling `<folder>-merged` directory, mirroring the source structure (JSON sidecars are not copied). Note the copies roughly double the disk usage; use `--in-place` if space is tight and you still have the Takeout zip as backup.

Skipped files (no usable JSON sidecar) and failed files (exiftool error) are copied — together with their sidecar, when one exists — into sibling `<folder>-skipped` and `<folder>-failed` directories so you can review or retry them. These folders are only created when there is something to put in them, and failed files are removed from the `-merged` tree so it only ever contains successes.

After running, the photo and video files (not the JSONs) are ready to be stored or uploaded wherever you like.
