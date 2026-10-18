#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 aiingjie
"""Exercise real ZIP/PNG/XML/Lottie positive data and independently corrupted packages."""
import copy
import hashlib
import io
import json
from pathlib import Path
import struct
import tempfile
import xml.etree.ElementTree as ET
import zipfile
import zlib
from PIL import Image
from validate_pack import ROOT, validate


def encoded(value):
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).encode("utf-8")


def picture(opaque=False, width=16):
    image = Image.new("RGBA", (width, 16), (255, 255, 255, 255 if opaque else 0))
    image.putpixel((width // 2, 8), (255, 255, 255, 255)); data = io.BytesIO(); image.save(data, "PNG"); return data.getvalue()


with zipfile.ZipFile(ROOT / "dist/c17-rounded-27.zip") as source:
    MOTION = source.read("assets/tile-flashlight-off-to-on.json")
VECTOR = b'<vector xmlns:android="http://schemas.android.com/apk/res/android" android:width="24dp" android:height="24dp" android:viewportWidth="24" android:viewportHeight="24"><path android:fillColor="#ffffffff" android:pathData="M 3 3 L 20 3 L 12 20 Z"/></vector>'
BASE = {"format": "c17-statusbar-icons", "version": 3, "id": "check-original", "name": "Check original", "author": "aiingjie", "license": "MIT", "fallback": "native",
        "icons": {role: {"source": "assets/a.png", "render": "mask"} for role in ("wifi.1", "tile.flashlight.off", "tile.flashlight.on")},
        "transitions": {"tile.flashlight.off_to_on": {"source": "assets/a.json", "from": "off", "to": "on", "reversible": False}}}
ASSETS = {"assets/a.png": picture(), "assets/a.json": MOTION}
cases, negatives = 0, 0


def case(directory, name, mutate=None, *, reject=True, raw=None, extra=None, prefix="", compression=zipfile.ZIP_DEFLATED, post=None):
    global cases, negatives
    manifest, assets = copy.deepcopy(BASE), dict(ASSETS)
    if mutate:
        mutate(manifest, assets)
    # A corrupt PNG/XML/Lottie must reach its own check; do not accidentally reject it only for an old digest.
    for row in [*manifest.get("icons", {}).values(), *manifest.get("transitions", {}).values()]:
        if isinstance(row, dict) and row.get("source") in assets:
            row["sha256"] = hashlib.sha256(assets[row["source"]]).hexdigest()
    data = raw(manifest) if raw else encoded(manifest)
    path = directory / (name + ".zip")
    with zipfile.ZipFile(path, "w", compression=compression) as archive:
        archive.writestr(prefix + "manifest.json", data)
        for source, content in assets.items():
            archive.writestr(prefix + source, content)
        if extra:
            extra(archive)
    if post:
        post(path)
    try:
        validate(path)
    except (ValueError, UnicodeError, OSError, ET.ParseError, zipfile.BadZipFile):
        if not reject:
            raise AssertionError("valid original package rejected: " + name)
        negatives += 1
    else:
        if reject:
            raise AssertionError("malformed package accepted: " + name)
    cases += 1


def change_animation(change):
    def mutate(manifest, assets):
        animation = json.loads(MOTION); change(animation); assets["assets/a.json"] = encoded(animation)
    return mutate


def change_xml(change):
    def mutate(manifest, assets):
        manifest["icons"]["wifi.1"]["source"] = "assets/a.xml"; assets["assets/a.xml"] = change(VECTOR)
    return mutate


def chunk(kind, body):
    return struct.pack(">I", len(body)) + kind + body + struct.pack(">I", zlib.crc32(kind + body) & 0xffffffff)


def freeze(value):
    if isinstance(value, dict):
        if value.get("a") == 1 and isinstance(value.get("k"), list):
            initial = next(frame["s"] for frame in value["k"] if "s" in frame)
            for frame in value["k"]:
                if "s" in frame: frame["s"] = initial
                if "e" in frame: frame["e"] = initial
        for child in value.values(): freeze(child)
    elif isinstance(value, list):
        for child in value: freeze(child)


def encrypt_headers(path):
    data = bytearray(path.read_bytes())
    for signature, delta in ((b"PK\x03\x04", 6), (b"PK\x01\x02", 8)):
        start = 0
        while (at := data.find(signature, start)) >= 0:
            data[at+delta] |= 1; start = at + 4
    path.write_bytes(data)


def link(archive):
    entry = zipfile.ZipInfo("assets/link.png"); entry.create_system = 3; entry.external_attr = 0o120777 << 16; archive.writestr(entry, b"a.png")


def self_extracting(path):
    original = path.read_bytes(); prefix = b"MZunsafe-executable-prefix"; data = bytearray(original)
    at = data.rfind(b"PK\x05\x06"); offset, = struct.unpack_from("<I", data, at+16); struct.pack_into("<I", data, at+16, offset+len(prefix))
    # Adjust local offsets too, so this is a genuinely readable SFX ZIP rather than a broken directory.
    start = 0
    while (at := data.find(b"PK\x01\x02", start)) >= 0:
        offset, = struct.unpack_from("<I", data, at+42); struct.pack_into("<I", data, at+42, offset+len(prefix)); start = at+46
    path.write_bytes(prefix+data)
    with zipfile.ZipFile(path) as archive:
        assert archive.testzip() is None, "negative SFX must remain a genuinely readable ZIP"


with tempfile.TemporaryDirectory(prefix="c17-v3-validator-") as temporary:
    directory = Path(temporary)
    for name, change, kwargs in [
        ("minimal", None, {}), ("outer-folder", None, {"prefix": "icons/"}),
        ("vector", change_xml(lambda data: data), {}),
        ("original-color", lambda m, a: m["icons"]["wifi.1"].update(render="color"), {}),
        ("safe-unknown-candidate", lambda m, a: m["icons"].update({"hint.new_service.default": {"source": "assets/a.png"}}), {}),
        ("numeric-exact-version", lambda m, a: m.update(version=3.0), {}),
    ]:
        case(directory, name, change, reject=False, **kwargs)
    manifest_cases = {
        "old-v2": lambda m, a: m.update(version=2), "boolean-version": lambda m, a: m.update(version=True),
        "old-root-render": lambda m, a: m.update(render="mask"), "native-class-field": lambda m, a: m.update(nativeClass="java.lang.Runtime"),
        "missing-fallback": lambda m, a: m.pop("fallback"), "empty-name": lambda m, a: m.update(name=" "),
        "missing-asset": lambda m, a: a.pop("assets/a.png"), "bad-known-state": lambda m, a: m["icons"].update({"wifi.5": {"source": "assets/a.png"}}),
        "fake-action-toggle": lambda m, a: m["icons"].update({"tile.alipay.on": {"source": "assets/a.png"}}),
        "old-string-asset": lambda m, a: m["icons"].update({"wifi.1": "assets/a.png"}),
        "unsupported-render": lambda m, a: m["icons"]["wifi.1"].update(render="native"),
        "missing-static-endpoint": lambda m, a: m["icons"].pop("tile.flashlight.off"),
        "wrong-transition-direction": lambda m, a: m["transitions"]["tile.flashlight.off_to_on"].update(to="off"),
        "animation-expression": change_animation(lambda data: data["layers"][0]["ks"]["p"].update(x="time*100")),
        "animation-image": change_animation(lambda data: data.update(assets=[{"id": "image", "p": "https://example.invalid/a.png"}])),
        "animation-text-layer": change_animation(lambda data: data["layers"][0].update(ty=5)),
        "animation-parent": change_animation(lambda data: data["layers"][0].update(parent=1)),
        "animation-long": change_animation(lambda data: data.update(op=60)),
        "animation-static-pretending": change_animation(freeze),
        "png-opaque": lambda m, a: a.update({"assets/a.png": picture(True)}),
        "png-dimension": lambda m, a: a.update({"assets/a.png": picture(width=1025)}),
        "png-trailing": lambda m, a: a.update({"assets/a.png": a["assets/a.png"] + b"trailing"}),
        "png-crc": lambda m, a: a.update({"assets/a.png": a["assets/a.png"][:-5] + bytes([a["assets/a.png"][-5] ^ 1]) + a["assets/a.png"][-4:]}),
        "apng": lambda m, a: a.update({"assets/a.png": a["assets/a.png"][:33] + chunk(b"acTL", struct.pack(">II", 1, 0)) + a["assets/a.png"][33:]}),
        "fake-png-bytes": lambda m, a: a.update({"assets/a.png": b"not a PNG"}),
        "unreferenced-bad-data": lambda m, a: a.update({"assets/hidden.json": b'{"expression":"danger"}'}),
    }
    for name, change in manifest_cases.items():
        case(directory, name, change)
    for name, change in {
        "xml-dtd": lambda x: b'<!DOCTYPE vector [<!ENTITY evil "x">]>' + x,
        "xml-reference": lambda x: x.replace(b"#ffffffff", b"@android:color/white"),
        "xml-svg": lambda x: x.replace(b"vector", b"svg"),
        "xml-script-node": lambda x: x.replace(b"</vector>", b"<script/></vector>"),
        "xml-negative-stroke": lambda x: x.replace(b"android:fillColor", b'android:strokeWidth="-1" android:fillColor'),
        "xml-alpha": lambda x: x.replace(b'android:width=', b'android:alpha="2" android:width='),
        "xml-nonfinite": lambda x: x.replace(b'viewportWidth="24"', b'viewportWidth="NaN"'),
        "xml-path-arity": lambda x: x.replace(b"M 3 3 L 20 3 L 12 20 Z", b"M 3 3 L 20"),
        "xml-arc-negative": lambda x: x.replace(b"M 3 3 L 20 3 L 12 20 Z", b"M 3 3 A -1 2 0 0 1 4 4"),
        "xml-deep": lambda x: x.replace(b"<path ", b"<group>"*9+b"<path ").replace(b"</vector>", b"</group>"*9+b"</vector>"),
    }.items():
        case(directory, name, change_xml(change))
    for name, raw in {
        "duplicate-json-key": lambda m: b'{"name":"duplicate",' + encoded(m)[1:],
        "json-nan": lambda m: encoded(m).replace(b'"version":3', b'"version":NaN'),
        "json-surrogate": lambda m: encoded(m).replace(b'"Check original"', b'"\\ud800"'),
        "wrong-sha": lambda m: encoded(m).replace(hashlib.sha256(ASSETS["assets/a.png"]).hexdigest().encode(), b"0"*64),
    }.items():
        case(directory, name, raw=raw)
    for name, extra in {
        "path-traversal": lambda zip: zip.writestr("../a.png", picture()),
        "duplicate-case": lambda zip: zip.writestr("assets/A.png", picture()),
        "nested-manifest": lambda zip: zip.writestr("other/manifest.json", b"{}"),
        "script-extra": lambda zip: zip.writestr("run.sh", b"echo unsafe"),
        "symlink": link,
        "single-file-limit": lambda zip: zip.writestr("assets/huge.png", b"x"*(1024*1024+1)),
    }.items():
        case(directory, name, extra=extra)
    case(directory, "nested-outer-folders", prefix="one/two/")
    case(directory, "encrypted", post=encrypt_headers)
    case(directory, "bzip2-not-supported", compression=zipfile.ZIP_BZIP2)
    case(directory, "zip-trailing-data", post=lambda path: path.write_bytes(path.read_bytes()+b"unsafe"))
    case(directory, "self-extracting-executable", post=self_extracting)
    for archive in (ROOT / "dist/c17-rounded-27.zip", ROOT / "dist/c17-rounded-27-png.zip"):
        result = validate(archive); assert result["icons"] == 177 and result["animations"] == 3; cases += 1

print(f"v3 validator checks passed: {cases}; malformed packages rejected: {negatives}; Android/OEM validation remains separate")
