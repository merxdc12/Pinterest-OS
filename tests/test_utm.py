import pytest
from urllib.parse import parse_qs, urlsplit
from pinterest_os.utm import marketing_url, SOURCES

@pytest.mark.parametrize("source", SOURCES.values())
def test_source(source):
    result = marketing_url("https://ithutir.com/a?x=%2F&UTM_SOURCE=old&utm_source=old#section",
                           source, "electronics", source + "_000001")
    assert "x=%2F" in result
    assert urlsplit(result).fragment == "section"
    assert parse_qs(urlsplit(result).query)["utm_source"] == [source]
    assert marketing_url(result, source, "electronics", source + "_000001") == result

@pytest.mark.parametrize("url", ["https://amazon.com/a?tag=example", "https://ithutir.com.evil.example/",
    "https://ithutir.com@evil.example/", "http://ithutir.com/", "https://ithutir.com:444/", "https://ithutir.com/ a"])
def test_external_or_invalid(url):
    with pytest.raises(ValueError):
        marketing_url(url, "pint", "electronics", "pint_000001")

def test_wrong_prefix():
    with pytest.raises(ValueError):
        marketing_url("https://ithutir.com/", "pint", "electronics", "tik_000001")

def test_optional_term():
    result = marketing_url("https://ithutir.com/?utm_term=old", "pint", "electronics", "pint_000001", "digital multimeter")
    assert parse_qs(urlsplit(result).query)["utm_term"] == ["digital multimeter"]
