#!/usr/bin/env python3
# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 aiingjie
"""Build the original C17示例库 family. No downloaded or traced artwork.

VectorDrawable and transparent PNG use the same path primitives. roles.json
is an exported production Registry snapshot; unknown new targets fail the
build rather than receiving a generic placeholder. Pillow is the only Python
dependency. Desktop validation never replaces Android production admission.
"""
from __future__ import annotations

import argparse
import hashlib
import io
import json
import math
from pathlib import Path
import zipfile
from dataclasses import dataclass
from PIL import Image, ImageDraw, ImageFont

ROOT = Path(__file__).resolve().parents[1]
WHITE = "#FFFFFFFF"
KAPPA = 0.5522847498
LICENSE = """SPDX-License-Identifier: GPL-3.0-only
Copyright (C) 2026 aiingjie

C17示例库 is original artwork made from the geometric source in
tools/generate_original.py. It contains no Apple, OEM,
PUI, SF Symbols, downloaded icon set, or traced image assets.

The artwork and generator are licensed under GNU General Public License,
version 3 only. The full license is available in LICENSES/GPL-3.0-only.txt:
https://www.gnu.org/licenses/gpl-3.0.txt
"""
LICENSE += "\n" + (ROOT / "LICENSES/GPL-3.0-only.txt").read_text("utf-8")


def fmt(value: float) -> str:
    return f"{value:.4f}".rstrip("0").rstrip(".") or "0"


@dataclass
class Shape:
    commands: list
    fill: bool = False
    width: float = 1.8

    def data(self) -> str:
        return " ".join(command + (" " + " ".join(fmt(v) for v in values) if values else "")
                        for command, values in self.commands)

    def xml(self) -> str:
        style = f'android:fillColor="{WHITE if self.fill else "#00000000"}"'
        if not self.fill:
            style += f' android:strokeColor="{WHITE}" android:strokeWidth="{fmt(self.width)}" android:strokeLineCap="round" android:strokeLineJoin="round"'
        return f'    <path {style} android:pathData="{self.data()}" />'

    def transformed(self, scale: float, dx: float, dy: float) -> "Shape":
        commands = []
        for command, values in self.commands:
            commands.append((command, tuple(value * scale + (dx if index % 2 == 0 else dy)
                                             for index, value in enumerate(values))))
        return Shape(commands, self.fill, self.width * scale)

    def paths(self):
        """Bezier vertices/tangents, also the source for PNG sampling and Lottie."""
        points, ins, outs = [], [], []
        for command, values in self.commands:
            if command == "M":
                if points:
                    yield points, ins, outs, False
                points, ins, outs = [tuple(values)], [(0, 0)], [(0, 0)]
            elif command == "L":
                points.append(tuple(values)); ins.append((0, 0)); outs.append((0, 0))
            elif command == "C":
                x1, y1, x2, y2, x, y = values
                outs[-1] = (x1 - points[-1][0], y1 - points[-1][1])
                points.append((x, y)); ins.append((x2 - x, y2 - y)); outs.append((0, 0))
            elif command == "Z":
                # Close a final cubic at the initial vertex without a duplicate node.
                if points[-1] == points[0] and len(points) > 1:
                    ins[0] = ins[-1]; points.pop(); ins.pop(); outs.pop()
                yield points, ins, outs, True
                points, ins, outs = [], [], []
            else:
                raise ValueError(f"Generator path command is not implemented: {command}")
        if points:
            yield points, ins, outs, False


def path(*values, fill=False, width=1.8) -> Shape:
    commands = []
    at = 0
    arity = {"M": 2, "L": 2, "C": 6, "Z": 0}
    while at < len(values):
        command = values[at]; count = arity[command]
        commands.append((command, tuple(values[at + 1:at + 1 + count])))
        at += count + 1
    return Shape(commands, fill, width)


def line(*points, width=1.8):
    return path("M", *points[0], *[value for point in points[1:] for value in ("L", *point)], width=width)


def polygon(points, fill=False, width=1.8):
    return Shape([("M", tuple(points[0]))] + [("L", tuple(point)) for point in points[1:]] + [("Z", ())], fill, width)


def circle(x, y, radius, fill=False, width=1.8):
    k = radius * KAPPA
    return path("M", x + radius, y, "C", x + radius, y + k, x + k, y + radius, x, y + radius,
                "C", x - k, y + radius, x - radius, y + k, x - radius, y,
                "C", x - radius, y - k, x - k, y - radius, x, y - radius,
                "C", x + k, y - radius, x + radius, y - k, x + radius, y, "Z", fill=fill, width=width)


def rect(x, y, w, h, radius=1.5, fill=False, width=1.8):
    r = min(radius, w / 2, h / 2); k = r * KAPPA
    return path("M", x + r, y, "L", x + w - r, y,
                "C", x + w - r + k, y, x + w, y + r - k, x + w, y + r,
                "L", x + w, y + h - r,
                "C", x + w, y + h - r + k, x + w - r + k, y + h, x + w - r, y + h,
                "L", x + r, y + h,
                "C", x + r - k, y + h, x, y + h - r + k, x, y + h - r,
                "L", x, y + r,
                "C", x, y + r - k, x + r - k, y, x + r, y, "Z", fill=fill, width=width)


