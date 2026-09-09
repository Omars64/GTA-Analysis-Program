"""Resolve configured listings without depending on theme-specific selectors."""
import re
from urllib.parse import urljoin, urlsplit
from network import get_soup


def resolve_source(url):
    soup = get_soup(url)
    title = soup.find('h1') or soup.title
    title = title.get_text(' ', strip=True) if title else url
    weekly = re.compile(r'(weekly.{0,30}update|event.week|weekly.bonus)', re.I)
    published = soup.find('meta', attrs={'property': 'article:published_time'})
    listing = '/category/' in url or urlsplit(url).query or url.rstrip('/').endswith('/news')
    if not listing and weekly.search(title) and published:
        return url, title
    candidates = []
    for a in soup.select('a[href]'):
        href = urljoin(url, a['href']).split('#')[0]
        label = a.get_text(' ', strip=True)
        if urlsplit(href).hostname != urlsplit(url).hostname or href == url or '/category/' in href:
            continue
        if weekly.search(label + ' ' + href) and 'gta' in (label + href).lower():
            if href not in [row[0] for row in candidates]:
                candidates.append((href, label))
    if candidates:
        return candidates[0]
    if not listing and published and soup.find('article') and soup.select('article h2'):
        return url, title
    raise ValueError('No weekly article links found on this source page.')
