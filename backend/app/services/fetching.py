"""Bounded public HTTP fetches with pinned DNS and manual redirect validation.

Only public IPs are contacted (checked for every redirect hop, and the connection is
pinned to the checked address so DNS cannot change in between). robots.txt is honored,
and there is no login, CAPTCHA or access-control bypass.
"""

import http.client
import ipaddress
import socket
import ssl
import threading
import time
from urllib.parse import quote, urljoin, urlsplit, urlunsplit
from urllib.robotparser import RobotFileParser

from app.core.config import get_settings

AGENT = "RelationshipResearchBot/1.0"
MAX_BYTES = 3 * 1024 * 1024
RETRYABLE_STATUS = {408, 425, 429, 500, 502, 503, 504}
# Translation/tunnel prefixes that is_global accepts but can reach private IPv4 networks.
BLOCKED_NETWORKS = [
    ipaddress.ip_network(n) for n in ("64:ff9b::/96", "64:ff9b:1::/48", "2002::/16", "2001::/32")
]


class FetchError(ValueError):
    """User-safe message; retryable errors may succeed if repeated shortly."""

    def __init__(self, message, retryable=False, retry_after=None):
        super().__init__(message)
        self.retryable = retryable
        self.retry_after = retry_after


def ascii_url(url):
    """The URL as sent on the wire: IDNA host, percent-encoded path and query.

    Search results and redirects carry Turkish characters ("Selçuk_Bayraktar"); http.client
    only sends ASCII. Existing %XX escapes are kept, so an encoded URL is unchanged.
    """
    parts = urlsplit(url)
    if parts.username or parts.password:
        raise FetchError("Unsupported URL")
    try:
        host = (parts.hostname or "").encode("idna").decode("ascii")
        port = parts.port
    except (UnicodeError, ValueError) as exc:
        raise FetchError("Unsupported URL") from exc
    host = f"[{host}]" if ":" in host else host
    netloc = host if port is None else f"{host}:{port}"
    path = quote(parts.path, safe="/%:@!$&'()*+,;=~")
    query = quote(parts.query, safe="/?%:@!$&'()*+,;=~")
    return urlunsplit((parts.scheme, netloc, path, query, ""))


def public_target(url):
    parts = urlsplit(url)
    if (
        parts.scheme not in ("http", "https")
        or not parts.hostname
        or parts.username
        or parts.password
    ):
        raise FetchError("Unsupported URL")
    try:
        port = parts.port or (443 if parts.scheme == "https" else 80)
    except ValueError as exc:
        raise FetchError("Unsupported port") from exc
    if port not in (80, 443):
        raise FetchError("Unsupported port")
    try:
        addresses = socket.getaddrinfo(parts.hostname, port, type=socket.SOCK_STREAM)
    except (socket.gaierror, UnicodeError) as exc:
        raise FetchError("Source address could not be resolved", retryable=True) from exc
    try:
        ips = [ipaddress.ip_address(item[4][0]) for item in addresses]
    except ValueError as exc:
        raise FetchError("Non-public destination blocked") from exc
    if not ips or any(
        not ip.is_global or any(ip in network for network in BLOCKED_NETWORKS) for ip in ips
    ):
        raise FetchError("Non-public destination blocked")
    return parts, addresses[0][4][0], port


class PinnedHTTP(http.client.HTTPConnection):
    def __init__(self, host, ip, port, secure, timeout=8):
        super().__init__(host, port, timeout=timeout)
        self.ip, self.secure = ip, secure
        self.aborted = False
        # http.client adds the port to the Host header unless it is the default; some sites
        # answer "Host: name:443" with a redirect to themselves, 404 or 503.
        self.default_port = 443 if secure else 80

    def connect(self):
        self.sock = socket.create_connection((self.ip, self.port), self.timeout)
        if self.secure:
            self.sock = ssl.create_default_context().wrap_socket(
                self.sock, server_hostname=self.host
            )
        if self.aborted:
            self.abort()

    def abort(self):
        """Called by the watchdog: unblock a recv() stuck on a slowly dripping server."""
        self.aborted = True
        sock = self.sock
        if sock is not None:
            try:
                sock.shutdown(socket.SHUT_RDWR)
            except OSError:
                pass


def retry_after_seconds(value):
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        return None