def arc(x, y, radius, start, end, width=1.8):
    steps = max(4, math.ceil(abs(end - start) / 10))
    return line(*[(x + radius * math.cos(math.radians(start + (end - start) * i / steps)),
                   y + radius * math.sin(math.radians(start + (end - start) * i / steps)))
                  for i in range(steps + 1)], width=width)


def slash():
    return line((4, 4), (20, 20), width=2.0)


def wifi(level=4):
    shapes = [circle(12, 19, 1.15, fill=True)]
    for threshold, radius in [(2, 4), (3, 7.5), (4, 11)]:
        if level >= threshold:
            shapes.append(arc(12, 19, radius, 225, 315))
    if level == 0:
        shapes = [circle(12, 18.8, 1.5, width=1.5)]
    return shapes


def cellular(level=4):
    shapes = []
    for index, height in enumerate([3, 6.8, 10.6, 14.4]):
        shapes.append(rect(3.5 + index * 4.4, 20 - height, 2.5, height, 1.1,
                           fill=index < level, width=1.05))
    return shapes


def battery(level):
    shapes = [rect(2.5, 6.5, 18, 11, 2.6, width=1.6), line((22, 10), (22, 14), width=1.6)]
    if level > 0:
        shapes.append(rect(4.8, 8.8, 13.4 * level / 100, 6.4, .9, fill=True))
    return shapes


def bluetooth():
    return [line((7, 6.5), (17, 15.7), (12, 20), (12, 4), (17, 8.3), (7, 17.5))]


def location():
    return [path("M", 12, 21, "C", 9.4, 17.6, 5.4, 13.4, 5.4, 9.6,
                 "C", 5.4, 1.1, 18.6, 1.1, 18.6, 9.6,
                 "C", 18.6, 13.4, 14.6, 17.6, 12, 21, "Z"), circle(12, 9.7, 2.2)]


def alarm():
    return [circle(12, 13, 7), line((12, 9), (12, 13), (15.2, 14.8)),
            line((4, 6), (6.6, 3.5)), line((17.4, 3.5), (20, 6)),
            line((7, 19), (5.5, 21)), line((17, 19), (18.5, 21))]


def moon():
    return [path("M", 18.9, 16.1, "C", 17.3, 20.6, 11.9, 22, 7.8, 19.3,
                 "C", 3.5, 16.7, 3.4, 10.3, 7.3, 7.1,
                 "C", 7, 12.5, 12.3, 17.5, 18.9, 16.1, "Z", fill=True)]


def speaker(level=3):
    shapes = [polygon([(4, 9), (8, 9), (12, 5.5), (12, 18.5), (8, 15), (4, 15)])]
    if level == 0:
        shapes += [line((16, 9.5), (20, 14.5)), line((20, 9.5), (16, 14.5))]
    for index in range(level):
        shapes.append(arc(12, 12, 4 + index * 3.2, -44, 44, width=1.6))
    return shapes


def hotspot():
    return [circle(12, 12, 1.6, fill=True), arc(12, 12, 5.2, -58, 58),
            arc(12, 12, 5.2, 122, 238), arc(12, 12, 9, -58, 58), arc(12, 12, 9, 122, 238)]


def headset():
    return [path("M", 4, 13, "L", 4, 11, "C", 4, .8, 20, .8, 20, 11, "L", 20, 13),
            rect(3.6, 11.5, 4.2, 8, 1.8, fill=True), rect(16.2, 11.5, 4.2, 8, 1.8, fill=True)]


def rotate():
    return [arc(12, 12, 8, 205, 387), line((19, 7), (20, 11.8), (15.5, 11)),
            rect(8.8, 7.5, 6.4, 10, 1.6, width=1.5)]


def lock():
    return [rect(5.5, 10, 13, 10, 2.5), path("M", 8, 10, "L", 8, 7,
            "C", 8, 1.7, 16, 1.7, 16, 7, "L", 16, 10), circle(12, 15, .85, fill=True)]


def nfc():
    return [path("M", 5, 18, "L", 5, 6, "C", 5, 3.3, 9.4, 3.3, 9.4, 6,
                 "L", 9.4, 14.5, "C", 9.4, 18.3, 14.6, 18.3, 14.6, 14.5,
                 "L", 14.6, 6, "C", 14.6, 3.3, 19, 3.3, 19, 6, "L", 19, 18)]


def cast():
    return [path("M", 4, 8, "L", 4, 5.5, "C", 4, 4.7, 4.7, 4, 5.5, 4,
                 "L", 19.5, 4, "C", 20.3, 4, 21, 4.7, 21, 5.5,
                 "L", 21, 16.5, "C", 21, 17.3, 20.3, 18, 19.5, 18, "L", 16, 18),
            circle(4, 20, 1.1, fill=True), arc(4, 20, 5, -90, 0), arc(4, 20, 9, -90, 0)]


def recording():
    return [rect(3.5, 5.5, 17, 13, 3), circle(12, 12, 3.1, fill=True)]


def microphone():
    return [rect(8.6, 3, 6.8, 11.5, 3.3), path("M", 5.5, 11, "L", 5.5, 12,
             "C", 5.5, 20.5, 18.5, 20.5, 18.5, 12, "L", 18.5, 11),
            line((12, 18.6), (12, 21)), line((8.6, 21), (15.4, 21))]


