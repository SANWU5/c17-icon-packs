#!/usr/bin/env python3
# SPDX-License-Identifier: MIT
# Copyright (c) 2026 aiingjie
"""Bounded, data-only v3 ZIP preflight. Android production admission is authoritative.

Checks actual ZIP entries, strict JSON, PNG CRC/transparency, restricted vector
geometry, Lottie shape/keyframe budgets, exact static endpoints and SHA-256.
It neither inflates Android Drawables nor runs RAR JNI, OEM parsers or scripts.
"""
from __future__ import annotations
import argparse
from decimal import Decimal
import hashlib
import io
import json
import math
from pathlib import Path
import re
import struct
import sys
import unicodedata
import xml.etree.ElementTree as ET
import zipfile
import zlib
from PIL import Image

ROOT = Path(__file__).resolve().parents[1]
ROLE = re.compile(r"(?:hint|wifi|cellular|battery|tile|slider|media|device|footer)(?:\.[a-z0-9][a-z0-9_]{0,47}){1,5}")
ASSET = re.compile(r"assets/[A-Za-z0-9][A-Za-z0-9_-]{0,95}\.(?:png|xml|json)")
HASH = re.compile(r"[0-9a-f]{64}")
NUMBER = re.compile(r"[-+]?(?:[0-9]+(?:\.[0-9]*)?|\.[0-9]+)(?:[eE][-+]?[0-9]+)?")
A = "{http://schemas.android.com/apk/res/android}"
MIB = 1024 * 1024


def need(condition, message):
    if not condition:
        raise ValueError(message)


def obj(value):
    need(isinstance(value, dict), "需要 JSON 对象")
    return value


def array(value):
    need(isinstance(value, list), "需要 JSON 数组")
    return value


def only(value, keys):
    need(not (set(obj(value)) - set(keys.split())), "不支持的字段：" + ",".join(sorted(set(value) - set(keys.split()))))


def bounded(value, minimum, maximum, integral=False):
    need(type(value) in (int, float, Decimal), "需要有限数值")
    need(math.isfinite(value) and minimum <= value <= maximum, "数值越界")
    if integral:
        need(value == int(value), "需要精确整数")
    return value


