"""Create a complete portable package from a finished PyInstaller build."""
import argparse
import hashlib
from pathlib import Path
import shutil
import zipfile

ROOT = Path(__file__).resolve().parents[1]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--dist', type=Path, default=ROOT / 'dist/Just Trim')
    parser.add_argument('--out', type=Path, default=ROOT / 'release')
    args = parser.parse_args()
    assert (args.dist / 'Just Trim.exe').is_file(), 'Build the executable first'
    args.out.mkdir(parents=True, exist_ok=True)
    destination = args.out / 'JustTrim-Windows'
    if destination.exists():
        raise SystemExit('Destination exists; use a new --out folder or archive the old package first.')
    shutil.copytree(args.dist, destination)
    for name in ('README.md', 'LICENSE.txt', 'THIRD-PARTY-NOTICES.txt', 'CHANGELOG.md'):
        shutil.copy2(ROOT / name, destination / name)
    shutil.copy2(ROOT / 'docs/START HERE.txt', destination / 'START HERE.txt')
    shutil.copytree(ROOT / 'licenses', destination / 'licenses')
    shutil.copytree(ROOT / 'docs', destination / 'docs')
    source = destination / 'source'
    source.mkdir()
    for name in ('src', 'tests', 'scripts', 'docs', 'licenses'):
        shutil.copytree(ROOT / name, source / name,
                        ignore=shutil.ignore_patterns('__pycache__', '*.pyc'))
    for name in ('README.md', 'LICENSE.txt', 'THIRD-PARTY-NOTICES.txt',
                 'CHANGELOG.md', 'requirements.txt', '.gitignore', '.gitattributes'):
        shutil.copy2(ROOT / name, source / name)
    archive = args.out / 'JustTrim-Windows.zip'
    with zipfile.ZipFile(archive, 'w', zipfile.ZIP_DEFLATED, compresslevel=6) as zipped:
        for file in sorted(destination.rglob('*')):
            if file.is_file():
                zipped.write(file, Path(destination.name) / file.relative_to(destination))
    with zipfile.ZipFile(archive) as zipped:
        assert zipped.testzip() is None, 'ZIP integrity failed'
    digest = hashlib.sha256(archive.read_bytes()).hexdigest()
    archive.with_suffix('.zip.sha256.txt').write_text(digest + '  ' + archive.name + '\n')
    print(f'Created {archive} ({archive.stat().st_size:,} bytes)\nSHA256 {digest}')


if __name__ == '__main__':
    main()