def camera():
    return [path("M", 4.5, 7.5, "L", 8, 7.5, "L", 9.5, 5, "L", 14.5, 5,
                 "L", 16, 7.5, "L", 19.5, 7.5, "C", 20.6, 7.5, 21, 8, 21, 9,
                 "L", 21, 18, "C", 21, 19.1, 20.5, 19.5, 19.5, 19.5,
                 "L", 4.5, 19.5, "C", 3.4, 19.5, 3, 19, 3, 18,
                 "L", 3, 9, "C", 3, 8, 3.5, 7.5, 4.5, 7.5, "Z"), circle(12, 13.1, 3.2)]


def handset():
    return [path("M", 5, 4.3, "C", 3, 6.8, 6.2, 13.5, 10.6, 17.5,
                 "C", 14.1, 20.8, 18.8, 21.6, 20, 18.5,
                 "L", 16.2, 15.5, "L", 13.8, 17,
                 "C", 10.9, 15.5, 8.6, 13.1, 7.3, 10.4,
                 "L", 9, 8.2, "L", 6.5, 4, "Z")]


def usb():
    return [line((12, 20), (12, 4)), polygon([(9.8, 5.8), (12, 2.8), (14.2, 5.8)], fill=True),
            line((12, 15), (6.5, 11.8), (6.5, 8)), circle(6.5, 6.9, 1.2),
            line((12, 12), (17.5, 9), (17.5, 6.5)), rect(16.2, 3.9, 2.6, 2.6, .3, fill=True),
            circle(12, 20.4, 1.25, fill=True)]


def hd():
    return [line((3.5, 7), (3.5, 17)), line((9, 7), (9, 17)), line((3.5, 12), (9, 12)),
            path("M", 14, 7, "L", 16, 7, "C", 22, 7, 22, 17, 16, 17, "L", 14, 17, "Z")]


def airplane():
    return [path("M", 11, 3.5, "C", 11, 1.5, 13, 1.5, 13, 3.5,
                 "L", 13, 9, "L", 21, 14, "L", 21, 16, "L", 13, 13.5,
                 "L", 13, 18, "L", 16, 20, "L", 16, 21, "L", 12, 20,
                 "L", 8, 21, "L", 8, 20, "L", 11, 18,
                 "L", 11, 13.5, "L", 3, 16, "L", 3, 14, "L", 11, 9, "Z", fill=True)]


def mobile_data():
    return [line((7, 20), (7, 4)), line((3.5, 8), (7, 4), (10.5, 8)),
            line((17, 4), (17, 20)), line((13.5, 16), (17, 20), (20.5, 16))]


def flashlight():
    return [polygon([(6.5, 4), (17.5, 4), (17.5, 8), (15, 11), (15, 20), (9, 20), (9, 11), (6.5, 8)]),
            line((7, 8), (17, 8)), line((11, 14), (13, 14), width=1.5)]


def sun(auto=False):
    shapes = [circle(12, 12, 4)]
    for degrees in range(0, 360, 45):
        angle = math.radians(degrees)
        shapes.append(line((12 + math.cos(angle) * 7, 12 + math.sin(angle) * 7),
                           (12 + math.cos(angle) * 9.5, 12 + math.sin(angle) * 9.5), width=1.6))
    if auto:
        # Auto marker is a distinct miniature A, not a fabricated on/off state.
        return [line((4, 20), (12, 3), (20, 20)), line((7.2, 14), (16.8, 14))]
    return shapes


def gear():
    points = []
    for index in range(32):
        angle = math.radians(index * 360 / 32 - 90)
        radius = 9 if index % 4 in (1, 2) else 7.2
        points.append((12 + radius * math.cos(angle), 12 + radius * math.sin(angle)))
    return [polygon(points, width=1.5), circle(12, 12, 3.1, width=1.6)]


def more():
    return [circle(x, 12, 1.55, fill=True) for x in (5.5, 12, 18.5)]


def play():
    return [polygon([(7, 4), (20, 12), (7, 20)], fill=True)]


def pause():
    return [rect(6, 4, 4, 16, 1.3, fill=True), rect(14, 4, 4, 16, 1.3, fill=True)]


def skip(forward=True):
    shapes = [polygon([(5, 5), (17, 12), (5, 19)], fill=True), line((19, 5), (19, 19), width=2.1)]
    if forward: return shapes
    return [Shape([(command, tuple(24-value if index % 2 == 0 else value for index, value in enumerate(values)))
                   for command, values in shape.commands], shape.fill, shape.width) for shape in shapes]


def media_output():
    return [path("M", 5, 16, "L", 3.5, 16, "L", 3.5, 4.5, "L", 20.5, 4.5, "L", 20.5, 16, "L", 19, 16),
            polygon([(7, 20), (12, 13.5), (17, 20)], fill=True)]


def device_entrance():
    return [path("M", 10.5, 17.5, "L", 4, 17.5, "L", 4, 4.5, "L", 20, 4.5, "L", 20, 9),
            line((6, 20.5), (10, 20.5)), rect(13, 10.5, 7.5, 11, 1.6), line((15.5, 19.2), (18, 19.2), width=1.1)]


