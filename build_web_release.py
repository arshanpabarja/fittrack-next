"""Build an allowlisted web release, without local databases, secrets or desktop UI."""
import argparse
import hashlib
import json
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


ROOT = Path(__file__).resolve().parent
PAGES = ('index', 'coaches', 'bodybuilding', 'calisthenics', 'functional', 'login',
         'signup', 'pending', 'dashboard', 'admin', 'admin-panel', 'coach-panel')
ASSET_SUFFIXES = {'.png', '.jpg', '.jpeg', '.webp', '.svg', '.ttf', '.woff', '.woff2', '.mp4', '.css', '.txt'}


def release_files():
    files = list((ROOT / 'web_portal').rglob('*.py'))
    files = [path for path in files if '__pycache__' not in path.parts]
    files += [ROOT / 'app' / name for name in (
        '__init__.py', 'domain/__init__.py', 'domain/dates.py', 'domain/membership.py')]
    files += [ROOT / 'lifebox-landing' / (page + '.html') for page in PAGES]
    files += [ROOT / 'lifebox-landing' / name for name in (
        'app.js', 'styles.css', 'owner.js', 'owner.css', 'coach.js', 'coach.css', 'member.js', 'member.css', 'robots.txt', 'sitemap.xml', 'PRODUCTION.md')]
    files += [path for path in (ROOT / 'lifebox-landing/assets').rglob('*')
              if path.is_file() and path.suffix.lower() in ASSET_SUFFIXES]
    files += [ROOT / 'deploy' / name for name in (
        'requirements-web.txt', 'deploy.env.example', 'gunicorn.conf.py',
        'lifebox.service.example', 'nginx.conf.example', 'README.md')]
    files += [ROOT / name for name in ('CLOUD_DEPLOYMENT.md', 'OWNER_PANEL.md', 'COACH_PANEL.md', 'MEMBER_PANEL.md')]
    for path in files:
        if not path.is_file() or path.is_symlink():
            raise ValueError(f'Missing or symbolic release file: {path.relative_to(ROOT)}')
        path.resolve().relative_to(ROOT)
    return sorted(set(files))


def build_release(output):
    output = Path(output).resolve()
    files = release_files()
    if output in files:
        raise ValueError('Output cannot overwrite a release source')
    output.parent.mkdir(parents=True, exist_ok=True)
    manifest = {}
    with ZipFile(output, 'w', ZIP_DEFLATED, compresslevel=6) as archive:
        for path in files:
            name = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            archive.writestr(name, data)
            manifest[name] = hashlib.sha256(data).hexdigest()
        archive.writestr('release-manifest.json', json.dumps(manifest, indent=2) + '\n')
    return output, len(files)


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist/lifebox-web.zip')
    args = parser.parse_args()
    output, count = build_release(args.output)
    print(f'Web release: {output} ({count} files, {output.stat().st_size:,} bytes)')
