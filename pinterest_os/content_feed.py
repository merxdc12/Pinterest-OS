"""Bounded, read-only ITHutir RSS import. Image URLs are metadata, never fetched."""
from __future__ import annotations

from html.parser import HTMLParser
import ipaddress
import re
import time
from urllib.error import URLError
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit
from urllib.request import HTTPRedirectHandler, Request, build_opener
from xml.etree import ElementTree as ET

FEED_URL = 'https://ithutir.com/rss.xml'
MAX_BYTES = 2 * 1024 * 1024
MAX_ITEMS = 200
TIMEOUT = 10


def canonical_url(value: str, base: str = '') -> str:
    value = value.strip()
    if not value or re.search(r'[\x00-\x20\x7f\\]', value):
        raise ValueError('Use an absolute HTTP(S) URL without credentials or whitespace.')
    parsed = urlsplit(urljoin(base, value) if base else value)
    host = parsed.hostname
    if parsed.scheme not in ('https', 'http') or not host or parsed.username or parsed.password:
        raise ValueError('Only public HTTP(S) URLs without credentials are allowed.')
    host = host.lower().rstrip('.')
    if host == 'localhost' or host.endswith(('.localhost', '.local')) or '.' not in host:
        raise ValueError('Local URLs are not allowed.')
    try:
        if not ipaddress.ip_address(host).is_global:
            raise ValueError('Private IP URLs are not allowed.')
    except ValueError as exc:
        if 'not allowed' in str(exc):
            raise
    port = parsed.port
    netloc = f'[{host}]' if ':' in host else host.encode('idna').decode('ascii')
    if port and (parsed.scheme, port) not in (('https', 443), ('http', 80)):
        netloc += f':{port}'
    query = [(key, val) for key, val in parse_qsl(parsed.query, keep_blank_values=True)
             if not key.lower().startswith('utm_') and key.lower() not in ('fbclid', 'gclid')]
    return urlunsplit((parsed.scheme, netloc, parsed.path or '/', urlencode(sorted(query)), ''))


class _HTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.parts, self.images, self.blocked = [], [], 0

    def handle_starttag(self, tag, attrs):
        if tag in ('script', 'style'):
            self.blocked += 1
        if not self.blocked and tag == 'img':
            self.images.append(dict(attrs).get('src', ''))

    def handle_endtag(self, tag):
        if tag in ('script', 'style'):
            self.blocked = max(0, self.blocked - 1)

    def handle_data(self, data):
        if not self.blocked:
            self.parts.append(data)


def plain_text(value: str, limit: int = 10000) -> str:
    parser = _HTML()
    parser.feed(value)
    return ' '.join(' '.join(parser.parts).split())[:limit]


def parse_feed(data: bytes, *, limit: int = MAX_ITEMS) -> list[dict]:
    if not 1 <= limit <= MAX_ITEMS:
        raise ValueError(f'Item limit must be between 1 and {MAX_ITEMS}.')
    if len(data) > MAX_BYTES:
        raise ValueError('RSS exceeds the 2 MiB limit.')
    # Reject DTDs/entities, including UTF-16/32 encodings that obscure declarations.
    if b'\x00' in data or re.search(br'<!\s*(DOCTYPE|ENTITY)', data, re.I):
        raise ValueError('RSS DTDs, entities and non UTF-8-compatible XML are not supported.')
    try:
        root = ET.fromstring(data)
    except ET.ParseError as exc:
        raise ValueError('Malformed RSS XML; the previous import has been retained.') from exc
    if root.tag != 'rss' or root.find('channel') is None:
        raise ValueError('Expected an RSS channel.')
    rows = []
    for item in root.find('channel').iterfind('item'):
        if len(rows) >= limit:
            break
        try:
            url = canonical_url(item.findtext('link') or '', FEED_URL)
        except ValueError:
            continue
        title = plain_text(item.findtext('title') or '', 500)
        if not title:
            continue
        html = item.findtext('{http://purl.org/rss/1.0/modules/content/}encoded') or item.findtext('description') or ''
        parser = _HTML()
        parser.feed(html)
        images = []
        for child in item.iter():
            if child.tag in ('{http://search.yahoo.com/mrss/}content',
                             '{http://search.yahoo.com/mrss/}thumbnail'):
                if child.get('medium', 'image') == 'image' and child.get('type', 'image/').startswith('image/'):
                    images.append(child.get('url', ''))
            elif child.tag == 'enclosure' and child.get('type', '').startswith('image/'):
                images.append(child.get('url', ''))
        images.extend(parser.images)
        image_url = ''
        for image in images:
            try:
                image_url = canonical_url(image, url)
                break
            except ValueError:
                continue
        rows.append(dict(canonical_url=url, guid=plain_text(item.findtext('guid') or '', 1000) or None,
                         title=title, summary=plain_text(html), image_url=image_url,
                         published_at=plain_text(item.findtext('pubDate') or '', 100) or None))
    return rows


class _NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        raise ValueError('RSS redirected; refresh refused. Only the configured HTTPS feed is read.')


def fetch_feed() -> bytes:
    """One fixed HTTPS GET, default TLS verification, no auth/cookies/redirects."""
    request = Request(FEED_URL, headers={'User-Agent': 'ITHutir-PinterestOS/1.0',
                                      'Accept': 'application/rss+xml, application/xml, text/xml'})
    try:
        started = time.monotonic()
        with build_opener(_NoRedirect()).open(request, timeout=TIMEOUT) as response:
            chunks, size = [], 0
            while True:
                # One buffered/socket read per iteration lets the total deadline be checked
                # even when a server continuously trickles data below the socket timeout.
                chunk = response.read1(65536)
                size += len(chunk)
                if size > MAX_BYTES or time.monotonic() - started > 30:
                    raise ValueError('RSS exceeds the size or total time limit.')
                if not chunk:
                    return b''.join(chunks)
                chunks.append(chunk)
    except (URLError, TimeoutError, OSError) as exc:
        raise ValueError('RSS unavailable. Check the network and retry; saved sources are retained.') from exc
