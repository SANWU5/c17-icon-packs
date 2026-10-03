#!/usr/bin/env python3
"""Data-only ZIP verifier. Android remains authoritative for import and RAR decoding."""
import io
import json
from pathlib import PurePosixPath
import re
import sys
from zipfile import ZipFile
from PIL import Image


def validate(filename):
    with ZipFile(filename) as archive:
        entries = archive.infolist()
        if len(entries) > 256 or sum(e.file_size for e in entries) > 16 * 1024 * 1024:
            raise ValueError('归档文件数量或展开体积超出限制')
        names = set()
        for entry in entries:
            path = entry.filename
            if path in names or path.startswith('/') or '\\' in path or ':' in path or any(p in ('', '.', '..') for p in path.rstrip('/').split('/')):
                raise ValueError('不安全或重复路径：' + path)
            if entry.file_size > 1024 * 1024 or entry.flag_bits & 1:
                raise ValueError('文件过大或已加密：' + path)
            if (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('不允许符号链接：' + path)
            names.add(path)
        manifests = [p for p in names if p == 'manifest.json' or p.endswith('/manifest.json')]
        if len(manifests) != 1:
            raise ValueError('必须有且仅有一个 manifest.json')
        prefix = manifests[0][:-len('manifest.json')]
        if archive.getinfo(manifests[0]).file_size > 65536:
            raise ValueError('manifest 超过 64 KB')
        manifest = json.loads(archive.read(manifests[0]))
        if manifest.get('format') != 'c17-statusbar-icons' or type(manifest.get('version')) is not int or manifest['version'] != 1 or manifest.get('render', 'mask') != 'mask':
            raise ValueError('规范版本或 render 无效')
        for field, maximum in [('name', 64), ('author', 128), ('license', 128)]:
            value = manifest.get(field, '')
            if not isinstance(value, str) or len(value) > maximum or field != 'author' and not value.strip():
                raise ValueError(field + ' 无效')
        mapping = manifest.get('icons')
        if not isinstance(mapping, dict) or not 1 <= len(mapping) <= 128:
            raise ValueError('icons 无效')
        for key, asset in mapping.items():
            if not re.fullmatch(r'hint\.[a-z][a-z0-9_]{0,47}(?:\.(?:on|off))?|(?:wifi|cellular)\.(?:[0-4]|none)|battery\.(?:charging\.)?(?:0|[1-9]0|100)', key) or not isinstance(asset, str) or not re.fullmatch(r'assets/[a-zA-Z0-9][a-zA-Z0-9_-]{0,63}\.(png|webp)', asset):
                raise ValueError('标识或资源路径无效：' + key)
            with Image.open(io.BytesIO(archive.read(prefix + asset))) as image:
                if image.format not in ('PNG', 'WEBP') or max(image.size) > 1024 or min(image.size) < 1:
                    raise ValueError('图片格式或尺寸无效：' + asset)
                if 'A' not in image.getbands() and 'transparency' not in image.info:
                    raise ValueError('图片缺少透明通道：' + asset)
        for family, states in [('wifi.', ['none', *map(str, range(5))]), ('cellular.', ['none', *map(str, range(5))]), ('battery.', list(map(str, range(0, 101, 10)))), ('battery.charging.', list(map(str, range(0, 101, 10))))]:
            if any(k.startswith(family) for k in mapping) and any(family + state not in mapping for state in states):
                raise ValueError('缺少系列状态：' + family)
        print('通过：', manifest['name'], len(mapping), '个图标；未执行 Android/RAR/SystemUI 测试')


if __name__ == '__main__':
    validate(sys.argv[1])
