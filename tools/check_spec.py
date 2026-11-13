#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 aiingjie
"""Check a C17 icon pack against icon pack spec 3.1 (docs/ICON-PACK-SPEC.zh-CN.md).

Standalone: Python 3.9+ standard library only (Pillow, when installed, is used for interlaced PNG files). It needs no
module classes and never runs code from the pack. For every icon it reads the canvas (VectorDrawable viewport or PNG
size) and the glyph box (VectorDrawable path geometry including strokes, clip paths and group transforms; PNG pixels
with alpha > 0), places the icon in the system icon box the way the module draws it, and compares it with the
reference canvas and system glyph size of its role (docs/icon-spec/role-canvases.json):

  fit      measured roles must be marked "fit": "canvas"
  aspect   canvas aspect of a canvas-fit icon within 5% of the reference canvas
  outside  glyph inside its canvas
  size     displayed glyph within 25% of the system glyph (status bar by height, others by area)
  states   all states of one icon placed at one scale

  python tools/check_spec.py <pack.zip> [more.zip ...] [--json report.json] [--all] [--roles role-canvases.json]

Exit status: 0 conforms, 1 problems listed, 2 the check could not run. This is a geometry preflight: run
tools/validate_pack.py for the format and safety rules; neither replaces the module's import or a look on the phone.
"""
from __future__ import annotations

import argparse
import collections
import json
import math
import re
import struct
import sys
import xml.etree.ElementTree as ET
import zipfile
import zlib
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
ROLE_TABLE = ROOT / "docs/icon-spec/role-canvases.json"
ASPECT_TOLERANCE = 0.05
SIZE_TOLERANCE = 0.25
STATE_TOLERANCE = 0.02
RASTER = 192                        # decode size of the module's spec check
OUTSIDE_TOLERANCE = 1 / 96          # of the longer canvas side, about one pixel of a 96 px icon
STATUS_BAR_SCOPES = ("hint", "wifi", "cellular", "battery")
LEVEL_FAMILIES = ("wifi", "cellular")
LEVELS = ("0", "1", "2", "3", "4")
SHARED_CANVAS = re.compile(r"cellular\.stacked_(?:primary|secondary)\.")   # two rows on one 19 x 16 canvas
MAX_ASSET = 1024 * 1024
A = "{http://schemas.android.com/apk/res/android}"

PROBLEMS = collections.OrderedDict([
    ("decode", "无法读取或没有可见图形"),
    ("fit", "未写 \"fit\": \"canvas\"（按旧规则裁边撑满）"),
    ("aspect", "画布比例与参考画布相差超过 5%"),
    ("outside", "图形超出画布"),
    ("size", "显示大小与系统图标相差超过 25%"),
    ("states", "同一图标各状态的缩放不一致"),
])
SHORT = {"decode": "读取", "fit": "未写fit", "aspect": "画布比例", "outside": "超出画布", "size": "大小", "states": "状态"}


class PackError(Exception):
    """The pack cannot be read at all."""


def read_pack(path: Path):
    """manifest dict and a reader for its files; the manifest may sit in one outer folder."""
    with zipfile.ZipFile(path) as archive:
        names = [i.filename for i in archive.infolist() if not i.is_dir()]
        manifests = [n for n in names if n.rsplit("/", 1)[-1] == "manifest.json" and n.count("/") <= 1]
        if len(manifests) != 1:
            raise PackError("需要恰好一个 manifest.json（根目录或一层文件夹里）")
        prefix = manifests[0][:-len("manifest.json")]
        files = {}
        for info in archive.infolist():
            if info.is_dir() or not info.filename.startswith(prefix):
                continue
            if info.file_size > MAX_ASSET + 256 * 1024:
                raise PackError("文件过大：" + info.filename)
            files[info.filename[len(prefix):]] = archive.read(info)

    def unique(pairs):
        out = {}
        for key, value in pairs:
            if key in out:
                raise PackError("manifest.json 有重复的键：" + key)
            out[key] = value
        return out
    try:
        manifest = json.loads(files["manifest.json"].decode("utf-8"), object_pairs_hook=unique)
    except (UnicodeDecodeError, json.JSONDecodeError) as failure:
        raise PackError("manifest.json 不是有效的 JSON：" + str(failure)) from None
    if not isinstance(manifest, dict) or not isinstance(manifest.get("icons"), dict):
        raise PackError("manifest.json 缺少 icons")
    return manifest, files


