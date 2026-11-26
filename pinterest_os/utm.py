"""Shared ITHutir campaign URL rules. Only owned HTTPS destinations are rewritten."""
import re
from urllib.parse import urlsplit, urlunsplit, unquote_plus, urlencode

SOURCES = {"pinterest": "pint", "youtube": "yt", "facebook": "fb", "tiktok": "tik"}
OWNED_HOSTS = {"ithutir.com", "www.ithutir.com"}
UTM_KEYS = {"utm_source", "utm_medium", "utm_campaign", "utm_content", "utm_term"}

def marketing_url(original: str, source: str, campaign: str, content_id: str, term: str = "") -> str:
    """Preserve unrelated query bytes and fragments; reject unapproved destinations."""
    if source not in SOURCES.values():
        raise ValueError("Unknown marketing source")
    if not re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,99}", campaign):
        raise ValueError("Invalid campaign slug")
    if not re.fullmatch(re.escape(source) + r"_[0-9]{6,}", content_id):
        raise ValueError("Invalid content tracking ID")
    if re.search(r"[\x00-\x20\x7f\\]", original):
        raise ValueError("Invalid URL characters")
    parts = urlsplit(original)
    if (parts.scheme != "https" or parts.hostname not in OWNED_HOSTS
            or parts.username is not None or parts.password is not None
            or parts.port not in (None, 443)):
        raise ValueError("External or non-HTTPS destination: manual partner-rule review required")
    query = [field for field in parts.query.split("&") if field
             and unquote_plus(field.partition("=")[0]).lower() not in UTM_KEYS]
    values = {"utm_source": source, "utm_medium": "organic_social",
              "utm_campaign": campaign, "utm_content": content_id}
    if term:
        values["utm_term"] = term
    query.append(urlencode(values))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, "&".join(query), parts.fragment))


def new_tracking_id(source: str) -> str:
    """Random UUID4-derived numeric ID; independent of local DB and backup sequence."""
    from uuid import uuid4
    if source not in SOURCES.values():
        raise ValueError("Unknown marketing source")
    return f"{source}_{uuid4().int:039d}"


def read_tracking_id(url: str, source: str) -> str:
    """Read the issued code from the saved URL, including legacy short codes."""
    from urllib.parse import parse_qs
    values = parse_qs(urlsplit(url).query).get("utm_content", [])
    if len(values) != 1 or not re.fullmatch(re.escape(source) + r"_[0-9]{6,}", values[0]):
        raise ValueError("Invalid stored tracking code")
    return values[0]