def device(kind):
    if kind == "headset": return headset()
    if kind == "speaker": return [rect(6, 3, 12, 18, 3), circle(12, 14.5, 3.4), circle(12, 6.5, .8, fill=True)]
    if kind in ("phone", "tablet", "pad"): return [rect(7 if kind == "phone" else 4.5, 3, 10 if kind == "phone" else 15, 18, 2.5), line((10, 18), (14, 18), width=1.4)]
    if kind == "computer": return [rect(3, 4, 18, 13, 2), line((12, 17), (12, 21)), line((7, 21), (17, 21))]
    if kind == "tv": return [rect(3, 5, 18, 13, 2), line((8, 21), (10, 18)), line((16, 21), (14, 18))]
    if kind == "watch": return [rect(6, 6, 12, 12, 3), rect(9, 2, 6, 4, 1), rect(9, 18, 6, 4, 1)]
    if kind == "wristband": return [rect(8, 5, 8, 14, 4), line((10, 2), (14, 2)), line((10, 22), (14, 22)), line((12, 9), (12, 12), (14, 13), width=1.2)]
    raise KeyError(kind)


def sparkle(x=16, y=7, radius=3):
    return polygon([(x, y-radius), (x+radius*.28, y-radius*.28), (x+radius, y),
                    (x+radius*.28, y+radius*.28), (x, y+radius), (x-radius*.28, y+radius*.28),
                    (x-radius, y), (x-radius*.28, y-radius*.28)], fill=True)


def temperature():
    return [path("M", 10, 13.5, "L", 10, 5, "C", 10, 1.7, 15, 1.7, 15, 5,
                 "L", 15, 13.5, "C", 20, 18, 14, 24, 9.5, 20,
                 "C", 7.5, 18.3, 8, 15.4, 10, 13.5, "Z"),
            line((12.5, 8), (12.5, 17), width=1.4), circle(12.5, 17.5, 1.5, fill=True),
            line((18, 6), (21, 6), width=1.4), line((18, 10), (20, 10), width=1.4)]


def shield():
    return [path("M", 12, 3, "L", 20, 6, "L", 19, 13, "C", 18.4, 17, 15, 19.7, 12, 21,
                 "C", 9, 19.7, 5.6, 17, 5, 13, "L", 4, 6, "Z")]


def leaf():
    return [path("M", 6, 18, "C", 1.2, 9.5, 11, 4, 20, 4,
                 "C", 20, 13.8, 15, 22, 6, 18, "Z"), line((5, 20), (16, 9), width=1.5)]


def light():
    return [path("M", 8.5, 16.5, "L", 8.5, 15, "C", 8.5, 13, 5.8, 12, 5.8, 8.5,
                 "C", 5.8, .3, 18.2, .3, 18.2, 8.5, "C", 18.2, 12, 15.5, 13, 15.5, 15,
                 "L", 15.5, 16.5, "Z"), line((9, 19), (15, 19)), line((10, 21), (14, 21))]


def briefcase():
    return [rect(3, 7, 18, 14, 2.3), path("M", 8, 7, "L", 8, 4.5,
            "C", 8, 2.5, 16, 2.5, 16, 4.5, "L", 16, 7),
            line((3, 12), (9, 14), (15, 14), (21, 12), width=1.5), rect(10, 12.5, 4, 3, .8, fill=True)]


def display_enhance():
    return [rect(3, 5, 18, 14, 2.5), line((6, 16), (10, 12), (13, 15)), sparkle(16, 9, 3)]


def video_enhance():
    return [path("M", 2.5, 12, "C", 7, 4, 17, 4, 21.5, 12,
                 "C", 17, 20, 7, 20, 2.5, 12, "Z"), circle(12, 12, 3), sparkle(19, 4, 2)]


def audio_effect():
    # Audio waves, deliberately not the branded Dolby double-D logo.
    return [line((4, 9), (4, 15)), line((8, 6), (8, 18)), line((12, 3), (12, 21)),
            line((16, 6), (16, 18)), line((20, 9), (20, 15))]


def bell():
    return [path("M", 5, 17, "C", 6.5, 15, 6, 11, 6.5, 8,
                 "C", 7.2, 2.4, 16.8, 2.4, 17.5, 8,
                 "C", 18, 11, 17.5, 15, 19, 17, "Z"), arc(12, 18, 3, 20, 160),
            line((12, 2), (12, 3.5), width=1.4)]


def vibrate():
    return [rect(8, 4, 8, 16, 1.8), line((4.5, 6), (3, 9), (5, 12), (3, 15), (4.5, 18), width=1.4),
            line((19.5, 6), (21, 9), (19, 12), (21, 15), (19.5, 18), width=1.4)]


def anti_theft():
    return [item.transformed(.76, .5, 4.2) for item in device("phone")] + [
        circle(18, 7, 3.5, width=1.5), line((18, 4.8), (18, 7.2), width=1.4), circle(18, 9, .55, fill=True)]


def energy_saver(super_mode=False):
    shapes = [item.transformed(.82, .5, 5.5) for item in battery(50)]
    if super_mode:
        return shapes + [polygon([(14, 3), (10, 9), (13, 9), (11, 14), (18, 7), (14, 7)], fill=True)]
    return shapes + [item.transformed(.45, 11, -.2) for item in leaf()]


