"""SoundCloud client.

Talks to the public ``api-v2.soundcloud.com`` HTTPS API. SoundCloud signs
every request with a ``client_id`` it embeds inside the JS bundles served
from soundcloud.com — we extract a fresh one on first use and cache it.

This is the same approach that yt-dlp uses (see
``yt_dlp/extractor/soundcloud.py``) — they refresh the id periodically and
fall back to a known set if extraction fails.

Note: the stream URLs returned by ``/tracks/{id}`` / search etc. are
short-lived and tied to a particular client_id. Always re-fetch via
:meth:`SoundCloudClient.stream_url` right before passing the URL to mpv.
"""
from __future__ import annotations

import json
import logging
import random
import re
import threading
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

log = logging.getLogger(__name__)

API = "https://api-v2.soundcloud.com"
HOME = "https://soundcloud.com/"
# Static fallbacks. Burnt one usually means the next has at least a few
# hours of life left; we always try to extract fresh first.
FALLBACK_CLIENT_IDS = (
    "iZIs9mchVcX5lhVRyQGGAYlNPVldzAoX",
    "qqK17BOlF1WUg4xCfCxL5RPTBVgNTyKn",
)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
)

# SoundCloud's public genre list, from /charts UI.
GENRES = (
    ("all-music", "Все жанры"),
    ("alternativerock", "Alternative Rock"),
    ("ambient", "Ambient"),
    ("classical", "Classical"),
    ("country", "Country"),
    ("danceedm", "Dance & EDM"),
    ("dancehall", "Dancehall"),
    ("deephouse", "Deep House"),
    ("disco", "Disco"),
    ("drumbass", "Drum & Bass"),
    ("dubstep", "Dubstep"),
    ("electronic", "Electronic"),
    ("folksingersongwriter", "Folk & Singer-Songwriter"),
    ("hiphoprap", "Hip-Hop & Rap"),
    ("house", "House"),
    ("indie", "Indie"),
    ("jazzblues", "Jazz & Blues"),
    ("latin", "Latin"),
    ("metal", "Metal"),
    ("piano", "Piano"),
    ("pop", "Pop"),
    ("rbsoul", "R&B & Soul"),
    ("reggae", "Reggae"),
    ("reggaeton", "Reggaeton"),
    ("rock", "Rock"),
    ("soundtrack", "Soundtrack"),
    ("techno", "Techno"),
    ("trance", "Trance"),
    ("triphop", "Trip Hop"),
    ("world", "World"),
)


