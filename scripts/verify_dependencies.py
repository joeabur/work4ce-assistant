"""Check the installed snapshot against the Python 3.12 Linux version lock offline."""
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

mismatched = []
count = 0
for line in (Path(__file__).resolve().parents[1] / 'requirements.lock').read_text().splitlines():
    if not line or line.startswith('#'):
        continue
    count += 1
    name, expected = line.split('==')
    try:
        if version(name) != expected:
            mismatched.append(name)
    except PackageNotFoundError:
        mismatched.append(name)
if mismatched:
    raise SystemExit('Pinned dependency installation required: ' + ', '.join(mismatched))
print(f'All {count} locked distribution versions match the installed environment.')
