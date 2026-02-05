# Duplicate File Remover

Simple Tkinter app to scan folders and move/delete duplicates.

## Features
- Scan within one directory or compare two directories
- Optional recursive scan of subfolders
- Move duplicates to a _duplicates folder (safer default)
- Delete duplicates with a confirmation prompt

## Requirements
- Python 3.8+ (Tkinter is part of the standard library on Windows)

## Run
```bash
python remove_duplicates.py
```

## How It Works
- Computes SHA-256 hashes in 1 MB chunks
- Files are treated as duplicates when both size and hash match

## Safety Notes
- Moving duplicates is safer than deleting
- Deleting is permanent and cannot be undone
- Back up important files before running

## License
MIT
