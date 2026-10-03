#!/usr/bin/env python3
"""Generate original teaching masks, not extracted OEM/PUI assets. Requires Pillow."""
import json
from pathlib import Path
from zipfile import ZipFile, ZIP_DEFLATED
from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]
SLOTS = 'bluetooth location alarm_clock zen volume hotspot headset rotate vpn nfc cast screen_record microphone camera privacy_call usb hd airplane'.split()
WHITE = (255, 255, 255, 255)


def icon(painter):
    canvas = Image.new('RGBA', (512, 512))
    painter(ImageDraw.Draw(canvas))
    return canvas.resize((128, 128), Image.Resampling.LANCZOS)


def hint(slot):
    def paint(d):
        if slot == 'bluetooth':
            d.line([(240, 64), (368, 174), (128, 360), (240, 448), (240, 64), (368, 338), (128, 152)], fill=WHITE, width=36, joint='curve')
        elif slot == 'location':
            d.ellipse((116, 56, 396, 336), outline=WHITE, width=32)
            d.line([(124, 254), (256, 448), (388, 254)], fill=WHITE, width=32, joint='curve')
            d.ellipse((204, 144, 308, 248), outline=WHITE, width=28)
        elif slot == 'alarm_clock':
            d.ellipse((92, 108, 420, 436), outline=WHITE, width=32)
            d.line([(256, 166), (256, 272), (330, 316)], fill=WHITE, width=30, joint='curve')
            d.arc((48, 44, 228, 180), 190, 290, fill=WHITE, width=32)
            d.arc((284, 44, 464, 180), 250, 350, fill=WHITE, width=32)
        else:
            # Each hint uses a different simple mask to make layered fallback easy to inspect.
            n = SLOTS.index(slot)
            d.rounded_rectangle((96, 96, 416, 416), radius=48, outline=WHITE, width=30)
            for i in range(n % 4 + 1):
                x = 162 + i * 60
                d.line([(x, 176), (x, 336)], fill=WHITE, width=24)
    return icon(paint)


def wifi(level):
    def paint(d):
        for i, box in enumerate([(204, 276, 308, 364), (140, 208, 372, 410), (72, 136, 440, 472), (8, 64, 504, 536)]):
            if i < level:
                d.arc(box, 226, 314, fill=WHITE, width=34)
        d.ellipse((235, 348, 277, 390), fill=WHITE)
    return icon(paint)


def cellular(level):
    def paint(d):
        for i in range(4):
            x = 76 + i * 98
            d.rounded_rectangle((x, 336 - i * 78, x + 52, 432), radius=18, outline=WHITE, width=12)
            if i < level:
                d.rounded_rectangle((x, 336 - i * 78, x + 52, 432), radius=18, fill=WHITE)
    return icon(paint)


def none(base):
    result = base.copy()
    overlay = Image.new('RGBA', (512, 512))
    draw = ImageDraw.Draw(overlay)
    draw.line((84, 84, 428, 428), fill=WHITE, width=32)
    result.alpha_composite(overlay.resize((128, 128), Image.Resampling.LANCZOS))
    return result


def battery(level, charging=False):
    def paint(d):
        d.rounded_rectangle((52, 148, 434, 364), radius=38, outline=WHITE, width=26)
        d.rounded_rectangle((444, 218, 472, 294), radius=10, fill=WHITE)
        width = int(314 * level / 100)
        if width:
            d.rounded_rectangle((86, 182, 86 + width, 330), radius=min(18, width / 2), fill=WHITE)
        # Native percentage/charging indicator stays on top; never bake text or a bolt into the mask.
    return icon(paint)


def build(name, complete):
    folder = ROOT / 'examples' / name
    assets = folder / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    mapping = {}
    def add(key, filename, image):
        image.save(assets / filename)
        mapping[key] = 'assets/' + filename
    for slot in SLOTS if complete else ['bluetooth', 'location']:
        add('hint.' + slot, slot + '.png', hint(slot))
    if complete:
        for level in range(5):
            add(f'wifi.{level}', f'wifi-{level}.png', wifi(level))
            add(f'cellular.{level}', f'cellular-{level}.png', cellular(level))
        add('wifi.none', 'wifi-none.png', none(wifi(4)))
        add('cellular.none', 'cellular-none.png', none(cellular(0)))
        for level in range(0, 101, 10):
            add(f'battery.{level}', f'battery-{level}.png', battery(level))
            add(f'battery.charging.{level}', f'charging-{level}.png', battery(level, True))
    manifest = dict(format='c17-statusbar-icons', version=1, name='完整线条教学示例' if complete else '蓝牙定位教学示例', author='aiingjie', license='MIT', render='mask', icons=mapping)
    (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (folder / 'LICENSE.txt').write_bytes((ROOT / 'LICENSE').read_bytes())
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    destination = dist / ('icon-pack.zip' if complete else 'hints-only.zip')
    with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(folder).as_posix())
    print(destination, len(mapping), 'roles')


def build_partial():
    """An original v2 example deliberately omits every other Wi-Fi level."""
    folder = ROOT / 'examples' / 'partial-native'
    assets = folder / 'assets'
    assets.mkdir(parents=True, exist_ok=True)
    wifi(4).save(assets / 'wifi-4.png')
    hint('location').save(assets / 'location.png')
    manifest = dict(format='c17-statusbar-icons', version=2, fallback='native',
                    name='部分状态原生回退教学示例', author='aiingjie', license='MIT',
                    render='mask', icons={'wifi.4': 'assets/wifi-4.png',
                                         'hint.location': 'assets/location.png'})
    (folder / 'manifest.json').write_text(json.dumps(manifest, ensure_ascii=False, indent=2) + '\n', encoding='utf-8')
    (folder / 'LICENSE.txt').write_bytes((ROOT / 'LICENSE').read_bytes())
    dist = ROOT / 'dist'
    dist.mkdir(exist_ok=True)
    destination = dist / 'partial-native.zip'
    with ZipFile(destination, 'w', ZIP_DEFLATED) as archive:
        for path in sorted(folder.rglob('*')):
            if path.is_file():
                archive.write(path, path.relative_to(folder).as_posix())
    print(destination, len(manifest['icons']), 'roles')


if __name__ == '__main__':
    build('minimal-hints', False)
    build('complete-outline', True)
    build_partial()
