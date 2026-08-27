"""Is this file actually the image it claims to be?

Written after eight housing images shipped as unreadable bytes with an
image extension. The test guarding them asked whether the file existed,
which it did, so the suite stayed green while every property on the page
rendered as a broken-image icon.

The checks read each format's header rather than decoding anything, so
they need no imaging library -- this project deliberately ships two
dependencies and neither of them is one.
"""

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
RIFF_SIGNATURE = b"RIFF"
WEBP_TAG = b"WEBP"

_PNG_HEADER_BYTES = 24
_WEBP_HEADER_BYTES = 12


def _read(path, count):
    try:
        with open(path, "rb") as handle:
            return handle.read(count)
    except OSError:
        return b""


def png_dimensions(data_or_path):
    """A PNG's width and height, or None if it is not one.

    The first chunk of a PNG is always IHDR and it carries the
    dimensions, so reading it rules out a file that opens with the
    signature and is damaged immediately after.
    """
    header = _read(data_or_path, _PNG_HEADER_BYTES)

    if len(header) < _PNG_HEADER_BYTES:
        return None

    if not header.startswith(PNG_SIGNATURE):
        return None

    if header[12:16] != b"IHDR":
        return None

    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")

    if width < 1 or height < 1:
        return None

    return width, height


def is_png(path):
    return png_dimensions(path) is not None


def is_webp(path):
    """Whether this is a WebP, checked through its RIFF container.

    WebP keeps its dimensions in a chunk whose layout depends on which
    of three encodings was used, which is more than this needs to know.
    The container declares its own length instead, and a file whose
    declared length disagrees with the bytes on disk is truncated or was
    never a WebP.
    """
    header = _read(path, _WEBP_HEADER_BYTES)

    if len(header) < _WEBP_HEADER_BYTES:
        return None

    if not header.startswith(RIFF_SIGNATURE):
        return False

    if header[8:12] != WEBP_TAG:
        return False

    declared = int.from_bytes(header[4:8], "little")

    try:
        import os

        actual = os.path.getsize(path)
    except OSError:
        return False

    # The RIFF size counts everything after the first eight bytes.
    return declared == actual - 8


def is_renderable_image(path):
    """Whether a browser will be able to draw this file.

    Covers the two formats this project ships: PNG for flat artwork and
    icons, WebP for photographs.
    """
    return bool(is_png(path)) or bool(is_webp(path))
