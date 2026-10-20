"""Assemble only public assets; infrastructure and private configuration stay out."""
from pathlib import Path
import shutil

root = Path(__file__).resolve().parent.parent
target = root / '.site'
if target.exists():
    raise SystemExit('Le dossier .site existe déjà. Utiliser un dossier de travail propre.')
target.mkdir()
for pattern in ('*.html', 'favicon.ico', 'robots.txt', 'sitemap.xml', 'site.webmanifest'):
    for source in root.glob(pattern):
        shutil.copy2(source, target / source.name)
for folder in ('css', 'js', 'img', 'media', 'caroussel', 'downloads'):
    shutil.copytree(root / folder, target / folder,
                    ignore=shutil.ignore_patterns('*.exe', 'desktop.ini', 'Thumbs.db'))
print('Site public assemblé dans .site ; installateurs distribués séparément sur le VPS.')
