"""Tiny HTTP helpers (standard library only)."""
import json
import ssl
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


def _throttle(host, min_gap):
    now = time.time()
    wait = _last_call.get(host, 0) + min_gap - now
    if wait > 0:
        time.sleep(wait)
    _last_call[host] = time.time()


def get_json(url, host_gap=0.15, retries=3, timeout=30, headers=None):
    host = url.split("/")[2]
    h = {"User-Agent": UA, "Accept": "application/json"}
    h.update(headers or {})
    for attempt in range(retries):
        _throttle(host, host_gap)
        req = urllib.request.Request(url, headers=h)
        try:
            with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
                return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return None
            if e.code in (401, 403):
                raise AccessDenied(f"{host} refused access (HTTP {e.code}).")
            if e.code == 429 or e.code >= 500:
                time.sleep(2 * (attempt + 1))
                continue
            raise
        except (urllib.error.URLError, TimeoutError):
            time.sleep(2 * (attempt + 1))
    raise RuntimeError(f"Could not reach {host}")


def post_json(url, payload, headers=None, host_gap=0.15, timeout=120):
    host = url.split("/")[2]
    _throttle(host, host_gap)
    h = {"User-Agent": UA, "Accept": "application/json", "Content-Type": "application/json"}
    h.update(headers or {})
    req = urllib.request.Request(url, data=json.dumps(payload).encode("utf-8"), headers=h, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL) as r:
            return json.loads(r.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        body = e.read().decode("utf-8", "replace")[:500]
        raise RuntimeError(f"HTTP {e.code} from {host}: {body}")