def small_screen():
    return [rect(4.5, 2.5, 15, 19, 2.5), rect(10, 11, 7, 8, 1.2),
            line((7, 6), (11, 10)), line((7, 10), (11, 10), (11, 6), width=1.4)]


def envelope():
    return [rect(3, 6, 18, 14, 2.6), line((3.5, 7), (12, 13.5), (20.5, 7)),
            circle(12, 13, 2.1, fill=True), line((9, 3), (15, 3), width=1.4)]


def payment(chat=False):
    # Original payment card or conversation marker, never a traced payment-service logo.
    shapes = [rect(3, 5, 18, 15, 2.3), line((3, 9), (21, 9), width=1.5)]
    if chat:
        return shapes + [path("M", 8, 12, "L", 17, 12, "L", 17, 16, "L", 13, 16,
                              "L", 10, 18, "L", 10, 16, "L", 8, 16, "Z", width=1.3)]
    return shapes + [line((8, 17), (11, 12), (14, 17), width=1.4), line((9.2, 15), (12.8, 15), width=1.2)]


def scanner(kind="qr"):
    shapes = [line((3, 8), (3, 3), (8, 3)), line((16, 3), (21, 3), (21, 8)),
              line((3, 16), (3, 21), (8, 21)), line((16, 21), (21, 21), (21, 16)),
              rect(7, 7, 3, 3, .4, fill=True), rect(14, 7, 3, 3, .4, fill=True)]
    if kind == "alipay":
        return shapes + [line((8, 17), (12, 12), (16, 17), width=1.4), line((10, 15), (14, 15), width=1.2)]
    if kind == "wechat":
        return shapes + [path("M", 7, 12, "L", 17, 12, "L", 17, 16, "L", 12, 16,
                              "L", 9, 18, "L", 9, 16, "L", 7, 16, "Z", width=1.3)]
    return shapes + [rect(7, 14, 3, 3, .4, fill=True), line((14, 14), (17, 14), (17, 17), (14, 17), width=1.4)]


def calculator():
    return [rect(5, 2.5, 14, 19, 2.4), rect(8, 5.5, 8, 4, .9, width=1.3),
            line((8, 13), (11, 13), width=1.4), line((9.5, 11.5), (9.5, 14.5), width=1.4),
            line((14, 13), (16, 13), width=1.4), circle(9.5, 18, .8, fill=True), circle(15, 18, .8, fill=True)]


def broom():
    return [line((13, 11), (19, 3)), polygon([(10, 10), (16, 14), (13, 21), (3, 15)]),
            line((7, 14), (11, 19), width=1.3), line((10, 13), (13, 17), width=1.3)]


def assistant():
    return [sparkle(10.5, 11, 7.5), circle(19, 5, 2.1, fill=True), circle(19, 18, 1.5, fill=True)]


def keyboard():
    shapes = [rect(2.5, 5, 19, 14, 2.2), line((7, 16), (17, 16), width=1.4)]
    for y in (9, 12):
        shapes.extend(circle(x, y, .65, fill=True) for x in (6, 10, 14, 18))
    return shapes


def power():
    return [arc(12, 12.5, 8, -58, 238), line((12, 2.5), (12, 11.5), width=2.1)]


def multi_system():
    return [rect(3, 3, 12.5, 13, 2), rect(8.5, 8, 12.5, 13, 2),
            line((10.5, 14), (18.5, 14)), line((16, 11.5), (18.5, 14), (16, 16.5), width=1.4)]


def screenshot():
    return [line((3, 8), (3, 3), (8, 3)), line((16, 3), (21, 3), (21, 8)),
            line((3, 16), (3, 21), (8, 21)), line((16, 21), (21, 21), (21, 16)),
            polygon([(7, 16), (11, 10), (14, 14), (16, 12), (18, 16)], width=1.5), circle(16, 7.5, 1.2)]


def controls():
    return [path("M", 3, 11, "L", 12, 3, "L", 21, 11), rect(6, 10, 12, 11, 1.8),
            line((9, 13), (9, 18), width=1.2), line((15, 13), (15, 18), width=1.2),
            circle(9, 14.5, 1.2, fill=True), circle(15, 17, 1.2, fill=True)]


def wallet():
    return [path("M", 4, 8, "L", 4, 5, "L", 17, 3, "L", 17, 7), rect(3, 7, 18, 14, 2.5),
            rect(14, 12, 7, 5, 1.3), circle(17, 14.5, .65, fill=True)]


BASES = {"bluetooth": bluetooth, "location": location, "alarm_clock": alarm, "zen": moon,
         "volume": lambda: speaker(0), "hotspot": hotspot, "headset": headset, "rotate": rotate,
         "rotation": rotate, "vpn": lock, "nfc": nfc, "cast": cast, "screen_record": recording,
         "microphone": microphone, "camera": camera, "privacy_call": handset, "usb": usb,
         "hd": hd, "airplane": airplane, "mobile_data": mobile_data, "wifi": wifi,
         "flashlight": flashlight, "dark": moon, "settings": gear, "more": more}
