# Duplicate File Remover

Simple Tkinter app to scan folders and move/delete duplicates.

## Features
- Scan within one directory or compare two directories
- Optional recursive scan of subfolders
- Move duplicates to a _duplicates folder (safer default)
- Delete duplicates with a confirmation prompt

## Requirements
- Python 3.8+ (Tkinter is part of the standard library on Windows)

## Install And Run
```bash
python remove_duplicates.py
```

## How To Use
1. Run the app.
2. Choose Directory A.
3. Optionally choose Directory B for comparison modes.
4. Select a Mode: Within Directory A only, Compare A vs B (remove duplicates from B), or Compare B vs A (remove duplicates from A).
5. Choose an Action: Move to _duplicates (safer) or Delete (dangerous).
6. Click "Scan & Run" and review the log.

## How It Works
- Computes SHA-256 hashes in 1 MB chunks
- Files are treated as duplicates when both size and hash match

## Safety Notes
- Moving duplicates is safer than deleting
- Deleting is permanent and cannot be undone
- Back up important files before running

## Screenshots
Add screenshots to show the UI and typical results. Place image files in a `docs/` folder and reference them here.

```markdown
![Main Window](docs/main-window.png)
![Scan Results](docs/scan-results.png)
```

## Bug Reports
Please use the GitHub issue template and include:
- Steps to reproduce
- Expected behavior
- Actual behavior
- Screenshots or logs if helpful

## License
MIT
