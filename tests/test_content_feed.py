"""RSS security, image tag coverage and persistent identity/evidence contracts."""
from unittest.mock import MagicMock, patch
from urllib.error import URLError

import pytest

from pinterest_os.content_factory import ContentFactory
from pinterest_os.content_feed import (
    FEED_URL, MAX_BYTES, _NoRedirect, canonical_url, fetch_feed, parse_feed,
)
from pinterest_os.storage import Storage


def rss(*items):
    return ('<rss version="2.0" xmlns:media="http://search.yahoo.com/mrss/" '
            'xmlns:content="http://purl.org/rss/1.0/modules/content/"><channel>' +
            ''.join(items) + '</channel></rss>').encode()


def item(link='/article', guid='a', extra=''):
    return f'<item><title>Engineering &amp; DIY</title><link>{link}</link><guid>{guid}</guid><description>Summary</description>{extra}</item>'


@pytest.mark.parametrize('tag', [
    '<media:content url="/cover.png" type="image/png"/>',
    '<media:thumbnail url="/cover.png"/>',
    '<enclosure url="/cover.png" type="image/png"/>',
    '<content:encoded><![CDATA[<script>bad()</script><p>Useful text</p><img src="/cover.png">]]></content:encoded>',
])
def test_supported_image_tags_and_plain_text(tag):
    row = parse_feed(rss(item(extra=tag)))[0]
    assert row['canonical_url'] == 'https://ithutir.com/article'
    assert row['image_url'] == 'https://ithutir.com/cover.png'
    assert 'bad()' not in row['summary']
    assert row['title'] == 'Engineering & DIY'


def test_missing_and_unsafe_images_remain_missing():
    for tag in ('', '<media:thumbnail url="file:///etc/passwd"/>', '<enclosure url="https://example.com/a.mp3" type="audio/mpeg"/>'):
        assert parse_feed(rss(item(extra=tag)))[0]['image_url'] == ''


@pytest.mark.parametrize('url', ['file:///etc/passwd', 'javascript:alert(1)', 'data:image/png;base64,abc',
                                'https://user:pass@example.com/a', 'http://127.0.0.1/a', 'http://localhost/a',
                                'https://10.0.0.1/a', 'https://example.com/with space', 'https://example.com:bad/a',
                                'https://example.com\\@127.0.0.1/a', '//localhost/a'])
def test_unsafe_urls_rejected(url):
    with pytest.raises(ValueError):
        canonical_url(url, FEED_URL)
    assert parse_feed(rss(item(link=url))) == []


def test_canonicalization_and_relative_links():
    assert canonical_url('HTTPS://ITHUTIR.COM:443/article?b=2&utm_source=pin&a=1#top') == 'https://ithutir.com/article?a=1&b=2'
    assert parse_feed(rss(item('../article')))[0]['canonical_url'] == 'https://ithutir.com/article'
    assert canonical_url('https://example.com/a?article=2') != canonical_url('https://example.com/a?article=3')


@pytest.mark.parametrize('data', [b'<rss>', b'<html/>', b'<!DOCTYPE rss [<!ENTITY x "bad">]><rss><channel/></rss>',
                                 '<rss><channel/></rss>'.encode('utf-16'), b'x' * (MAX_BYTES + 1)])
def test_malformed_and_unbounded_xml_rejected(data):
    with pytest.raises(ValueError):
        parse_feed(data)


def test_bounded_item_count():
    assert len(parse_feed(rss(*(item(f'/a/{i}', str(i)) for i in range(250))))) == 200
    assert len(parse_feed(rss(item(), item('/b', 'b')), limit=1)) == 1
    with pytest.raises(ValueError):
        parse_feed(rss(item()), limit=1000)


def test_fetch_is_fixed_https_get_with_timeout_no_redirects():
    response = MagicMock()
    response.__enter__.return_value = response
    response.read1.side_effect = [rss(item()), b'']
    opener = MagicMock()
    opener.open.return_value = response
    with patch('pinterest_os.content_feed.build_opener', return_value=opener):
        assert parse_feed(fetch_feed())
    args, kwargs = opener.open.call_args
    assert args[0].full_url == FEED_URL
    assert args[0].get_method() == 'GET'
    assert not args[0].has_header('Authorization')
    assert kwargs['timeout'] == 10
    with pytest.raises(ValueError, match='redirected'):
        _NoRedirect().redirect_request(None, None, 302, '', {}, 'http://127.0.0.1/')


def test_network_failure_message_and_size_bound():
    with patch('pinterest_os.content_feed.build_opener') as opener:
        opener.return_value.open.side_effect = URLError('offline')
        with pytest.raises(ValueError, match='RSS unavailable'):
            fetch_feed()
    response = MagicMock()
    response.__enter__.return_value = response
    response.read1.return_value = b'x' * 65536
    with patch('pinterest_os.content_feed.build_opener') as opener:
        opener.return_value.open.return_value = response
        with pytest.raises(ValueError, match='size or total time'):
            fetch_feed()


def test_guid_url_aliases_refresh_failures_and_confirmation_preserved(tmp_path):
    db = Storage(tmp_path / 'rss.sqlite3')
    try:
        factory = ContentFactory(db)
        factory.refresh_feed(lambda: rss(item()))
        sid = factory.sources()[0]['id']
        # Same GUID with a new URL, then same URL with a new GUID: one source.
        factory.refresh_feed(lambda: rss(item('/renamed', 'a')))
        factory.refresh_feed(lambda: rss(item('/renamed', 'new-guid')))
        factory.refresh_feed(lambda: rss(item('/article?utm_source=pin', 'a')))
        assert len(factory.sources()) == 1
        assert factory.sources()[0]['id'] == sid
        ledger = factory.rows('SELECT * FROM rss_publication_ledger')[0]
        assert ledger['eligibility_state'] == 'RSS_ELIGIBLE'
        assert ledger['remote_publication_state'] == 'UNKNOWN'
        assert ledger['pinterest_connection_state'] == 'PINTEREST_CONNECTION_UNKNOWN'
        factory.confirm_publication(ledger['id'], 'https://www.pinterest.com/pin/123456/')
        factory.refresh_feed(lambda: rss(item()))
        assert factory.rows('SELECT * FROM rss_publication_ledger')[0]['remote_publication_state'] == 'PUBLISHED_CONFIRMED'
        with pytest.raises(ValueError):
            factory.refresh_feed(lambda: b'<bad')
        state = factory.rows('SELECT * FROM content_feed_refresh')[0]
        assert state['status'] == 'ERROR' and state['succeeded_at']
        assert len(factory.sources()) == 1
        with pytest.raises(OSError):
            factory.refresh_feed(lambda: (_ for _ in ()).throw(OSError('offline')))
        assert len(factory.sources()) == 1
    finally:
        db.close()


def test_conflicting_aliases_do_not_merge_sources(tmp_path):
    db = Storage(tmp_path / 'rss.sqlite3')
    try:
        factory = ContentFactory(db)
        factory.refresh_feed(lambda: rss(item('/a', 'a'), item('/b', 'b')))
        message = factory.refresh_feed(lambda: rss(item('/a', 'b')))
        assert '1 conflicting aliases skipped' in message
        assert len(factory.sources()) == 2
    finally:
        db.close()
