"""On-demand, source-attributed vehicle specifications and web image fallback."""
import re
import time
from urllib.parse import urljoin

from network import get_soup, fetch_context
from storage import store
from vehicle_intelligence import vehicle_key, _norm, load_catalog, _best_catalog_match

BASE = 'https://www.gtabase.com/grand-theft-auto-v/vehicles/'


def parse_profile(soup, url, name):
    title = soup.title.get_text(' ', strip=True) if soup.title else ''
    # Exact model boundary: do not confuse e.g. Comet with Comet Retro Custom.
    page_name = re.split(r'\s*[|:]\s*', title)[0]
    if vehicle_key(page_name) != vehicle_key(name):
        return None
    fields, performance = {}, {}
    for row in soup.select('.field-entry'):
        label, value = row.select_one('.field-label'), row.select_one('.field-value')
        if not label or not value:
            continue
        label_text = label.get_text(' ', strip=True).rstrip(':')
        text = value.get_text(' ', strip=True)
        if row.find_parent(class_='gta5-stats') and label_text.lower() in {'speed', 'acceleration', 'braking', 'handling', 'overall'}:
            try:
                number = float(text)
                if 0 <= number <= 100:
                    performance[label_text] = number
            except ValueError:
                pass
        elif label_text in {'Vehicle Class', 'Manufacturer', 'Vehicle Features', 'GTA Online Price', 'Top Speed', 'Top Speed (Game Files)', 'Lap Time', 'Seats', 'Mass / Weight', 'Drive Train', 'Gears'}:
            fields[label_text] = text[:1000]
    resistance = soup.select_one('.field-entry.explosive-resistance .field-value')
    durability = []
    if resistance:
        for row in resistance.select('tr'):
            cells = row.find_all('td')
            if len(cells) == 2:
                durability.append({'weapon': cells[0].get_text(' ', strip=True), 'hits': cells[1].get_text(' ', strip=True)})
    condition = resistance.select_one('.field-prefix') if resistance else None
    images = []
    for meta in soup.select('meta[property="og:image"], meta[name="twitter:image"]'):
        image = urljoin(url, meta.get('content', ''))
        if image.startswith('https://') and image not in images:
            images.append(image)
    return {'name': name, 'source_url': url, 'fields': fields, 'performance': performance,
            'durability': durability, 'durability_conditions': condition.get_text(' ', strip=True) if condition else '',
            'image_urls': images, 'available': True}


def get_profile(name):
    key = vehicle_key(name)
    cached = store.get('vehicle-profiles', key)
    if cached and time.time() - cached.get('checked_at', 0) < (604800 if cached.get('available') else 3600):
        return cached
    match, _ = _best_catalog_match(name, load_catalog())
    slugs = list(dict.fromkeys(filter(None, [(match or {}).get('page_slug'), key.replace(' ', '-'), _norm(name).replace(' ', '-') ])))
    profile = None
    with fetch_context(timeout=7, budget=25):
        for slug in slugs:
            try:
                profile = parse_profile(get_soup(BASE + slug), BASE + slug, name)
                if profile:
                    break
            except InterruptedError:
                raise
            except Exception:
                continue
        if not profile:
            # Search the public vehicle index when a model uses an unexpected slug.
            try:
                directory = store.get('vehicle-profiles', '_directory')
                if not directory or time.time() - directory.get('checked_at', 0) > 604800:
                    soup = get_soup(BASE)
                    links = {}
                    for link in soup.select('a[href]'):
                        url = urljoin(BASE, link['href']).split('?')[0].rstrip('/')
                        label = link.get_text(' ', strip=True) or link.get('title', '')
                        if url.startswith(BASE) and label:
                            links.setdefault(vehicle_key(label), url)
                    directory = {'links': links, 'checked_at': time.time()}
                    store.put('vehicle-profiles', '_directory', directory)
                url = directory['links'].get(key)
                if url:
                    profile = parse_profile(get_soup(url), url, name)
            except InterruptedError:
                raise
            except Exception:
                pass
    result = profile or {'name': name, 'available': False, 'image_urls': [], 'fields': {}, 'performance': {}, 'durability': []}
    result['checked_at'] = time.time()
    store.put('vehicle-profiles', key, result)
    return result