def fetch_public(url, limit=None, before_request=None):
    settings = get_settings()
    limit = limit or settings.fetch_max_bytes
    deadline = time.monotonic() + settings.fetch_document_seconds
    for _ in range(4):
        if time.monotonic() > deadline:
            raise FetchError("Document time limit exceeded", retryable=True)
        url = ascii_url(url)
        if before_request:
            before_request(url)
        parts, ip, port = public_target(url)
        connection = PinnedHTTP(
            parts.hostname, ip, port, parts.scheme == "https", settings.fetch_timeout_seconds
        )
        # Socket timeouts apply per recv(); the watchdog enforces the whole-document limit.
        abort = getattr(connection, "abort", None)
        watchdog = threading.Timer(max(0.01, deadline - time.monotonic()), abort) if abort else None
        if watchdog:
            watchdog.daemon = True
            watchdog.start()
        try:
            path = parts.path or "/"
            if parts.query:
                path += "?" + parts.query
            connection.request(
                "GET", path, headers={"User-Agent": AGENT, "Accept-Encoding": "identity"}
            )
            response = connection.getresponse()
            if response.status in (301, 302, 303, 307, 308):
                destination = response.getheader("Location")
                if not destination:
                    raise FetchError("Redirect without destination")
                target = urljoin(url, destination)
                if parts.scheme == "https" and urlsplit(target).scheme != "https":
                    raise FetchError("Insecure redirect blocked")
                url = target
                continue
            content = bytearray()
            while True:
                if time.monotonic() > deadline:
                    raise FetchError("Document time limit exceeded", retryable=True)
                # read1 returns after one network read, so the deadline is checked often.
                reader = getattr(response, "read1", response.read)
                chunk = reader(min(65536, limit + 1 - len(content)))
                content.extend(chunk)
                if len(content) > limit:
                    raise FetchError("Document size limit exceeded")
                if not chunk:
                    break
            if getattr(connection, "aborted", False):
                # A shutdown socket reads as EOF; never return a truncated page as complete.
                raise FetchError("Document time limit exceeded", retryable=True)
            return url, response.status, response.getheader("Content-Type", ""), bytes(content), {
                "retry_after": response.getheader("Retry-After")
            }
        except ssl.SSLError as exc:
            if getattr(connection, "aborted", False):
                raise FetchError("Document time limit exceeded", retryable=True) from exc
            raise FetchError("Source TLS certificate could not be verified") from exc
        except (TimeoutError, socket.timeout) as exc:
            raise FetchError("Source did not respond in time", retryable=True) from exc
        except (http.client.HTTPException, OSError) as exc:
            if getattr(connection, "aborted", False):
                raise FetchError("Document time limit exceeded", retryable=True) from exc
            raise FetchError("Source connection failed", retryable=True) from exc
        finally:
            if watchdog:
                watchdog.cancel()
            connection.close()
    raise FetchError("Too many redirects")


class PageFetcher:
    """One instance per job: caches robots.txt and spaces requests per origin."""

    def __init__(self, retries=None, sleep=time.sleep):
        self.robots = {}
        self.last_request = {}
        self.retries = get_settings().fetch_retries if retries is None else retries
        self.sleep = sleep

    def _allow(self, url):
        parts = urlsplit(url)
        origin = f"{parts.scheme}://{parts.netloc}"
        if origin not in self.robots:
            _, status, _, body, _ = fetch_public(origin + "/robots.txt", 256 * 1024)
            parser = RobotFileParser()
            if status in (404, 410):
                parser.parse([])
            elif status == 200:
                parser.parse(body.decode("utf-8", errors="replace").splitlines())
            elif status in RETRYABLE_STATUS:
                raise FetchError("Robots policy temporarily unavailable", retryable=True)
            else:
                raise FetchError("Robots policy unavailable or denied")
            self.robots[origin] = parser
        policy = self.robots[origin]
        if not policy.can_fetch(AGENT, url):
            raise FetchError("Source disallows automated retrieval")
        delay = max(1, policy.crawl_delay(AGENT) or 0)
        if delay > 10:
            raise FetchError("Source crawl delay exceeds job budget")
        self.sleep(max(0, delay - (time.monotonic() - self.last_request.get(origin, 0))))
        self.last_request[origin] = time.monotonic()

    def _fetch_once(self, url):
        final_url, status, content_type, body, meta = fetch_public(url, before_request=self._allow)
        if status in RETRYABLE_STATUS:
            raise FetchError(
                f"Source returned HTTP {status}",
                retryable=True,
                retry_after=retry_after_seconds(meta["retry_after"]),
            )
        if status != 200:
            raise FetchError(f"Source returned HTTP {status}")
        kind = content_type.lower()
        if "text/html" not in kind and "application/xhtml+xml" not in kind:
            raise FetchError("Only HTML profiles are supported in this MVP")
        return final_url, body

    def fetch(self, url):
        for attempt in range(self.retries + 1):
            try:
                return self._fetch_once(url)
            except FetchError as exc:
                wait = exc.retry_after if exc.retry_after is not None else 2**attempt
                if not exc.retryable or attempt == self.retries or wait > 10:
                    raise
                self.sleep(wait)
        raise AssertionError("unreachable")
