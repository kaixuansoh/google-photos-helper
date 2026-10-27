# media-metadata-tools

Command-line tools for repairing photo and video metadata. Each tool lives in its own folder with its own README:

| Tool | What it does |
|---|---|
| [embed-sidecar-metadata](embed-sidecar-metadata/) | Embeds JSON sidecar metadata (taken time, GPS) into the media files themselves |
| [fix-jpeg-extension](fix-jpeg-extension/) | Renames mislabelled JPEGs (`.HEIC`/`.PNG` files that are really JPEG bytes) to `.JPG` |
| [sync-file-dates](sync-file-dates/) | Sets filesystem creation/modified dates to the embedded date taken, or stamps a date of your choosing |

A typical cleanup of an exported photo library runs them in that order: embed the sidecar metadata, fix any extension failures and re-run, then sync the filesystem dates.

## Requirements

- Python 3.10+
- [exiftool](https://exiftool.org/): `brew install exiftool`