def text(value, maximum, required=False):
    need(isinstance(value, str) and len(value.encode("utf-16-le")) // 2 <= maximum, "文本长度或类型无效")
    need(not any(unicodedata.category(c) == "Cc" for c in value), "文本包含控制字符")
    need(not required or bool(value.strip()), "必填文本为空")
    return value.strip()


def strict_json(data, limit):
    need(0 < len(data) <= limit, "JSON 字节超限")
    def pairs(rows):
        result = {}
        for key, value in rows:
            need(key not in result, "JSON 重复字段：" + key)
            result[key] = value
        return result
    def number(token):
        need(len(token) <= 64, "JSON 数值过长")
        value = Decimal(token)
        need(math.isfinite(value) and abs(value.as_tuple().exponent) <= 1024, "JSON 数值超限")
        return value
    def constant(token):
        raise ValueError("JSON 不接受 " + token)
    value = json.loads(data.decode("utf-8", errors="strict"), object_pairs_hook=pairs,
                       parse_int=number, parse_float=number, parse_constant=constant)
    nodes = 0
    def walk(item, depth):
        nonlocal nodes
        nodes += 1
        need(nodes <= 16384 and depth <= 24, "JSON 深度或节点超限")
        if isinstance(item, str):
            item.encode("utf-8", errors="strict")
            need(len(item.encode("utf-16-le")) // 2 <= 65536, "JSON 字符串超限")
        elif isinstance(item, dict):
            for key, child in item.items():
                walk(key, depth); walk(child, depth + 1)
        elif isinstance(item, list):
            for child in item:
                walk(child, depth + 1)
    walk(value, 0)
    return obj(value)


def known_roles():
    rows = json.loads((ROOT / "roles.json").read_text("utf-8"))
    return {row["role"] for row in rows}, {row["target"] for row in rows}


def role_valid(role, known, targets):
    need(isinstance(role, str) and len(role) <= 128 and ROLE.fullmatch(role), "角色语法无效：" + str(role))
    target = max((target for target in targets if role.startswith(target + ".")), key=len, default=None)
    need(target is None or role in known or (target == role and target.startswith("hint.")), "已登记目标含非法状态：" + role)


def png(data):
    need(45 <= len(data) <= MIB and data[:8] == b"\x89PNG\r\n\x1a\n", "需要真实 PNG")
    at, chunks, width, height, idat, ended = 8, 0, 0, 0, False, False
    clean = bytearray(data[:8])
    while at < len(data):
        chunks += 1
        need(chunks <= 1024 and at + 12 <= len(data), "PNG 块超限或截断")
        length, = struct.unpack_from(">I", data, at)
        end = at + 12 + length
        need(end <= len(data), "PNG 块截断")
        kind = data[at + 4:at + 8]
        need(re.fullmatch(b"[A-Za-z]{4}", kind) and kind not in (b"acTL", b"fcTL", b"fdAT"), "拒绝 APNG 或非法 PNG 块")
        expected, = struct.unpack_from(">I", data, end - 4)
        need(zlib.crc32(data[at + 4:end - 4]) & 0xffffffff == expected, "PNG CRC 错误")
        if chunks == 1:
            need(kind == b"IHDR" and length == 13, "PNG 缺少正确 IHDR")
            width, height = struct.unpack_from(">II", data, at + 8)
            need(1 <= width <= 1024 and 1 <= height <= 1024, "PNG 尺寸超限")
        else:
            need(kind != b"IHDR", "PNG IHDR 重复")
        idat |= kind == b"IDAT"
        if kind == b"IEND":
            need(length == 0 and idat and end == len(data), "PNG IEND 无效或存在尾随数据")
            ended = True
        need(not 65 <= kind[0] <= 90 or kind in (b"IHDR", b"PLTE", b"IDAT", b"IEND"), "PNG 未知关键块")
        if kind in (b"IHDR", b"PLTE", b"IDAT", b"IEND", b"tRNS"):
            clean.extend(data[at:end])
        at = end
    need(ended, "PNG 缺少 IEND")
    with Image.open(io.BytesIO(clean)) as image:
        image.load()
        need(image.format == "PNG" and image.size == (width, height), "PNG 无法解码")
        need("A" in image.getbands() or "transparency" in image.info, "PNG 缺少 Alpha")
        need(image.convert("RGBA").getchannel("A").getextrema()[0] < 255, "PNG 未含透明背景")


def vector_path(data):
    need(data and len(data) <= 65536, "矢量路径为空或超限")
    at, command, commands, numbers, args = 0, None, 0, 0, []
    def check():
        if command is None:
            return
        kind = command.upper()
        arity = {"Z": 0, "H": 1, "V": 1, "M": 2, "L": 2, "T": 2, "S": 4, "Q": 4, "C": 6, "A": 7}[kind]
        need(not args if arity == 0 else args and len(args) % arity == 0, "路径参数数量无效")
        if kind == "A":
            for i in range(0, len(args), 7):
                need(args[i] >= 0 and args[i+1] >= 0 and args[i+3] in (0, 1) and args[i+4] in (0, 1), "弧线半径或标记无效")
    while at < len(data):
        c = data[at]
        if c.isspace() or c == ",":
            at += 1; continue
        if c in "MmLlHhVvCcSsQqTtAaZz":
            check(); need(command is not None or c in "Mm", "路径须以 M 开始")
            command, args = c, []; commands += 1; at += 1
            need(commands <= 2048, "路径命令超限"); continue
        need(command is not None, "路径命令缺失")
        number = NUMBER.match(data, at)
        need(number is not None, "路径命令或数值无效")
        value = float(number.group()); numbers += 1
        need(math.isfinite(value) and abs(value) <= 4096 and numbers <= 8192, "路径数值或数量超限")
        args.append(value); at = number.end()
    check()


def vector(data):
    need(0 < len(data) <= 128 * 1024, "XML 大小超限")
    source = data.decode("utf-8", errors="strict")
    need("&" not in source and not re.search(r"<!\s*(?:DOCTYPE|ENTITY)|<\?(?!xml(?:\s|\?))", source, re.I), "XML 禁止实体、DTD、处理指令")
    root = ET.fromstring(source)
    need(root.tag == "vector", "XML 根须为 vector")
    count, path_chars = 0, 0
    def numeric(attrs, key, default, low, high):
        value = float(attrs.get(key, default)); bounded(value, low, high)
    def node(element, depth):
        nonlocal count, path_chars
        count += 1
        need(count <= 128 and depth < 8 and element.tag in ("vector", "group", "path", "clip-path"), "XML 节点/层级/标签无效")
        need(element is root or element.tag != "vector", "XML 不允许嵌套 vector")
        need(not element.text or not element.text.strip(), "XML 不允许文字内容")
        attrs = {}
        for key, value in element.attrib.items():
            need(key.startswith(A) and "@" not in value and "?" not in value, "XML 属性命名空间或引用无效")
            attrs[key[len(A):]] = value
        allowed = {"vector": "width height viewportWidth viewportHeight alpha name", "group": "rotation pivotX pivotY scaleX scaleY translateX translateY name", "clip-path": "pathData fillType name", "path": "pathData fillColor fillAlpha strokeColor strokeAlpha strokeWidth strokeLineCap strokeLineJoin strokeMiterLimit fillType name"}
        need(not set(attrs) - set(allowed[element.tag].split()), "XML 未知属性")
        need(len(attrs.get("name", "")) <= 64, "XML 名称超长")
        if element.tag == "vector":
            for key in ("width", "height"):
                if key in attrs:
                    value = float(re.sub(r"(?:dp|px)$", "", attrs[key])); bounded(value, 0, 1024); need(value > 0, "XML 固有尺寸须为正")
            numeric(attrs, "viewportWidth", "nan", 1, 1024); numeric(attrs, "viewportHeight", "nan", 1, 1024); numeric(attrs, "alpha", 1, 0, 1)
        elif element.tag == "group":
            for key in "rotation pivotX pivotY scaleX scaleY translateX translateY".split():
                numeric(attrs, key, 1 if key.startswith("scale") else 0, -4096, 4096)
        else:
            need("pathData" in attrs and len(element) == 0, "XML 路径缺失或含子节点")
            path_chars += len(attrs["pathData"]); need(path_chars <= 65536, "XML 路径总长度超限"); vector_path(attrs["pathData"])
            need(attrs.get("fillType", "nonZero") in ("nonZero", "evenOdd"), "XML fillType 无效")
            if element.tag == "path":
                for key in ("fillColor", "strokeColor"):
                    need(key not in attrs or re.fullmatch(r"#[0-9a-fA-F]{8}", attrs[key]), "XML 颜色须为 #AARRGGBB")
                for key in ("fillAlpha", "strokeAlpha"):
                    numeric(attrs, key, 1, 0, 1)
                numeric(attrs, "strokeWidth", 0, 0, 4096); numeric(attrs, "strokeMiterLimit", 4, 1, 64)
                need(attrs.get("strokeLineCap", "butt") in ("butt", "round", "square"), "XML lineCap 无效")
                need(attrs.get("strokeLineJoin", "miter") in ("miter", "round", "bevel"), "XML lineJoin 无效")
        for child in element:
            need(element.tag in ("vector", "group") and (not child.tail or not child.tail.strip()), "XML 子节点结构无效")
            node(child, depth + 1)
    node(root, 0)


def animation(data, transient=False):
    root = strict_json(data, 256 * 1024)
    only(root, "v w h fr ip op layers assets nm ddd markers")
    need(isinstance(root.get("v"), str) and re.fullmatch(r"[0-9]+(?:\.[0-9]+){1,3}", root["v"]), "Lottie 版本无效")
    bounded(root.get("w"), 1, 256, True); bounded(root.get("h"), 1, 256, True)
    fps = bounded(root.get("fr"), 1, 60); start = bounded(root.get("ip"), 0, 100000); end = bounded(root.get("op"), 0, 100000)
    need(end > start and (end-start)*1000/fps <= (1500 if transient else 800) + Decimal(".001"), "Lottie 时长超限")
    need(root.get("ddd", 0) == 0 and not array(root.get("assets", [])) and not array(root.get("markers", [])), "Lottie 禁止外部资源、3D 和标记")
    budget = {"shapes": 0, "frames": 0, "vertices": 0, "changes": 0}
    def point(value, kind="point"):
        values = array(value); need(len(values) in (2, 3) and (kind != "size" or len(values) == 2), "动画坐标维度无效")
        for v in values[:2]: bounded(v, 0 if kind == "size" else -4096, 4096)
        if len(values) == 3: bounded(values[2], 100 if kind == "scale" else 0, 100 if kind == "scale" else 0)
    def value(raw, kind):
        if kind in ("scalar", "nonneg", "opacity"):
            bounded(raw, -4096 if kind == "scalar" else 0, 100 if kind == "opacity" else 4096)
        elif kind in ("point", "size", "scale"):
            point(raw, kind)
        elif kind == "color":
            need(len(array(raw)) in (3, 4), "动画颜色维度无效")
            for channel in raw: bounded(channel, 0, 1)
        else:
            only(raw, "i o v c"); need(type(raw.get("c")) is bool, "动画路径 c 无效")
            vertices = array(raw.get("v")); incoming = array(raw.get("i")); outgoing = array(raw.get("o")); budget["vertices"] += len(vertices)
            need(1 <= len(vertices) <= 512 and len(vertices) == len(incoming) == len(outgoing) and budget["vertices"] <= 2048, "动画路径顶点超限或不匹配")
            for points in (vertices, incoming, outgoing):
                for coordinate in points:
                    need(len(array(coordinate)) == 2, "动画路径须二维"); point(coordinate)
    def prop(raw, kind):
        only(raw, "a k ix"); mode = bounded(raw.get("a", 0), 0, 1, True)
        if "ix" in raw: bounded(raw["ix"], 0, 65535, True)
        if mode == 0: value(raw.get("k"), kind); return
        frames = array(raw.get("k")); need(2 <= len(frames) <= 64, "动画关键帧数量无效")
        last, first, changed = -math.inf, None, False
        for index, frame in enumerate(frames):
            only(frame, "t s e i o h to ti"); budget["frames"] += 1; need(budget["frames"] <= 256, "动画关键帧总量超限")
            moment = bounded(frame.get("t"), start, end); need(moment > last, "动画时间须严格递增"); last = moment
            need("s" in frame or index == len(frames)-1, "动画关键帧缺起值")
            for key in ("s", "e"):
                if key not in frame: continue
                raw_value = frame[key]
                if kind in ("scalar", "nonneg", "opacity", "path"):
                    need(len(array(raw_value)) == 1, "关键帧值维度无效"); value(raw_value[0], kind)
                else: value(raw_value, kind)
                if first is None: first = raw_value
                elif first != raw_value: changed = True
            if "h" in frame: bounded(frame["h"], 0, 1, True)
            for key in ("i", "o"):
                if key in frame:
                    only(frame[key], "x y")
                    for axis, low, high in (("x", 0, 1), ("y", -16, 16)):
                        ease = frame[key].get(axis); values = ease if isinstance(ease, list) else [ease]; need(1 <= len(values) <= 4, "缓动参数数量无效")
                        for item in values: bounded(item, low, high)
            for key in ("to", "ti"):
                if key in frame: point(frame[key])
        budget["changes"] += int(changed)
    def transform(raw, shape=False):
        only(raw, ("ty nm hd " if shape else "") + "a p s r o sk sa")
        for key in "a p s r o sk sa".split():
            if key in raw: prop(raw[key], "point" if key in ("a", "p") else "scale" if key == "s" else "opacity" if key == "o" else "scalar")
    def shapes(rows, depth):
        need(depth <= 8 and array(rows), "动画形状层级为空或超限")
        for shape in rows:
            budget["shapes"] += 1; need(budget["shapes"] <= 256, "动画形状数量超限"); obj(shape)
            kind = shape.get("ty"); allowed = {"gr": "it np cix bm", "sh": "ks ind d", "fl": "c o r bm", "st": "c o w lc lj ml bm", "tr": "a p s r o sk sa", "el": "p s d", "rc": "p s r d"}
            need(kind in allowed, "不支持的 Lottie 形状：" + str(kind)); only(shape, "ty nm hd " + allowed[kind])
            if "nm" in shape: text(shape["nm"], 128)
            if "hd" in shape: need(type(shape["hd"]) is bool, "动画 hd 类型无效")
            if "bm" in shape: bounded(shape["bm"], 0, 0)
            if "d" in shape: bounded(shape["d"], 1, 3, True)
            if kind == "gr":
                for key in ("np", "cix"):
                    if key in shape: bounded(shape[key], 0, 256, True)
                shapes(shape.get("it"), depth + 1)
            elif kind == "sh":
                if "ind" in shape: bounded(shape["ind"], 0, 65535, True)
                prop(shape.get("ks"), "path")
            elif kind in ("fl", "st"):
                prop(shape.get("c"), "color"); prop(shape.get("o"), "opacity")
                if kind == "fl":
                    if "r" in shape: bounded(shape["r"], 1, 2, True)
                else:
                    prop(shape.get("w"), "nonneg")
                    for key in ("lc", "lj"):
                        if key in shape: bounded(shape[key], 1, 3, True)
                    if "ml" in shape: bounded(shape["ml"], 1, 64)
            elif kind == "tr": transform(shape, True)
            else:
                prop(shape.get("p"), "point"); prop(shape.get("s"), "size")
                if kind == "rc": prop(shape.get("r"), "nonneg")
    indices = set(); layers = array(root.get("layers")); need(1 <= len(layers) <= 16, "动画 layer 数量超限")
    for layer in layers:
        only(layer, "ddd ind ty nm ks ao shapes ip op st sr bm hd"); bounded(layer.get("ty"), 4, 4, True)
        for key in ("ddd", "ao", "bm", "st"):
            if key in layer: bounded(layer[key], 0, 0)
        if "sr" in layer: bounded(layer["sr"], 1, 1)
        index = bounded(layer.get("ind"), 0, 65535, True); need(index not in indices, "动画 layer ind 重复"); indices.add(index)
        need(bounded(layer.get("op", end), start, end) > bounded(layer.get("ip", start), start, end), "动画 layer 时间范围无效")
        if "nm" in layer: text(layer["nm"], 128)
        if "hd" in layer: need(type(layer["hd"]) is bool, "动画 hd 类型无效")
        transform(layer.get("ks")); shapes(layer.get("shapes"), 0)
    need(budget["changes"] > 0, "静态或无变化关键帧不能冒充动画")


def archive_entries(path):
    need(0 < path.stat().st_size <= 24 * MIB, "归档须为 1 字节至 24 MiB")
    data = path.read_bytes()
    need(data[:2] == b"PK", "只接受ZIP数据，不接受带可执行前缀的自解压文件")
    end = next((at for at in range(len(data)-22, max(-1, len(data)-65558), -1) if data[at:at+4] == b"PK\x05\x06" and at+22+struct.unpack_from("<H", data, at+20)[0] == len(data)), None)
    need(end is not None, "需要完整 ZIP；RAR 请交 Android 生产导入器")
    disk, central_disk, count_here, count, size, offset = struct.unpack_from("<HHHHII", data, end+4)
    need(disk == central_disk == 0 and count_here == count and count <= 1024 and count != 65535 and offset+size == end, "ZIP 分卷/ZIP64/数量/目录范围无效")
    at = offset
    for _ in range(count):
        need(at+46 <= end and data[at:at+4] == b"PK\x01\x02", "ZIP 中央目录截断")
        flags, method = struct.unpack_from("<HH", data, at+8); uncompressed, = struct.unpack_from("<I", data, at+24)
        name_size, extra_size, comment_size, disk_start = struct.unpack_from("<HHHH", data, at+28); attributes, = struct.unpack_from("<I", data, at+38)
        need(not flags & 1 and method in (0, 8) and uncompressed <= MIB and disk_start == 0 and (attributes >> 16) & 0o170000 in (0, 0o100000, 0o040000), "ZIP 加密/特殊文件/压缩方法/大小不受支持")
        at += 46 + name_size + extra_size + comment_size; need(at <= end, "ZIP 中央目录越界")
    need(at == end, "ZIP 中央目录大小不匹配")
    entries, names, total = {}, set(), 0
    with zipfile.ZipFile(io.BytesIO(data)) as archive:
        need(len(archive.infolist()) == count, "ZIP 条目计数不匹配")
        for entry in archive.infolist():
            name = entry.orig_filename; normalized = name[:-1] if entry.is_dir() and name.endswith("/") else name
            need(0 < len(name) <= 192 and not name.startswith("/") and not any(c in name for c in "\\:") and not any(unicodedata.category(c) == "Cc" for c in name) and all(part not in ("", ".", "..") for part in normalized.split("/")), "ZIP 路径无效")
            need(normalized.lower() not in names, "ZIP 重复或大小写冲突路径"); names.add(normalized.lower())
            if not entry.is_dir():
                with archive.open(entry) as stream: content = stream.read(MIB+1)
                need(len(content) <= MIB, "ZIP 资源展开超限"); total += len(content); need(total <= 48*MIB, "ZIP 展开总量超限"); entries[name] = content
    manifests = [name for name in entries if name == "manifest.json" or name.endswith("/manifest.json")]
    need(len(manifests) == 1, "须恰好有一个 manifest.json"); prefix = manifests[0][:-13]
    need(not prefix or prefix.count("/") == 1, "只允许一层包外目录")
    result = {}
    for name, content in entries.items():
        need(name.startswith(prefix), "包外不能有额外文件"); name = name[len(prefix):]
        need(name == "manifest.json" or ASSET.fullmatch(name) or name in ("LICENSE", "LICENSE.txt", "LICENSE.md", "README.md"), "包内不支持文件：" + name)
        limit = 256*1024 if name == "manifest.json" or name.endswith(".json") else 128*1024 if name.endswith(".xml") else MIB if name.startswith("assets/") else 64*1024
        need(len(content) <= limit, "文件大小超限：" + name); result[name] = content
    return result


def validate(path):
    entries = archive_entries(Path(path)); manifest = strict_json(entries["manifest.json"], 256*1024)
    need("fit" not in manifest, "fit 只能写在单个图标上，不能写在包的顶层")
    only(manifest, "format version id name author license fallback icons transitions")
    need(manifest.get("format") == "c17-statusbar-icons" and type(manifest.get("version")) is Decimal and manifest["version"] == 3 and manifest.get("fallback") == "native", "需要 version=3、fallback=native")
    pack_id = text(manifest.get("id"), 64, True); need(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", pack_id), "包 id 无效")
    text(manifest.get("name"), 64, True); text(manifest.get("author", ""), 128); text(manifest.get("license"), 128, True)
    icons = obj(manifest.get("icons")); need(1 <= len(icons) <= 512, "图案数须为 1–512")
    known, targets = known_roles(); refs, transitions = {}, obj(manifest.get("transitions", {})); need(len(transitions) <= 128, "动画数超过 128")
    def reference(row, static):
        only(row, "source render fit sha256" if static else "source from to reversible sha256")
        source = row.get("source"); need(isinstance(source, str) and ASSET.fullmatch(source) and source.endswith((".png", ".xml") if static else ".json"), "资源路径或扩展名无效")
        need(source in entries, "缺少资源：" + source)
        if "sha256" in row:
            declared = row["sha256"]; need(isinstance(declared, str) and (not declared or HASH.fullmatch(declared)), "资源摘要格式无效")
            need(not declared or declared == hashlib.sha256(entries[source]).hexdigest(), "资源 SHA-256 不匹配")
        return source
    for role, row in icons.items():
        role_valid(role, known, targets); reference(row, True); need(row.get("render", "mask") in ("mask", "color"), "render 无效")
        # Spec 3.1: "canvas" maps the whole canvas onto the system icon box; "visible" (or no fit) is the 3.0 crop-and-fill rule.
        need(row.get("fit", "visible") in ("canvas", "visible"), "fit 只能是 canvas 或 visible")
    for key, row in transitions.items():
        target, _, kind = key.rpartition("."); need(target.startswith("tile.") and ROLE.fullmatch(target+".on") and kind in ("off_to_on", "on_to_off", "transient"), "动画目标/类型无效")
        source = reference(row, False); to = row.get("to"); start = row.get("from"); reversible = row.get("reversible", False); need(type(reversible) is bool and to in ("on", "off"), "动画末态/反播字段无效")
        need((start == "transient" and not reversible) if kind == "transient" else kind == str(start)+"_to_"+str(to) and start != to, "动画 from/to 与名称不一致")
        need(target+'.'+to in icons and (kind == "transient" or target+'.'+start in icons), "动画必须有精确静态端点")
        refs[source] = kind == "transient" and refs.get(source, True)
    # Validate every asset, including unreferenced data: no hidden executable or unsafe payload.
    for name, data in entries.items():
        if not name.startswith("assets/"): continue
        if name.endswith(".png"): png(data)
        elif name.endswith(".xml"): vector(data)
        else: animation(data, refs.get(name, False))
    return {"name": manifest["name"], "icons": len(icons), "animations": len(transitions), "unknown_roles": sum(role not in known and role not in targets for role in icons), "sha256": hashlib.sha256(Path(path).read_bytes()).hexdigest()}


def main():
    if hasattr(sys.stdout, "reconfigure"):
        sys.stdout.reconfigure(encoding="utf-8"); sys.stderr.reconfigure(encoding="utf-8")
    parser = argparse.ArgumentParser(description=__doc__); parser.add_argument("archives", nargs="+", type=Path); args = parser.parse_args()
    for path in args.archives:
        try:
            report = validate(path); print(f"通过：{path}: {report['icons']} 静态 / {report['animations']} 动态声明 / {report['unknown_roles']} 未登记候选；SHA-256 {report['sha256']}")
        except (ValueError, OSError, KeyError, TypeError, RecursionError, zipfile.BadZipFile, ET.ParseError, struct.error, UnicodeError) as failure:
            parser.exit(1, f"拒绝：{path}: {failure}\n")
    print("仅桌面 ZIP 预检通过；Android 严格生产导入、RAR JNI、OEM 视觉及实际动画播放另验。")


if __name__ == "__main__":
    main()
