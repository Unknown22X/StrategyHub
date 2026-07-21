import importlib.util
from pathlib import Path
import struct


ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "rangebot_icon_generator", ROOT / "deploy" / "generate_icon.py"
)
assert SPEC is not None and SPEC.loader is not None
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


def test_generated_icon_is_a_single_64_pixel_32_bit_windows_icon(tmp_path) -> None:
    destination = MODULE.generate_icon(tmp_path / "RangeBot.ico")
    payload = destination.read_bytes()

    reserved, icon_type, count = struct.unpack_from("<HHH", payload, 0)
    width, height, colors, entry_reserved, planes, bits, size, offset = struct.unpack_from(
        "<BBBBHHII", payload, 6
    )

    assert (reserved, icon_type, count) == (0, 1, 1)
    assert (width, height) == (MODULE.SIZE, MODULE.SIZE)
    assert (colors, entry_reserved, planes, bits) == (0, 0, 1, 32)
    assert offset == 22
    assert size == len(payload) - offset
    assert len(payload) > MODULE.SIZE * MODULE.SIZE * 4
