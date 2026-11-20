"""Tiny HTTP helpers (standard library only)."""
import json
import ssl
import threading
import time
import urllib.error
import urllib.request

from . import __version__

UA = f"MTGCommanderDeckTester/{__version__} (local deck testing tool)"
_last_call = {}

try:  # certifi avoids "certificate verify failed" with python.org's macOS Python
    import certifi
    _SSL = ssl.create_default_context(cafile=certifi.where())
except Exception:
    _SSL = ssl.create_default_context()


class AccessDenied(RuntimeError):
    pass


_lock = threading.Lock()
_blocked_until = {}  # host -> time until which we must not call it (after HTTP 429)

# Scryfall's documented hard limits: 2 requests/second for these endpoints, 10/second for the rest.
SCRYFALL_HEAVY = ("/cards/search", "/cards/named", "/cards/random", "/cards/collection")


def _bucket(url, min_gap):
    host = url.split("/")[2]
    if host == "api.scryfall.com":
        path = "/" + url.split("/", 3)[3] if url.count("/") >= 3 else "/"
        if path.startswith(SCRYFALL_HEAVY):
            return "scryfall-heavy", max(min_gap, 0.6)
        return host, max(min_gap, 0.12)
    return host, min_gap


def _throttle(url, min_gap):
    key, gap = _bucket(url, min_gap)
    host = url.split("/")[2]
    with _lock:
        now = time.time()
        start = max(now, _last_call.get(key, 0) + gap, _blocked_until.get(host, 0))
        _last_call[key] = start
    if start > now:
        time.sleep(start - now)


def _back_off(url, err):
    """HTTP 429: respect Retry-After (Scryfall asks for 60 s) for every later call to that host."""
    host = url.split("/")[2]
    try:
        wait = int(err.headers.get("Retry-After") or 60)
    except (TypeError, ValueError):
        wait = 60
    with _lock:
        _blocked_until[host] = max(_blocked_until.get(host, 0), time.time() + wait)
    return wait


def blocked_for(host):
    return max(0, _blocked_until.get(host, 0) - time.time())


def get_json(url, host_gap=0.15, retries=3, timeout=30, headers=None):
    host = url.split("/")[2]
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    for attempt in range(retries):
        _throttle(url, host_gap)
        req = urllib.request.Request(url, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (401, 403):
                raise AccessDenied(f"{host} refused access (HTTP {e.code}).")
            if e.code == 429:
                _back_off(url, e)  # later calls wait; this one is retried after the pause
                continue
            if e.code >= 500:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Could not reach {host}")


def post_json(url, payload, headers=None, host_gap=0.15, timeout=120, retries=2):
    host = url.split("/")[2]
    h = {"User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json"}
    h.update(headers or {})
    data = json.dumps(payload).encode("utf-8")
    for attempt in range(retries + 1):
        _throttle(url, host_gap)
        req = urllib.request.Request(url, data=data, headers=h, method="POST")
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < retries:
                _back_off(url, e)
                continue
            body = e.read().decode("utf-8", "replace")[:500]
            raise RuntimeError(f"HTTP {e.code} from {host}: {body}")
