from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from pathlib import Path
from uuid import uuid4

from fastapi import HTTPException, Request, status
from PIL import Image, ImageOps, UnidentifiedImageError

MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_SOURCE_PIXELS = 40_000_000
MAX_SOURCE_EDGE = 12_000
MAX_FLYER_EDGE = 1_600
SUPPORTED_IMAGE_TYPES = {
    "image/jpeg": ("JPEG", ".jpg"),
    "image/png": ("PNG", ".png"),
    "image/webp": ("WEBP", ".webp"),
}

# Pillow raises before allocating extreme decompression-bomb images.  The
# explicit dimension checks below make the public contract deterministic.
Image.MAX_IMAGE_PIXELS = MAX_SOURCE_PIXELS


@dataclass(frozen=True)
class NormalizedFlyerImage:
    content: bytes
    mime_type: str
    width: int
    height: int
    has_alpha: bool
    digest: str


@dataclass(frozen=True)
class StoredFlyerImage:
    storage_key: str
    source_storage_key: str
    mime_type: str
    size_bytes: int
    width: int
    height: int
    has_alpha: bool


async def read_bounded_image_body(request: Request) -> bytes:
    """Read an upload without buffering an unbounded request body."""
    chunks: list[bytes] = []
    size = 0
    async for chunk in request.stream():
        size += len(chunk)
        if size > MAX_UPLOAD_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="Image must be 10 MiB or smaller.",
            )
        chunks.append(chunk)
    return b"".join(chunks)


def normalize_flyer_image(content: bytes, declared_mime_type: str) -> NormalizedFlyerImage:
    """Decode once and create a deterministic, flyer-safe canonical asset.

    Transparent borders are trimmed because they otherwise make equivalent
    products appear at wildly different visual scales. Opaque photography is
    never cropped. Background removal is intentionally outside this boundary.
    """
    mime_type = declared_mime_type.split(";", 1)[0].strip().lower()
    expected = SUPPORTED_IMAGE_TYPES.get(mime_type)
    if expected is None:
        raise HTTPException(
            status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            detail="Only PNG, JPEG, and WebP images are allowed.",
        )
    if not content:
        raise HTTPException(status_code=422, detail="Image content is empty.")
    if len(content) > MAX_UPLOAD_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            detail="Image must be 10 MiB or smaller.",
        )

    try:
        with Image.open(io.BytesIO(content)) as probe:
            if probe.format != expected[0]:
                raise HTTPException(
                    status_code=422,
                    detail="Image content does not match the declared MIME type.",
                )
            if getattr(probe, "n_frames", 1) != 1:
                raise HTTPException(status_code=422, detail="Animated images are not supported.")
            width, height = probe.size
            if (
                width < 1
                or height < 1
                or width > MAX_SOURCE_EDGE
                or height > MAX_SOURCE_EDGE
                or width * height > MAX_SOURCE_PIXELS
            ):
                raise HTTPException(status_code=422, detail="Image dimensions are too large.")
            probe.verify()

        with Image.open(io.BytesIO(content)) as source:
            source.load()
            image = ImageOps.exif_transpose(source)
            has_alpha = _has_visible_transparency(image)
            if has_alpha:
                image = _trim_transparent_border(image.convert("RGBA"))
            else:
                image = image.convert("RGB")
            image.thumbnail((MAX_FLYER_EDGE, MAX_FLYER_EDGE), Image.Resampling.LANCZOS)

            output = io.BytesIO()
            if has_alpha or mime_type == "image/png":
                if image.mode not in {"RGB", "RGBA"}:
                    image = image.convert("RGBA" if has_alpha else "RGB")
                image.save(output, format="PNG", compress_level=9, optimize=False)
                normalized_mime = "image/png"
            else:
                image.save(
                    output,
                    format="JPEG",
                    quality=92,
                    subsampling=0,
                    optimize=False,
                    progressive=False,
                )
                normalized_mime = "image/jpeg"
    except HTTPException:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise HTTPException(status_code=422, detail="Image dimensions are too large.") from None
    except (UnidentifiedImageError, OSError, SyntaxError, ValueError):
        raise HTTPException(status_code=422, detail="Image content is invalid or corrupt.") from None

    normalized = output.getvalue()
    return NormalizedFlyerImage(
        content=normalized,
        mime_type=normalized_mime,
        width=image.width,
        height=image.height,
        has_alpha=has_alpha,
        digest=hashlib.sha256(normalized).hexdigest(),
    )


def store_flyer_image(
    *,
    namespace: str,
    original_content: bytes,
    declared_mime_type: str,
) -> StoredFlyerImage:
    """Persist immutable source and normalized variants in a server-owned namespace."""
    from app.services.rendering import storage_path_for_key

    normalized = normalize_flyer_image(original_content, declared_mime_type)
    source_extension = SUPPORTED_IMAGE_TYPES[declared_mime_type.split(";", 1)[0].strip().lower()][1]
    normalized_extension = ".png" if normalized.mime_type == "image/png" else ".jpg"
    source_digest = hashlib.sha256(original_content).hexdigest()
    source_key = f"{namespace}/source/{source_digest}{source_extension}"
    flyer_key = f"{namespace}/flyer/{normalized.digest}{normalized_extension}"
    _write_immutable(storage_path_for_key(source_key), original_content)
    _write_immutable(storage_path_for_key(flyer_key), normalized.content)
    return StoredFlyerImage(
        storage_key=flyer_key,
        source_storage_key=source_key,
        mime_type=normalized.mime_type,
        size_bytes=len(normalized.content),
        width=normalized.width,
        height=normalized.height,
        has_alpha=normalized.has_alpha,
    )


def _has_visible_transparency(image: Image.Image) -> bool:
    if image.mode in {"RGBA", "LA"}:
        alpha = image.getchannel("A")
        return alpha.getextrema()[0] < 255
    return image.mode == "P" and "transparency" in image.info


def _trim_transparent_border(image: Image.Image) -> Image.Image:
    alpha = image.getchannel("A")
    bounds = alpha.getbbox()
    if bounds is None:
        raise HTTPException(status_code=422, detail="Image is fully transparent.")
    cropped = image.crop(bounds)
    padding = max(2, round(max(cropped.size) * 0.04))
    canvas = Image.new("RGBA", (cropped.width + padding * 2, cropped.height + padding * 2))
    canvas.alpha_composite(cropped, (padding, padding))
    return canvas


def _write_immutable(path: Path, content: bytes) -> None:
    if path.is_file():
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid4().hex}.tmp")
    try:
        temporary.write_bytes(content)
        temporary.replace(path)
    finally:
        temporary.unlink(missing_ok=True)