BASES.update({"auto_brightness": lambda: sun(True), "auto_color_temperature": temperature,
              "data_saver": leaf, "dolby": audio_effect, "breathing_light": light, "work": briefcase,
              "osie": display_enhance, "iris": video_enhance, "otg": usb, "dnd": moon,
              "no_disturb": lambda: bell()+[line((9, 12), (15, 12), width=1.6)],
              "battery_saver": energy_saver, "phone_anti_theft": anti_theft,
              "super_power_saver": lambda: energy_saver(True), "vibration": vibrate,
              "small_screen": small_screen, "envelope": envelope,
              "alipay": payment, "ali_scan": lambda: scanner("alipay"),
              "wechat_pay": lambda: payment(True), "wechat_scan": lambda: scanner("wechat"),
              "calculator": calculator, "clean": broom, "google_now": assistant,
              "lock_screen": lock, "input_method": keyboard, "shutdown": power,
              "qr_scanner": scanner, "multi_system": multi_system, "screenshot": screenshot,
              "controls": controls, "wallet": wallet})


def tile_artwork(target: str, state: str):
    name = target.removeprefix("tile.")
    if name == "ringer_mode":
        if state == "silent": return bell()+[slash()]
        if state == "vibrate": return vibrate()
        if state == "ring": return bell()+[arc(12, 11, 10, -47, 0, width=1.3), arc(12, 11, 10, 180, 227, width=1.3)]
        raise KeyError(target+'.'+state)
    if name == "screen_record":
        if state == "idle": return [rect(3.5, 5.5, 17, 13, 3), circle(12, 12, 3.1)]
        if state == "recording": return [rect(3.5, 5.5, 17, 13, 3), rect(9, 9, 6, 6, 1, fill=True)]
        if state != "unavailable": raise KeyError(target+'.'+state)
    if name not in BASES:
        raise KeyError(target)
    base = BASES[name]()
    if state == "on": return base
    if state == "off": return base + [slash()]
    if state == "unavailable":
        return [item.transformed(.72, .8, .8) for item in base] + [circle(18, 18, 3.4, width=1.5), line((16.6, 18), (19.4, 18), width=1.5)]
    if state == "default": return base
    raise KeyError(f"{target}.{state}")


def artwork(target: str, state: str):
    if target == "wifi": return wifi(4) + [slash()] if state == "none" else wifi(int(state))
    if target == "cellular": return cellular(0) + [slash()] if state == "none" else cellular(int(state))
    if target in ("battery", "battery.charging"): return battery(int(state))
    if target.startswith("hint."):
        name = target.removeprefix("hint.")
        shapes = BASES[name]()
        return shapes + [circle(20, 4, 1.4, fill=True)] if name == "bluetooth" and state == "on" else shapes
    if target.startswith("tile."): return tile_artwork(target, state)
    if target == "slider.volume.normal": return speaker({"mute": 0, "low": 1, "medium": 2, "high": 3}[state])
    if target == "slider.volume.wired": return headset() + ([slash()] if state == "mute" else [])
    if target == "slider.volume.bluetooth": return bluetooth() + ([slash()] if state == "mute" else [])
    if target == "slider.brightness": return sun()
    if target == "slider.brightness_auto": return sun(True)
    if target.startswith("footer."): return BASES[target.removeprefix("footer.")]()
    if target == "media.play_pause": return {"play": play, "pause": pause}[state]()
    if target == "media.previous": return skip(False)
    if target == "media.next": return skip(True)
    if target == "media.output": return media_output()
    if target == "device.entrance": return device_entrance()
    if target.startswith("device.") and state == "default": return device(target.removeprefix("device."))
    # New registered targets require intentional artwork; never silently substitute.
    raise KeyError(f"No original drawing for {target}.{state}")


def xml_bytes(shapes):
    return ('<?xml version="1.0" encoding="utf-8"?>\n'
            '<!-- Original C17示例库; GPL-3.0-only; no traced third-party artwork. -->\n'
            '<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="24dp" android:height="24dp" android:viewportWidth="24" android:viewportHeight="24">\n'
            + "\n".join(shape.xml() for shape in shapes) + '\n</vector>\n').encode("utf-8")


def raster(shapes, size=96, supersample=4):
    scale = size * supersample / 24
    image = Image.new("L", (size * supersample, size * supersample), 0)
    draw = ImageDraw.Draw(image)
    for shape in shapes:
        for vertices, ins, outs, closed in shape.paths():
            sampled = [vertices[0]]
            segments = len(vertices) if closed else len(vertices) - 1
            for index in range(segments):
                next_index = (index + 1) % len(vertices)
                a, b = vertices[index], vertices[next_index]
                c = (a[0] + outs[index][0], a[1] + outs[index][1])
                d = (b[0] + ins[next_index][0], b[1] + ins[next_index][1])
                for step in range(1, 25):
                    t = step / 24; u = 1 - t
                    sampled.append((u**3*a[0]+3*u*u*t*c[0]+3*u*t*t*d[0]+t**3*b[0],
                                    u**3*a[1]+3*u*u*t*c[1]+3*u*t*t*d[1]+t**3*b[1]))
            pixels = [(round(x * scale), round(y * scale)) for x, y in sampled]
            if shape.fill:
                draw.polygon(pixels, fill=255)
            else:
                stroke = max(1, round(shape.width * scale))
                draw.line(pixels, fill=255, width=stroke, joint="curve")
                radius = shape.width * scale / 2
                # Round line caps and joins are shared with the XML contract.
                for x, y in (pixels if len(pixels) < 8 else [pixels[0], pixels[-1]]):
                    draw.ellipse((x-radius, y-radius, x+radius, y+radius), fill=255)
    image = image.resize((size, size), Image.Resampling.LANCZOS)
    result = Image.new("RGBA", (size, size), "white"); result.putalpha(image)
    return result