# ---------------------------------------------------------------- PNG

def png_measure(data: bytes):
    """(width, height), alpha > 0 box (left, top, right, bottom) in pixels or None."""
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("不是 PNG")
    pos, chunks, idat = 8, {}, []
    while pos + 8 <= len(data):
        length, kind = struct.unpack(">I4s", data[pos:pos + 8])
        body = data[pos + 8:pos + 8 + length]
        if kind == b"IDAT":
            idat.append(body)
        else:
            chunks.setdefault(kind, body)
        pos += 12 + length
        if kind == b"IEND":
            break
    width, height, depth, color, _, _, interlace = struct.unpack(">IIBBBBB", chunks[b"IHDR"])
    channels = {0: 1, 2: 3, 3: 1, 4: 2, 6: 4}[color]
    if interlace or depth not in (8, 16) and not (color == 3 and depth in (1, 2, 4)):
        return (width, height), _png_alpha_box_pillow(data)
    raw = zlib.decompress(b"".join(idat))
    bits = channels * depth
    stride, step = (width * bits + 7) // 8, max(1, bits // 8)
    trns = chunks.get(b"tRNS")
    rows, previous, offset = [], bytearray(stride), 0
    for _ in range(height):
        kind, line = raw[offset], bytearray(raw[offset + 1:offset + 1 + stride])
        offset += 1 + stride
        for i in range(stride):
            left = line[i - step] if i >= step else 0
            up, corner = previous[i], previous[i - step] if i >= step else 0
            if kind == 1: line[i] = (line[i] + left) & 255
            elif kind == 2: line[i] = (line[i] + up) & 255
            elif kind == 3: line[i] = (line[i] + (left + up) // 2) & 255
            elif kind == 4:
                p = left + up - corner
                pa, pb, pc = abs(p - left), abs(p - up), abs(p - corner)
                line[i] = (line[i] + (left if pa <= pb and pa <= pc else up if pb <= pc else corner)) & 255
        rows.append(bytes(line))
        previous = line
    box = None
    for y, line in enumerate(rows):
        alpha = _row_alpha(line, width, color, depth, trns)
        first = len(alpha) - len(alpha.lstrip(b"\x00"))
        if first < len(alpha):
            last = len(alpha.rstrip(b"\x00"))
            box = (first, y, last, y + 1) if box is None else (min(box[0], first), box[1], max(box[2], last), y + 1)
    return (width, height), box


def _row_alpha(line: bytes, width: int, color: int, depth: int, trns) -> bytes:
    """One byte per pixel, zero where the pixel is fully transparent."""
    if color == 3:
        if depth < 8:
            per, mask = 8 // depth, (1 << depth) - 1
            line = bytes((line[x // per] >> (8 - depth * (x % per + 1))) & mask for x in range(width))
        table = bytes((trns[i] if trns and i < len(trns) else 255) for i in range(256))
        return line[:width].translate(table)
    size = depth // 8
    channels = {0: 1, 2: 3, 4: 2, 6: 4}[color]
    if color in (4, 6):
        parts = [line[(channels - 1) * size + k::channels * size] for k in range(size)]
        return parts[0] if size == 1 else bytes(a | b for a, b in zip(*parts))
    if not trns:
        return b"\xff" * width
    key = trns if size == 2 else bytes(trns[1::2])
    pixel = channels * size
    return bytes(0 if line[x * pixel:(x + 1) * pixel] == key else 255 for x in range(width))


def _png_alpha_box_pillow(data):
    try:
        from PIL import Image
        import io
    except ImportError:
        return "unsupported"
    with Image.open(io.BytesIO(data)) as image:
        return image.convert("RGBA").getchannel("A").getbbox()


# ---------------------------------------------------------------- VectorDrawable

_TOKEN = re.compile(r"\s*,?\s*([-+]?(?:\d+\.?\d*|\.\d+)(?:[eE][-+]?\d+)?)")


def _number(text, pos):
    match = _TOKEN.match(text, pos)
    if not match:
        raise ValueError("pathData 数字无效：" + text[pos:pos + 20])
    return float(match.group(1)), match.end()


def _flag(text, pos):
    while pos < len(text) and text[pos] in " ,\t\r\n":
        pos += 1
    if pos >= len(text) or text[pos] not in "01":
        raise ValueError("pathData 弧线标志无效")
    return text[pos] == "1", pos + 1


def path_points(data: str):
    """Points on the outline of an SVG/VectorDrawable path (curves and arcs sampled)."""
    points, pos, command = [], 0, None
    x = y = sx = sy = 0.0
    last_control, n = None, len(data)
    arity = {"M": 2, "L": 2, "H": 1, "V": 1, "C": 6, "S": 4, "Q": 4, "T": 2, "A": 7, "Z": 0}
    while True:
        while pos < n and data[pos] in " ,\t\r\n":
            pos += 1
        if pos >= n:
            return points
        if data[pos].upper() in arity:
            command, pos = data[pos], pos + 1
        elif command is None or command.upper() == "Z":
            raise ValueError("pathData 命令无效：" + data[pos:pos + 20])
        upper, rel = command.upper(), command.islower()
        if upper == "Z":
            x, y, last_control = sx, sy, None
            continue
        args = []
        for i in range(arity[upper]):
            if upper == "A" and i in (3, 4):
                value, pos = _flag(data, pos)
            else:
                value, pos = _number(data, pos)
            args.append(value)
        ox, oy = (x, y) if rel else (0.0, 0.0)
        if upper == "M":
            x, y = args[0] + ox, args[1] + oy
            sx, sy, command = x, y, ("l" if rel else "L")
            points.append((x, y)); last_control = None; continue
        if upper in ("L", "H", "V"):
            x = args[0] + ox if upper in ("L", "H") else x
            y = (args[1] if upper == "L" else args[0]) + oy if upper in ("L", "V") else y
            points.append((x, y)); last_control = None; continue
        if upper in ("C", "S", "Q", "T"):
            if upper == "C":
                c1, c2, end = (args[0] + ox, args[1] + oy), (args[2] + ox, args[3] + oy), (args[4] + ox, args[5] + oy)
            elif upper == "S":
                c1 = (2 * x - last_control[0], 2 * y - last_control[1]) if last_control and last_control[2] == "C" else (x, y)
                c2, end = (args[0] + ox, args[1] + oy), (args[2] + ox, args[3] + oy)
            elif upper == "Q":
                q, end = (args[0] + ox, args[1] + oy), (args[2] + ox, args[3] + oy)
            else:
                q = (2 * x - last_control[0], 2 * y - last_control[1]) if last_control and last_control[2] == "Q" else (x, y)
                end = (args[0] + ox, args[1] + oy)
            for k in range(1, 25):
                t, u = k / 24, 1 - k / 24
                if upper in ("C", "S"):
                    points.append((u**3 * x + 3 * u * u * t * c1[0] + 3 * u * t * t * c2[0] + t**3 * end[0],
                                   u**3 * y + 3 * u * u * t * c1[1] + 3 * u * t * t * c2[1] + t**3 * end[1]))
                else:
                    points.append((u * u * x + 2 * u * t * q[0] + t * t * end[0], u * u * y + 2 * u * t * q[1] + t * t * end[1]))
            last_control = (c2[0], c2[1], "C") if upper in ("C", "S") else (q[0], q[1], "Q")
            x, y = end
            continue
        rx, ry, rotation, large, sweep = abs(args[0]), abs(args[1]), math.radians(args[2]), args[3], args[4]
        end = (args[5] + ox, args[6] + oy)
        points.extend(_arc(x, y, rx, ry, rotation, large, sweep, end))
        x, y = end
        last_control = None


def _arc(x1, y1, rx, ry, phi, large, sweep, end):
    """SVG endpoint arc sampled (SVG 1.1 implementation notes F.6.5)."""
    x2, y2 = end
    if rx == 0 or ry == 0 or (x1, y1) == (x2, y2):
        return [end]
    cos, sin = math.cos(phi), math.sin(phi)
    dx, dy = (x1 - x2) / 2, (y1 - y2) / 2
    xp, yp = cos * dx + sin * dy, -sin * dx + cos * dy
    scale = (xp * xp) / (rx * rx) + (yp * yp) / (ry * ry)
    if scale > 1:
        rx, ry = rx * math.sqrt(scale), ry * math.sqrt(scale)
    num = rx * rx * ry * ry - rx * rx * yp * yp - ry * ry * xp * xp
    root = math.sqrt(max(0.0, num / (rx * rx * yp * yp + ry * ry * xp * xp)))
    if large == sweep:
        root = -root
    cxp, cyp = root * rx * yp / ry, -root * ry * xp / rx
    cx, cy = cos * cxp - sin * cyp + (x1 + x2) / 2, sin * cxp + cos * cyp + (y1 + y2) / 2
    start = math.atan2((yp - cyp) / ry, (xp - cxp) / rx)
    delta = math.atan2((-yp - cyp) / ry, (-xp - cxp) / rx) - start
    if sweep and delta < 0:
        delta += 2 * math.pi
    elif not sweep and delta > 0:
        delta -= 2 * math.pi
    out = []
    for k in range(1, 33):
        angle = start + delta * k / 32
        px, py = rx * math.cos(angle), ry * math.sin(angle)
        out.append((cos * px - sin * py + cx, sin * px + cos * py + cy))
    return out


def _alpha(color):
    """Alpha 0-255 of an android color attribute (#RGB, #ARGB, #RRGGBB, #AARRGGBB); None when absent."""
    if color is None:
        return None
    text = color.strip()
    if not re.fullmatch(r"#[0-9A-Fa-f]{3,8}", text) or len(text) not in (4, 5, 7, 9):
        raise ValueError("颜色只能直接写 #AARRGGBB 等：" + text)
    return int(text[1] * 2, 16) if len(text) == 5 else int(text[1:3], 16) if len(text) == 9 else 255


def _mul(m, n):
    a, b, c, d, e, f = m
    p, q, r, s, t, u = n
    return (a * p + c * q, b * p + d * q, a * r + c * s, b * r + d * s, a * t + c * u + e, b * t + d * u + f)


def _group_matrix(node):
    get = lambda key, default: float(node.get(A + key, default))  # noqa: E731
    px, py, sx, sy = get("pivotX", 0), get("pivotY", 0), get("scaleX", 1), get("scaleY", 1)
    angle = math.radians(get("rotation", 0))
    cos, sin = math.cos(angle), math.sin(angle)
    m = (1, 0, 0, 1, -px, -py)
    m = _mul((sx, 0, 0, sy, 0, 0), m)
    m = _mul((cos, sin, -sin, cos, 0, 0), m)
    return _mul((1, 0, 0, 1, get("translateX", 0) + px, get("translateY", 0) + py), m)


def _box(points, m, grow=0.0):
    xs = [m[0] * x + m[2] * y + m[4] for x, y in points]
    ys = [m[1] * x + m[3] * y + m[5] for x, y in points]
    return (min(xs) - grow, min(ys) - grow, max(xs) + grow, max(ys) + grow) if xs else None


def _meet(a, b):
    """Intersection of two boxes; () when nothing is left."""
    if not a or not b:
        return ()
    box = (max(a[0], b[0]), max(a[1], b[1]), min(a[2], b[2]), min(a[3], b[3]))
    return box if box[0] < box[2] and box[1] < box[3] else ()


def _join(a, b):
    if not a:
        return b or a
    if not b:
        return a
    return (min(a[0], b[0]), min(a[1], b[1]), max(a[2], b[2]), max(a[3], b[3]))


def vector_measure(data: bytes):
    """(viewport width, height), glyph box in viewport units or None."""
    if re.search(rb"<!(?:DOCTYPE|ENTITY)", data):
        raise ValueError("XML 不能含 DOCTYPE 或实体")
    root = ET.fromstring(data)
    if root.tag != "vector":
        raise ValueError("根节点必须是 <vector>")
    canvas = (float(root.get(A + "viewportWidth")), float(root.get(A + "viewportHeight")))
    if canvas[0] <= 0 or canvas[1] <= 0:
        raise ValueError("viewport 无效")
    if float(root.get(A + "alpha", 1)) <= 0:
        return canvas, None

    def walk(node, m, clip):
        ink = None
        for child in node:
            if child.tag == "group":
                ink = _join(ink, walk(child, _mul(m, _group_matrix(child)), clip))
            elif child.tag == "clip-path":
                region = _box(path_points(child.get(A + "pathData", "")), m) or ()
                clip = region if clip is None else _meet(clip, region)
            elif child.tag == "path":
                points = path_points(child.get(A + "pathData", ""))
                fill = (_alpha(child.get(A + "fillColor")) or 0) * float(child.get(A + "fillAlpha", 1)) > 0
                width = float(child.get(A + "strokeWidth", 0))
                stroke = (_alpha(child.get(A + "strokeColor")) or 0) * float(child.get(A + "strokeAlpha", 1)) > 0 and width > 0
                if not points or not (fill or stroke):
                    continue
                box = _box(points, m, width / 2 * math.sqrt(abs(m[0] * m[3] - m[1] * m[2])) if stroke else 0.0)
                box = box if clip is None else _meet(box, clip)
                ink = _join(ink, box)
            else:
                raise ValueError("不支持的节点：" + child.tag)
        return ink
    ink = walk(root, (1, 0, 0, 1, 0, 0), None)
    if not ink:
        return canvas, None
    # The module finds the glyph box on a raster decode (192 px, alpha > 0), which takes in the partly covered pixels
    # at the edges: half a pixel more on each side than the exact geometry.
    pad = 0.5 * max(canvas) / RASTER
    return canvas, (ink[0] - pad, ink[1] - pad, ink[2] + pad, ink[3] + pad)


# ---------------------------------------------------------------- spec 3.1 rules

def measure(manifest, files):
    """One row per icon: role, fit, canvas and glyph box in canvas units (or the reason it could not be read)."""
    items = []
    for role, asset in manifest["icons"].items():
        item = {"role": role, "source": asset.get("source"), "fit": "canvas" if asset.get("fit") == "canvas" else "visible"}
        items.append(item)
        try:
            data = files[asset["source"]]
            if asset["source"].endswith(".xml"):
                item["canvas"], ink = vector_measure(data)
            elif asset["source"].endswith(".png"):
                item["canvas"], ink = png_measure(data)
                if ink == "unsupported":
                    item["error"] = "隔行扫描 PNG 需要安装 Pillow 才能读取像素"
                    continue
            else:
                raise ValueError("只支持 PNG 和 VectorDrawable XML")
            if ink:
                item["ink"] = [round(v, 4) for v in ink]
        except (KeyError, ValueError, TypeError, ET.ParseError, struct.error, zlib.error) as failure:
            item["error"] = "%s：%s" % (type(failure).__name__, failure)
    return items


def _level(row):
    return row["target"] in LEVEL_FAMILIES and row["role"].rsplit(".", 1)[-1] in LEVELS


def analyse(items, table):
    rows = []
    for item in items:
        ref = table.get(item["role"])
        row = {"role": item["role"], "fit": item["fit"], "source": item["source"], "problems": [], "detail": {},
               "scope": ref["scope"] if ref else item["role"].split(".")[0],
               "target": ref["target"] if ref else item["role"].rsplit(".", 1)[0],
               "reference": ref["from"] if ref else None, "measured": bool(ref) and ref["from"].startswith("system:")}
        if ref:
            row["referenceCanvas"] = ref["canvas"]
        row.update({k: item[k] for k in ("canvas", "ink") if k in item})
        rows.append(row)
    # Module rule for Wi-Fi/cellular levels 0-4 without fit: one crop over the levels drawn on the same canvas.
    unions = {}
    for row in rows:
        if _level(row) and row["fit"] == "visible" and "ink" in row:
            peers = [p["ink"] for p in rows if p["target"] == row["target"] and _level(p) and p["fit"] == "visible"
                     and "ink" in p and p["canvas"] == row["canvas"]]
            unions[row["role"]] = (min(b[0] for b in peers), min(b[1] for b in peers), max(b[2] for b in peers), max(b[3] for b in peers))
    for row in rows:
        canvas, ref = row.get("canvas"), row.get("referenceCanvas")
        aspect_off = (canvas and ref and row["measured"] and row["fit"] == "canvas"
                      and abs((canvas[0] / canvas[1]) / (ref[0] / ref[1]) - 1) > ASPECT_TOLERANCE)
        if aspect_off:
            row["problems"].append("aspect")
            row["detail"]["aspect"] = "画布 %s × %s，参考 %s × %s" % (_num(canvas[0] / canvas[1] * ref[1]), _num(ref[1]), _num(ref[0]), _num(ref[1]))
        if "ink" not in row:
            row["problems"].append("decode")
            item = next(i for i in items if i["role"] == row["role"])
            row["detail"]["decode"] = item.get("error", "没有可见图形")
            continue
        if row["fit"] != "canvas" and row["measured"]:
            row["problems"].append("fit")
        (cw, ch), (left, top, right, bottom) = canvas, row["ink"]
        slack = OUTSIDE_TOLERANCE * max(cw, ch)
        if left < -slack or top < -slack or right > cw + slack or bottom > ch + slack:
            row["problems"].append("outside")
            row["detail"]["outside"] = "图形 %s, %s – %s, %s，画布 %s × %s" % tuple(_num(v, 2) for v in (left, top, right, bottom, cw, ch))
        if not ref:
            continue
        rw, rh = ref
        if row["fit"] == "canvas" or SHARED_CANVAS.match(row["role"]):
            frame = (cw, ch)
        elif row["role"] in unions:
            u = unions[row["role"]]
            frame = (u[2] - u[0], u[3] - u[1])
        else:
            frame = (right - left, bottom - top)
        scale = min(rw / frame[0], rh / frame[1])
        sw, sh = (right - left) * scale / rw, (bottom - top) * scale / rh
        row["shown"] = {"width": round(sw, 3), "height": round(sh, 3), "area": round(math.sqrt(sw * sh), 3), "longest": round(max(sw, sh), 3)}
        row["boxHeightShare"] = round(min(1.0, (rw / rh) / (cw / ch)), 4)
        system = table[row["role"]].get("systemInk")
        if not system:
            continue
        key = "height" if row["scope"] in STATUS_BAR_SCOPES else "area"
        ratio = row["shown"][key] / system[key]
        row["ratio"], row["system"] = round(ratio, 3), system
        capped = key == "area" and ratio < 1 and row["shown"]["longest"] >= system["longest"] * 0.95
        if _level(row):
            row["levelRatio"] = ratio      # only the fullest level is sized: empty bars may be left blank
        elif abs(ratio - 1) > SIZE_TOLERANCE and not capped:
            row["problems"].append("size")
            row["detail"]["size"] = "%s %.2f，系统 %.2f（%s %d%%）" % ("高度" if key == "height" else "面积", row["shown"][key],
                                                              system[key], "大" if ratio > 1 else "小", round(abs(ratio - 1) * 100))
    for family in LEVEL_FAMILIES:
        levels = [r for r in rows if r["target"] == family and "levelRatio" in r]
        full = max(levels, key=lambda r: r["shown"]["height"]) if levels else None
        if full and abs(full["levelRatio"] - 1) > SIZE_TOLERANCE:
            for r in levels:
                r["problems"].append("size")
                r["detail"]["size"] = "最满一档高度 %.2f，系统 %.2f" % (full["shown"]["height"], full["system"]["height"])
    groups = collections.defaultdict(list)
    for row in rows:
        if row["fit"] == "canvas" and "boxHeightShare" in row:
            groups["canvas", row["target"], tuple(row["referenceCanvas"])].append(row)
        elif row["fit"] == "visible" and _level(row) and "canvas" in row:
            groups["visible", row["target"]].append(row)
    for key, group in groups.items():
        if key[0] == "canvas":
            shares = sorted({r["boxHeightShare"] for r in group})
            bad, text = shares[-1] / shares[0] - 1 > STATE_TOLERANCE, "画布占格子高度 " + " / ".join(_num(s, 3) for s in shares)
        else:
            aspects = sorted({round(r["canvas"][0] / r["canvas"][1], 4) for r in group})
            bad, text = len(aspects) > 1, "各档画布比例 " + " / ".join(_num(a, 3) for a in aspects) + "，无法统一裁切"
        if bad:
            for r in group:
                r["problems"].append("states")
                r["detail"]["states"] = key[1] + "：" + text
    return rows


def _num(value, digits=1):
    text = ("%." + str(digits) + "f") % value
    return text.rstrip("0").rstrip(".") if "." in text else text


def print_report(path, manifest, rows, show_all):
    print("图标包：%s（%s，%s），%d 个图标" % (manifest.get("name"), manifest.get("id"), path.name, len(rows)))
    codes = list(PROBLEMS)
    print("  " + " | ".join(["区域", "图标", "canvas", "无实测参考"] + [SHORT[c] for c in codes]))
    scopes = collections.OrderedDict()
    for row in rows:
        scopes.setdefault(row["scope"], []).append(row)
    for scope, group in scopes.items():
        cells = [scope, len(group), sum(r["fit"] == "canvas" for r in group), sum(not r["measured"] for r in group)]
        print("  " + " | ".join(map(str, cells + [sum(c in r["problems"] for r in group) for c in codes])))
    failing = [r for r in rows if r["problems"]]
    if not failing:
        print("全部符合规范 3.1。")
    for code in codes:
        hit = [r for r in rows if code in r["problems"]]
        if hit:
            print("\n[%s] %d 个" % (PROBLEMS[code], len(hit)))
            for r in hit if show_all else hit[:12]:
                print("  " + r["role"] + ("：" + r["detail"][code] if code in r["detail"] else ""))
            if not show_all and len(hit) > 12:
                print("  …… 另有 %d 个（加 --all 列出全部）" % (len(hit) - 12))
    unmeasured = sum(not r["measured"] for r in rows)
    if unmeasured:
        print("\n%d 个图标的角色没有实测的系统画布（参考表里 from 为 default:、未登记的角色或按资源名提供的角色），"
              "只检查了读取、是否超出画布和各状态是否一致；这些角色可以不写 fit。" % unmeasured)
    return len(failing)


def main(argv=None):
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description="按 C17 图标包规范 3.1 检查图标包的画布与大小（不需要模块代码）")
    parser.add_argument("packs", nargs="+", type=Path)
    parser.add_argument("--json", type=Path, help="把逐个图标的结果写成 JSON")
    parser.add_argument("--all", action="store_true", help="列出全部问题图标")
    parser.add_argument("--roles", type=Path, default=ROLE_TABLE, help="参考画布表（默认 docs/icon-spec/role-canvases.json）")
    args = parser.parse_args(argv)
    try:
        table = json.loads(args.roles.read_text("utf-8"))["roles"]
    except (OSError, ValueError, KeyError) as failure:
        print("读不到参考画布表：%s" % failure, file=sys.stderr)
        return 2
    results, failing = [], 0
    for path in args.packs:
        try:
            manifest, files = read_pack(path)
        except (OSError, zipfile.BadZipFile, PackError) as failure:
            print("检查无法运行：%s：%s" % (path, failure), file=sys.stderr)
            return 2
        rows = analyse(measure(manifest, files), table)
        failing += print_report(path, manifest, rows, args.all)
        results.append({"pack": path.name, "id": manifest.get("id"), "name": manifest.get("name"), "icons": rows})
        if len(args.packs) > 1:
            print()
    if args.json:
        args.json.parent.mkdir(parents=True, exist_ok=True)
        args.json.write_text(json.dumps({"spec": "c17-icon-pack 3.1", "packs": results}, ensure_ascii=False, indent=1) + "\n", "utf-8")
    return 1 if failing else 0


if __name__ == "__main__":
    sys.exit(main())
