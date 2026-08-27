"""Is this file actually the image it claims to be?

Written after eight housing PNGs shipped as unreadable bytes with a
`.png` extension. The test guarding them asked whether the file existed,
which it did, so the suite stayed green while every property on the page
rendered as a broken-image icon.

The check reads the signature and the IHDR chunk rather than decoding
anything, so it needs no imaging library -- this project deliberately
ships two dependencies and neither of them is one.
"""

PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
_HEADER_BYTES = 24


def png_dimensions(path):
    """The image's width and height, or None if it is not a PNG.

    None covers every way this can go wrong -- missing, unreadable,
    truncated, or bytes that were never a PNG at all -- because the
    caller wants the same answer in all of them: do not try to show it.
    """
    try:
        with open(path, "rb") as handle:
            header = handle.read(_HEADER_BYTES)
    except OSError:
        return None

    if len(header) < _HEADER_BYTES:
        return None

    if not header.startswith(PNG_SIGNATURE):
        return None

    # The first chunk of a PNG is always IHDR, and it carries the
    # dimensions. Checking it rules out a file that happens to open with
    # the signature but is damaged immediately after.
    if header[12:16] != b"IHDR":
        return None

    width = int.from_bytes(header[16:20], "big")
    height = int.from_bytes(header[20:24], "big")

    if width < 1 or height < 1:
        return None

    return width, height


def is_png(path):
    """Whether a browser will be able to render this file."""
    return png_dimensions(path) is not None