def png_bytes(shapes, size=96):
    output = io.BytesIO(); raster(shapes, size).save(output, "PNG", optimize=True)
    return output.getvalue()


def prop(value): return {"a": 0, "k": value}


def animated(values):
    frames = []
    for index, (time, value) in enumerate(values):
        frame = {"t": time, "s": value}
        if index < len(values) - 1:
            frame.update({"e": values[index+1][1], "o": {"x": [0.25], "y": [0.1]}, "i": {"x": [0.75], "y": [0.9]}})
        frames.append(frame)
    return {"a": 1, "k": frames}


def lottie_group(shapes, opacity=None):
    items = []
    for shape in shapes:
        paths = [{"ty": "sh", "ks": prop({"v": vertices, "i": ins, "o": outs, "c": closed})}
                 for vertices, ins, outs, closed in shape.paths()]
        paint = {"ty": "fl" if shape.fill else "st", "c": prop([1, 1, 1, 1]), "o": prop(100)}
        if not shape.fill: paint.update({"w": prop(shape.width), "lc": 2, "lj": 2, "ml": 4})
        items.append({"ty": "gr", "it": paths + [paint, {"ty": "tr", "o": prop(100)}]})
    items.append({"ty": "tr", "o": opacity or prop(100)})
    return {"ty": "gr", "it": items}


def animation(target):
    # A real 400 ms graphic animation from the supplied off drawing to on drawing.
    # The diagonal off stroke fades; the function glyph makes a small, bounded
    # emphasis pulse. Final frame exactly retains the on artwork transform.
    layer = {"ddd": 0, "ind": 1, "ty": 4, "nm": target + " original on transition", "ip": 0, "op": 12,
             "ks": {"a": prop([12, 12, 0]), "p": prop([12, 12, 0]), "r": prop(0), "o": prop(100),
                    "s": animated([(0, [100, 100, 100]), (6, [106, 106, 100]), (12, [100, 100, 100])])},
             "shapes": [lottie_group(BASES[target.removeprefix("tile.")]()),
                        lottie_group([slash()], animated([(0, [100]), (8, [0]), (12, [0])]))]}
    return {"v": "5.7.4", "nm": "C17示例库 " + target, "w": 24, "h": 24, "fr": 30,
            "ip": 0, "op": 12, "ddd": 0, "assets": [], "markers": [], "layers": [layer]}


def role_snapshot():
    """Explicit copy of the production Registry, never a source of native lookup rules."""
    return json.loads((ROOT / "roles.json").read_text("utf-8"))


