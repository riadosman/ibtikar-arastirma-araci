"""Request encoding: what the fetcher puts on the wire for real-world URLs."""

from urllib.parse import urlsplit

import pytest

from app.services import fetching
from app.services.fetching import FetchError


def test_https_requests_send_the_host_without_the_default_port():
    # "Host: example.org:443" made WordPress sites redirect to themselves forever and
    # other servers answer 404 or 503 (fintechistanbul.org, marmara.edu.tr, bilkent.edu.tr).
    secure = fetching.PinnedHTTP("example.org", "93.184.216.34", 443, True)
    secure.putrequest("GET", "/ekip/")
    assert b"Host: example.org" in secure._buffer
    plain = fetching.PinnedHTTP("example.org", "93.184.216.34", 80, False)
    plain.putrequest("GET", "/")
    assert b"Host: example.org" in plain._buffer


class Response:
    def __init__(self, status, location=None, body=b"<html>ok</html>"):
        self.status, self.location, self.body = status, location, body

    def getheader(self, name, default=None):
        return {"Location": self.location, "Content-Type": "text/html"}.get(name, default)

    def read(self, size):
        chunk, self.body = self.body, b""
        return chunk


def wire(monkeypatch, responses):
    """Record the host and path of every request instead of opening sockets."""
    sent, targets = [], []
    monkeypatch.setattr(fetching, "public_target",
                        lambda url: targets.append(url) or (urlsplit(url), "93.184.216.34", 443))

    class Connection:
        def __init__(self, host, *args):
            self.host = host

        def request(self, method, path, headers):
            path.encode("ascii")  # http.client sends the request line as ASCII
            sent.append((self.host, path))

        def getresponse(self):
            return responses.pop(0)

        def close(self):
            pass

    monkeypatch.setattr(fetching, "PinnedHTTP", Connection)
    return sent, targets


def test_turkish_characters_in_a_url_are_percent_encoded(monkeypatch):
    # Every robots-allowed URL with "ç", "İ" or "ö" in its path failed with UnicodeEncodeError.
    sent, _ = wire(monkeypatch, [Response(200)])
    final, status, _, body, _ = fetching.fetch_public("https://tr.wikipedia.org/wiki/Selçuk_Bayraktar")
    assert sent == [("tr.wikipedia.org", "/wiki/Sel%C3%A7uk_Bayraktar")]
    assert status == 200 and body == b"<html>ok</html>"
    assert final == "https://tr.wikipedia.org/wiki/Sel%C3%A7uk_Bayraktar"


def test_encoded_urls_queries_and_redirect_targets_stay_valid(monkeypatch):
    sent, targets = wire(monkeypatch, [
        Response(301, location="/wiki/İstanbul_Teknik_Üniversitesi?ara=öğretim üyeleri"),
        Response(200),
    ])
    fetching.fetch_public("https://tr.wikipedia.org/wiki/Sel%C3%A7uk_Bayraktar?q=a%20b&x=1")
    assert sent[0][1] == "/wiki/Sel%C3%A7uk_Bayraktar?q=a%20b&x=1"  # already encoded: unchanged
    assert sent[1][1] == ("/wiki/%C4%B0stanbul_Teknik_%C3%9Cniversitesi"
                          "?ara=%C3%B6%C4%9Fretim%20%C3%BCyeleri")
    assert all(url.isascii() for url in targets)


def test_international_domain_names_are_resolved_in_ascii(monkeypatch):
    sent, targets = wire(monkeypatch, [Response(200)])
    fetching.fetch_public("https://müzik.example/ekip")
    assert targets == ["https://xn--mzik-0ra.example/ekip"]
    assert sent == [("xn--mzik-0ra.example", "/ekip")]


@pytest.mark.parametrize("url", [
    "https://" + "ü" * 70 + ".example/",  # label too long for IDNA
    "https://user:secret@example.org/",
])
def test_unusable_urls_fail_as_a_source_error_not_a_crash(url):
    with pytest.raises(FetchError, match="Unsupported URL"):
        fetching.fetch_public(url)
