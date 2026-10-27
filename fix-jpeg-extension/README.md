# fix-jpeg-extension

Renames mislabelled JPEG files to `.JPG` in place.

## The problem

Some exported files carry the wrong extension — the bytes are actually JPEG but the file is named `.HEIC` or `.PNG` — which makes tools like exiftool fail with errors like `Not a valid HEIC`.

## The fix

The script sniffs each file's magic bytes and, when the content is JPEG but the extension says otherwise, renames the file to `.JPG` in place, along with its `.supplemental-metadata.json` sidecar so the pairing still works. Genuinely non-JPEG files are left untouched.

## Usage

```bash
# Preview what would be renamed
python3 fix_jpeg_extension.py /path/to/photos --dry-run

# Rename for real
python3 fix_jpeg_extension.py /path/to/photos
```