def write_zip(destination, manifest, resources):
    destination.parent.mkdir(parents=True, exist_ok=True)
    entries = {"manifest.json": json.dumps(manifest, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8"),
               "LICENSE.txt": LICENSE.encode("utf-8"), "README.md": (
                   "# C17示例库\n\n原创圆润几何图标。只包含本版固定角色表，不能据此宣称全控制中心适配。\n"
                   "PNG 与 VectorDrawable 使用同一几何母版；mask 跟随实际宿主颜色。\n"
                   "电池不包含百分数字或充电闪电，仍由原生绘制。动画资源通过准入不等于已接入原生播放。\n"
                   "主包包含 XML，备用包包含96px PNG。两者均仅在用户选择范围后应用。\n").encode("utf-8"), **resources}
    with zipfile.ZipFile(destination, "w", zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, content in sorted(entries.items()):
            info = zipfile.ZipInfo(name, (2026, 10, 18, 0, 0, 0)); info.compress_type = zipfile.ZIP_DEFLATED
            info.external_attr = 0o100644 << 16; info.create_system = 3
            archive.writestr(info, content)
    return entries


def contact_sheet(roles, drawings, output):
    columns = 6; width = columns * 220; cell_height = 142
    image = Image.new("RGB", (width, math.ceil(len(roles) / columns) * cell_height + 92), "#eef0f3")
    draw = ImageDraw.Draw(image)
    font_path = Path("C:/Windows/Fonts/msyh.ttc")
    if not font_path.exists(): font_path = Path("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf")
    font = ImageFont.truetype(str(font_path), 15); small = ImageFont.truetype(str(font_path), 12)
    draw.text((20, 14), "C17示例库 · original geometry / XML + PNG", fill="#171a20", font=font)
    draw.text((20, 43), f"{len(roles)} registered static roles · 18 / 24 / 36px · native conditions unchanged", fill="#505760", font=small)
    for index, row in enumerate(roles):
        x = (index % columns) * 220; y = 88 + (index // columns) * cell_height
        draw.rounded_rectangle((x+6, y, x+214, y+134), radius=12, fill="white")
        for dark, left in ((False, x+16), (True, x+115)):
            draw.rounded_rectangle((left, y+9, left+90, y+77), radius=9, fill="#22272f" if dark else "#f2f4f7")
            for size, dx in ((18, 2), (24, 24), (36, 53)):
                icon = raster(drawings[row["role"]], size)
                if not dark:
                    color = Image.new("RGBA", icon.size, "#141a22"); color.putalpha(icon.getchannel("A")); icon = color
                image.paste(icon, (left+dx, y+44-size//2), icon)
        draw.text((x+16, y+86), row["role"], fill="#1b2633", font=small)
        title = row["title"] + (" · 待接入" if not row["supported"] else "")
        draw.text((x+16, y+108), title[:26], fill="#596473", font=small)
    output.parent.mkdir(parents=True, exist_ok=True); image.save(output, "PNG", optimize=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, default=ROOT / "dist")
    parser.add_argument("--copy-to", type=Path, help="optional copy of the generated vector ZIP")
    arguments = parser.parse_args(); output = arguments.output.resolve(); output.mkdir(parents=True, exist_ok=True)
    roles = role_snapshot()
    drawings = {}; missing = []
    for row in roles:
        try: drawings[row["role"]] = artwork(row["target"], row["state"])
        except (KeyError, ValueError) as failure: missing.append(f'{row["role"]}: {failure}')
    if missing: raise RuntimeError("New roles require original drawings; no placeholders generated:\n" + "\n".join(missing))
    source_directory = ROOT / "artwork/c17-rounded-27"; source_directory.mkdir(parents=True, exist_ok=True)
    png_directory = source_directory / "png96"; png_directory.mkdir(exist_ok=True)
    vector_resources, png_resources, vector_icons, png_icons = {}, {}, {}, {}
    for row in roles:
        role = row["role"]; safe_name = role.replace(".", "-")
        vector_data = xml_bytes(drawings[role]); png_data = png_bytes(drawings[role])
        with Image.open(io.BytesIO(png_data)) as image:
            alpha = image.getchannel("A")
            if alpha.getbbox() is None or alpha.getextrema()[0] != 0:
                raise RuntimeError(f"Original drawing must be nonempty with transparent margins: {role}")
        (source_directory / f"{safe_name}.xml").write_bytes(vector_data)
        (png_directory / f"{safe_name}.png").write_bytes(png_data)
        for extension, data, resources, icons in (("xml", vector_data, vector_resources, vector_icons), ("png", png_data, png_resources, png_icons)):
            resource = f"assets/{safe_name}.{extension}"; resources[resource] = data
            icons[role] = {"source": resource, "render": "mask", "sha256": hashlib.sha256(data).hexdigest()}
    transitions = {}
    for target in ("tile.flashlight", "tile.dark", "tile.rotation"):
        if f"{target}.off" not in drawings or f"{target}.on" not in drawings: continue
        data = json.dumps(animation(target), ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        resource = "assets/" + target.replace(".", "-") + "-off-to-on.json"
        (source_directory / Path(resource).name).write_bytes(data)
        vector_resources[resource] = png_resources[resource] = data
        transitions[target + ".off_to_on"] = {"source": resource, "from": "off", "to": "on", "reversible": False, "sha256": hashlib.sha256(data).hexdigest()}
    base_manifest = {"format": "c17-statusbar-icons", "version": 3, "id": "c17-rounded-27", "name": "C17示例库", "author": "aiingjie", "license": "GPL-3.0-only", "fallback": "native", "transitions": transitions}
    manifest = {**base_manifest, "icons": vector_icons}; png_manifest = {**base_manifest, "id": "c17-rounded-27-png", "name": "C17示例库 · PNG", "icons": png_icons}
    vector_zip = output / "c17-rounded-27.zip"; png_zip = output / "c17-rounded-27-png.zip"
    write_zip(vector_zip, manifest, vector_resources); write_zip(png_zip, png_manifest, png_resources)
    if arguments.copy_to:
        arguments.copy_to.parent.mkdir(parents=True, exist_ok=True); arguments.copy_to.write_bytes(vector_zip.read_bytes())
    from validate_pack import validate
    validate(vector_zip); validate(png_zip)
    (source_directory / "LICENSE.txt").write_text(LICENSE, "utf-8")

    (output / "manifest-vector.json").write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    (output / "manifest-png.json").write_text(json.dumps(png_manifest, ensure_ascii=False, indent=2) + "\n", "utf-8")
    contact_sheet(roles, drawings, output / "contact-sheet.png")
    report = {"roles": len(roles), "targets": len({row["target"] for row in roles}), "supported_roles": sum(row["supported"] for row in roles), "animations": len(transitions),
              "vector_bytes": vector_zip.stat().st_size, "png_bytes": png_zip.stat().st_size,
              "vector_sha256": hashlib.sha256(vector_zip.read_bytes()).hexdigest(), "png_sha256": hashlib.sha256(png_zip.read_bytes()).hexdigest(),
              "note": "Registered roles only; static/XML/animation admission is not native visual or playback validation."}
    (output / "report.json").write_text(json.dumps(report, indent=2) + "\n", "utf-8")
    print(json.dumps(report)); print(f"Contact sheet: {output / 'contact-sheet.png'}")


if __name__ == "__main__":
    main()
