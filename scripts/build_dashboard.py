"""Build and package the static dashboard from its frozen npm lockfile."""
import hashlib
import os
from pathlib import Path
import shutil
import subprocess
import tempfile

ROOT=Path(__file__).resolve().parents[1]
SOURCE=ROOT/'apps'/'dashboard'
DESTINATION=ROOT/'src'/'work4ce_assistant'/'web_assets'
MARKER='.work4ce-generated'


def fingerprint():
    digest=hashlib.sha256(b'work4ce-static-build-v1')
    files=[]
    for directory,children,names in os.walk(SOURCE):
        children[:]=[name for name in children if name not in {'node_modules','.next','out','.git'}]
        files.extend(Path(directory)/name for name in names if not name.endswith('.tsbuildinfo'))
    files.sort()
    for file in files:
        digest.update(str(file.relative_to(SOURCE)).encode())
        digest.update(file.read_bytes())
    return digest.hexdigest()


def main():
    if not (SOURCE/'package-lock.json').is_file():
        raise SystemExit('Dashboard source and npm lockfile are required.')
    wanted=fingerprint()
    marker=DESTINATION/MARKER
    if marker.is_file() and marker.read_text()==wanted and (DESTINATION/'index.html').is_file():
        print('Dashboard build matches current sources.')
        return
    if DESTINATION.exists() and not marker.is_file():
        raise SystemExit('Refusing to replace unknown dashboard assets without a generated marker.')
    if not shutil.which('npm'):
        raise SystemExit('Node/npm are required to build the dashboard.')
    environment={**os.environ,'NEXT_TELEMETRY_DISABLED':'1'}
    subprocess.run(['npm','ci','--cache',str(ROOT/'.local'/'npm-cache')],cwd=SOURCE,env=environment,check=True)
    subprocess.run(['npm','run','build'],cwd=SOURCE,env=environment,check=True)
    output=SOURCE/'out'
    if not (output/'index.html').is_file() or any(p.is_symlink() for p in output.rglob('*')):
        raise SystemExit('Expected a regular-file-only dashboard export.')
    DESTINATION.parent.mkdir(parents=True,exist_ok=True)
    (ROOT/'.local').mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(dir=ROOT/'.local') as directory:
        stage=Path(directory)/'assets'
        shutil.copytree(output,stage)
        (stage/MARKER).write_text(fingerprint())
        if DESTINATION.exists():
            shutil.rmtree(DESTINATION)
        shutil.copytree(stage,DESTINATION)
    print('Dashboard built and staged in the Python package.')


if __name__=='__main__':
    main()
