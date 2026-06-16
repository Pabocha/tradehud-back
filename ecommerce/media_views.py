import hashlib
from pathlib import Path
from django.conf import settings
from django.http import Http404, HttpResponseNotModified
from django.utils.http import http_date
from django.views.static import serve as static_serve


def _safe_media_path(path: str) -> Path:
    media_root = Path(settings.MEDIA_ROOT).resolve()
    full_path = (media_root / path).resolve()

    if media_root not in full_path.parents and full_path != media_root:
        raise Http404("Invalid media path")

    if not full_path.exists() or not full_path.is_file():
        raise Http404("Media not found")

    return full_path


def serve_media_with_cache(request, path):
    full_path = _safe_media_path(path)
    stat = full_path.stat()

    # Weak ETag based on size and mtime to support conditional GET in development.
    etag_seed = f"{stat.st_size}:{stat.st_mtime_ns}"
    etag_hash = hashlib.md5(etag_seed.encode(), usedforsecurity=False).hexdigest()
    etag = f'W/"{etag_hash}"'
    last_modified = http_date(stat.st_mtime)

    if_none_match = request.headers.get("If-None-Match")
    if if_none_match and etag in [v.strip() for v in if_none_match.split(",")]:
        response = HttpResponseNotModified()
        response["ETag"] = etag
        response["Last-Modified"] = last_modified
        response["Cache-Control"] = "public, max-age=86400"
        return response

    response = static_serve(request, path, document_root=settings.MEDIA_ROOT, show_indexes=False)
    response["Cache-Control"] = "public, max-age=86400"
    response["ETag"] = etag
    response["Last-Modified"] = last_modified
    return response
