"""Resolve web output in the working project and published crawler package."""
from pathlib import Path


def public_dir(root):
    root = Path(root)
    if root.name == 'crawler' and all((root.parent / name).is_file() for name in
                                    ('index.html', 'app.js', 'fetch_public_notices.py')):
        return root.parent
    return root / 'publish'