@dataclass
class Track:
    """One SoundCloud track."""

    id: int
    title: str
    artist: str
    duration_ms: int
    permalink_url: str
    artwork_url: str | None
    waveform_url: str | None
    genre: str
    raw: dict = field(default_factory=dict, repr=False)

    @property
    def duration_str(self) -> str:
        s = max(0, self.duration_ms // 1000)
        h, rem = divmod(s, 3600)
        m, sec = divmod(rem, 60)
        if h:
            return f"{h}:{m:02d}:{sec:02d}"
        return f"{m}:{sec:02d}"

    @property
    def display_artwork(self) -> str | None:
        """Bigger artwork URL (500px instead of default 100px)."""
        url = self.artwork_url
        if not url:
            return None
        # SoundCloud returns t500x500 / t300x300 / large; t500x500 looks best for wallpapers.
        for marker in ("-large.", "-t500x500.", "-t300x300.", "-badge."):
            if marker in url:
                return url.replace("-large.", "-t500x500.").replace(
                    "-t300x300.", "-t500x500."
                )
        return url

    @classmethod
    def from_api(cls, data: dict) -> Track:
        user = data.get("user") or {}
        return cls(
            id=int(data["id"]),
            title=str(data.get("title") or "—"),
            artist=str(user.get("username") or data.get("publisher_metadata", {}).get("artist") or "Unknown"),
            duration_ms=int(data.get("duration") or 0),
            permalink_url=str(data.get("permalink_url") or ""),
            artwork_url=data.get("artwork_url") or user.get("avatar_url"),
            waveform_url=data.get("waveform_url"),
            genre=str(data.get("genre") or ""),
            raw=data,
        )


class SoundCloudError(RuntimeError):
    pass


class SoundCloudClient:
    """Thread-safe SoundCloud API client.

    Extracts a fresh client_id on first call by scraping soundcloud.com's
    main JS bundle. Caches it for the lifetime of the process.
    """

    def __init__(self, cache_path: Path | None = None) -> None:
        self._client_id: str | None = None
        self._lock = threading.Lock()
        self._cache_path = cache_path

    # ---------- bootstrap ----------
    def _http(
        self,
        url: str,
        params: dict | None = None,
        timeout: float = 15.0,
    ) -> bytes:
        if params:
            sep = "&" if "?" in url else "?"
            url = url + sep + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            return resp.read()

    def _http_json(self, url: str, params: dict | None = None, timeout: float = 15.0) -> dict:
        body = self._http(url, params=params, timeout=timeout)
        try:
            return json.loads(body.decode("utf-8"))
        except json.JSONDecodeError as e:
            raise SoundCloudError(f"Bad JSON from {url[:80]}…: {e}") from e

    def _extract_client_id(self) -> str:
        """Scrape a fresh client_id from the SoundCloud homepage's JS bundles.

        Strategy:
        1. Download soundcloud.com homepage HTML.
        2. Find every <script src="https://a-v2.sndcdn.com/assets/...js">.
        3. Download each and grep ``client_id:"<id>"``.
        4. Return the first match.
        """
        log.debug("Extracting SoundCloud client_id…")
        html = self._http(HOME).decode("utf-8", errors="replace")
        scripts = re.findall(
            r'<script[^>]+src="(https://a-v2\.sndcdn\.com/assets/[^"]+\.js)"', html
        )
        if not scripts:
            scripts = re.findall(
                r'src="(https://[a-z0-9.-]+\.sndcdn\.com/assets/[^"]+\.js)"', html
            )
        # Iterate from last (main bundle is usually last).
        for url in reversed(scripts):
            try:
                body = self._http(url, timeout=10).decode("utf-8", errors="replace")
            except Exception as e:  # noqa: BLE001
                log.debug("  skip %s: %s", url, e)
                continue
            m = re.search(r'client_id\s*[:=]\s*"([0-9a-zA-Z]{16,})"', body)
            if m:
                cid = m.group(1)
                log.debug("  found client_id=%s in %s", cid, url)
                return cid
        raise SoundCloudError("Could not extract client_id from soundcloud.com")

    @property
    def client_id(self) -> str:
        if self._client_id:
            return self._client_id
        with self._lock:
            if self._client_id:
                return self._client_id
            # Try cached file first.
            if self._cache_path and self._cache_path.exists():
                try:
                    cached = json.loads(self._cache_path.read_text(encoding="utf-8"))
                    cid = cached.get("client_id")
                    saved_at = float(cached.get("saved_at") or 0)
                    if cid and time.time() - saved_at < 24 * 3600:
                        self._client_id = cid
                        return cid
                except Exception:  # noqa: BLE001
                    pass
            # Try live extraction.
            try:
                cid = self._extract_client_id()
                self._client_id = cid
                if self._cache_path:
                    try:
                        self._cache_path.parent.mkdir(parents=True, exist_ok=True)
                        self._cache_path.write_text(
                            json.dumps({"client_id": cid, "saved_at": time.time()}),
                            encoding="utf-8",
                        )
                    except Exception:  # noqa: BLE001
                        pass
                return cid
            except Exception as e:  # noqa: BLE001
                log.warning("Live client_id extraction failed: %s; trying fallbacks", e)
            # Final fallback: hardcoded ids (random order so we don't always burn the same one).
            for cid in random.sample(FALLBACK_CLIENT_IDS, len(FALLBACK_CLIENT_IDS)):
                # quick health check
                try:
                    self._http_json(
                        f"{API}/tracks/293", params={"client_id": cid}, timeout=8
                    )
                except Exception:  # noqa: BLE001
                    continue
                self._client_id = cid
                return cid
            raise SoundCloudError(
                "Could not obtain SoundCloud client_id — neither live extraction nor fallbacks worked"
            )

    def invalidate(self) -> None:
        """Drop cached client_id (call on 401/403)."""
        with self._lock:
            self._client_id = None
            if self._cache_path and self._cache_path.exists():
                try:
                    self._cache_path.unlink()
                except Exception:  # noqa: BLE001
                    pass

    # ---------- API calls ----------
    def _api_json(self, path: str, params: dict | None = None, timeout: float = 15.0) -> dict:
        params = dict(params or {})
        params["client_id"] = self.client_id
        try:
            return self._http_json(f"{API}{path}", params=params, timeout=timeout)
        except urllib.error.HTTPError as e:
            if e.code in (401, 403):
                # client_id probably burnt; try one more time with fresh id.
                self.invalidate()
                params["client_id"] = self.client_id
                return self._http_json(f"{API}{path}", params=params, timeout=timeout)
            raise

    def search(self, query: str, limit: int = 20) -> list[Track]:
        if not query.strip():
            return []
        data = self._api_json(
            "/search/tracks",
            params={"q": query.strip(), "limit": limit, "offset": 0, "linked_partitioning": 1},
        )
        return [Track.from_api(t) for t in (data.get("collection") or []) if t.get("kind") == "track"]

    def charts(self, limit: int = 50) -> list[Track]:
        """Trending tracks across all genres on SoundCloud.

        SoundCloud's public API only exposes ``kind=trending`` for the
        ``all-music`` genre right now (other ``kind=top`` / per-genre
        endpoints return 404 in 2025). For genre-specific exploration use
        :meth:`search` with the genre name.
        """
        data = self._api_json(
            "/charts",
            params={
                "kind": "trending",
                "genre": "soundcloud:genres:all-music",
                "limit": limit,
                "offset": 0,
                "linked_partitioning": 1,
            },
        )
        out: list[Track] = []
        for entry in data.get("collection") or []:
            track_data = entry.get("track")
            if track_data:
                out.append(Track.from_api(track_data))
        return out

    def selections(self) -> list[dict]:
        """Curated discovery selections (mixes by mood / 'Buzzing' artists / …).

        Returns the raw selection dicts; each has an ``items`` array of
        playlist refs and a localized ``title``.
        """
        data = self._api_json("/mixed-selections", params={"variant_ids": ""})
        return data.get("collection") or []

    def related(self, track_id: int, limit: int = 20) -> list[Track]:
        data = self._api_json(
            f"/tracks/{int(track_id)}/related",
            params={"limit": limit, "offset": 0, "linked_partitioning": 1},
        )
        return [Track.from_api(t) for t in (data.get("collection") or []) if t.get("kind") == "track"]

    def track(self, track_id: int) -> Track:
        return Track.from_api(self._api_json(f"/tracks/{int(track_id)}"))

    def stream_url(self, track: Track) -> str:
        """Resolve a playable HTTP URL for libmpv.

        SoundCloud puts ``transcodings`` inside ``track.media``; we pick the
        progressive MP3 if available (single GET, easy to seek), falling back
        to HLS otherwise.
        """
        media = (track.raw.get("media") or {}).get("transcodings") or []
        if not media:
            # Re-fetch the track in case the search response was abridged.
            full = self.track(track.id)
            media = (full.raw.get("media") or {}).get("transcodings") or []
        if not media:
            raise SoundCloudError(f"No transcodings for track {track.id}")

        def score(t: dict) -> int:
            fmt = (t.get("format") or {}).get("protocol", "")
            mime = (t.get("format") or {}).get("mime_type", "")
            quality = t.get("quality") or ""
            s = 0
            if fmt == "progressive":
                s += 100
            if "audio/mpeg" in mime or "mp3" in mime.lower():
                s += 50
            if quality == "hq":
                s += 200
            return s

        media.sort(key=score, reverse=True)
        chosen = media[0]
        resolved = self._api_json(chosen["url"].replace(API, ""))
        url = resolved.get("url")
        if not url:
            raise SoundCloudError(f"Empty stream url for track {track.id}")
        return str(url)
