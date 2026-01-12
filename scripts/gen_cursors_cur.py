from __future__ import annotations

from pathlib import Path
import struct

from PIL import Image


def png_to_cur(
    png_path: Path,
    cur_path: Path,
    *,
    size: tuple[int, int] = (64, 64),
    hotspot: tuple[int, int] = (0, 0),
) -> None:
    img = Image.open(png_path).convert("RGBA")
    tmp_ico = cur_path.with_suffix(".ico")
    # In some environments Pillow may emit an empty ICO when using sizes=[...].
    # To keep this robust, write a single-size ICO by resizing explicitly.
    img = img.resize(size, Image.Resampling.LANCZOS)
    img.save(tmp_ico, format="ICO")

    data = bytearray(tmp_ico.read_bytes())
    if len(data) < 6:
        raise ValueError("Invalid ICO")

    reserved, typ, count = struct.unpack_from("<HHH", data, 0)
    if reserved != 0 or typ != 1 or count < 1:
        raise ValueError(f"Unexpected ICO header: reserved={reserved}, type={typ}, count={count}")

    # Set type = 2 (CUR)
    struct.pack_into("<H", data, 2, 2)

    hx, hy = hotspot
    for i in range(count):
        entry_off = 6 + i * 16
        if entry_off + 16 > len(data):
            raise ValueError("ICO truncated")

        # In CUR: replace (planes, bitcount) with hotspot (x,y)
        struct.pack_into("<HH", data, entry_off + 4, hx, hy)

    cur_path.write_bytes(data)
    tmp_ico.unlink(missing_ok=True)


def main() -> int:
    static_dir = Path(__file__).resolve().parents[1] / "src" / "xinling" / "static"

    sizes: tuple[tuple[int, int], ...] = ((64, 64), (48, 48), (32, 32))

    for name in ("miku1", "miku2"):
        png = static_dir / f"{name}.png"

        if not png.exists():
            raise SystemExit(f"Missing: {png}")

        for size in sizes:
            suffix = "" if size == (64, 64) else f"_{size[0]}"
            cur = static_dir / f"{name}{suffix}.cur"
            png_to_cur(png, cur, size=size, hotspot=(0, 0))
            print(f"Wrote: {cur}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())

