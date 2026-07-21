"""Generate RangeBot.ico using only the Python standard library."""

from __future__ import annotations

from pathlib import Path
import struct


SIZE = 64


def _inside_rounded_square(x: int, y: int, radius: int = 13) -> bool:
    if radius <= x < SIZE - radius or radius <= y < SIZE - radius:
        return True
    corner_x = radius if x < radius else SIZE - radius - 1
    corner_y = radius if y < radius else SIZE - radius - 1
    return (x - corner_x) ** 2 + (y - corner_y) ** 2 <= radius**2


def _distance_to_segment(
    x: float,
    y: float,
    start_x: float,
    start_y: float,
    end_x: float,
    end_y: float,
) -> float:
    dx = end_x - start_x
    dy = end_y - start_y
    if dx == 0 and dy == 0:
        return ((x - start_x) ** 2 + (y - start_y) ** 2) ** 0.5
    projection = ((x - start_x) * dx + (y - start_y) * dy) / (dx * dx + dy * dy)
    projection = max(0.0, min(1.0, projection))
    nearest_x = start_x + projection * dx
    nearest_y = start_y + projection * dy
    return ((x - nearest_x) ** 2 + (y - nearest_y) ** 2) ** 0.5


def _is_white_mark(x: int, y: int) -> bool:
    bars = (
        16 <= x <= 21 and 39 <= y <= 49,
        28 <= x <= 33 and 31 <= y <= 49,
        40 <= x <= 45 and 24 <= y <= 49,
    )
    if any(bars):
        return True
    segments = (
        (15, 35, 29, 25),
        (29, 25, 45, 17),
        (45, 17, 40, 17),
        (45, 17, 44, 22),
    )
    return any(
        _distance_to_segment(x, y, start_x, start_y, end_x, end_y) <= 2.0
        for start_x, start_y, end_x, end_y in segments
    )


def _bitmap_data() -> tuple[bytes, bytes]:
    pixels = bytearray()
    mask = bytearray()
    for y in range(SIZE - 1, -1, -1):
        mask_row = bytearray(SIZE // 8)
        for x in range(SIZE):
            if not _inside_rounded_square(x, y):
                pixels.extend((0, 0, 0, 0))
                mask_row[x // 8] |= 1 << (7 - (x % 8))
                continue
            if _is_white_mark(x, y):
                pixels.extend((248, 250, 255, 255))
                continue
            ratio = (x + y) / (2 * (SIZE - 1))
            red = int(45 + 60 * ratio)
            green = int(78 + 24 * ratio)
            blue = int(205 + 35 * ratio)
            pixels.extend((blue, green, red, 255))
        mask.extend(mask_row)
    return bytes(pixels), bytes(mask)


def generate_icon(destination: Path) -> Path:
    """Write a valid 64x64, 32-bit Windows icon and return its absolute path."""
    destination = destination.expanduser().resolve()
    destination.parent.mkdir(parents=True, exist_ok=True)
    pixels, mask = _bitmap_data()
    bitmap_header = struct.pack(
        "<IIIHHIIIIII",
        40,
        SIZE,
        SIZE * 2,
        1,
        32,
        0,
        len(pixels) + len(mask),
        0,
        0,
        0,
        0,
    )
    image = bitmap_header + pixels + mask
    icon_header = struct.pack("<HHH", 0, 1, 1)
    directory_entry = struct.pack(
        "<BBBBHHII",
        SIZE,
        SIZE,
        0,
        0,
        1,
        32,
        len(image),
        len(icon_header) + 16,
    )
    destination.write_bytes(icon_header + directory_entry + image)
    return destination


if __name__ == "__main__":
    print(generate_icon(Path(__file__).with_name("RangeBot.ico")))
