# C17 图标管理 v3

适用于 **C17 1.8.3-beta.95 / code188 测试版**的图标管理 v3。v3 包格式与 beta94/code187 相同；下文的可见高度归一、总开关和预览流程以 beta95/code188 为准，不能据此推定旧版行为。规范与源码接入不代表全部功能已通过手机视觉验收。旧 v1/v2 包不能直接用于新版。主模块：[c17-statusbar](https://github.com/SANWU5/c17-statusbar)。历史规范已移至 [docs/legacy](docs/legacy/README.md)。

本仓库只收录规范、制作工具和原创资源。没有PUI图案、用户主题、原始OEM APK、反汇编代码、手机截图或用户配置，也不提供旧主题导入功能。

## C17示例库与操作

- [C17示例库 · XML主包](dist/c17-rounded-27.zip)：177个登记静态角色、3个纯图形短转场声明。
- [96px PNG备用包](dist/c17-rounded-27-png.zip)：相同原创几何和状态。
- [浅深色接触表](dist/contact-sheet.png)、[角色快照](roles.json)、[制作报告与SHA-256](dist/report.json)。

图案由圆、线、圆角矩形及贝塞尔曲线原创制作，没有临摹Apple、SF Symbols、OEM或PUI。支付和助手入口使用原创功能符号，不复制服务商Logo。

**C17示例库是格式与角色制作示例，不是 iOS 27、Apple 或 SF Symbols 原版素材。** 文件路径与包内 `id` 中的 `c17-rounded-27` 是兼容标记，不代表 Apple 版本或素材来源。

App入口为 **其他 → 图标管理**，首页分“选套装”和“自定义”。导入或下载先暂存预览，选择范围并查看缺项后应用；取消暂存不入库、不改效果。高级选项也可“仅加入图标库”，供稍后自定义选取。单个目标可选择系统默认或具体图案，再按需设置颜色、透明度、逐状态与动画。总开关关闭后保留已保存的选择并恢复系统或功能默认图案；关闭时保存选择不会自动启用总开关。删除来源后受影响图案回退，独立颜色和透明度保留。

角色明确“系统默认”优先；其他情况依次尝试明确单项来源、所选范围套装中的同一角色、原生。不借另一档信号、普通电池或另一开关状态。包不改变原生开关、系统隐藏条件、点击、无障碍、位置或布局。

## 文件格式

ZIP内恰好一个`manifest.json`，位于根目录或统一的一层外部文件夹中。建议发布独立ZIP，整个规范仓库含多个历史示例，不能作为一个图标包导入。

本页两个 `dist` ZIP 可单独下载后从文件导入。App“从 GitHub 导入”按仓库寻找 Release 资源 `icon-pack-v3.zip`；仅把规范和 `dist` 文件推送到仓库，不会自动生成这个 Release 资源，也不表示整个源码仓库可导入。

```text
manifest.json
assets/bluetooth-on.xml
assets/wifi-4.png
LICENSE.txt
README.md
```

```json
{
  "format": "c17-statusbar-icons",
  "version": 3,
  "id": "my-original-icons",
  "name": "我的原创图标",
  "author": "作者",
  "license": "MIT",
  "fallback": "native",
  "icons": {
    "hint.bluetooth.on": {"source": "assets/bluetooth-on.xml", "render": "mask"},
    "wifi.4": {"source": "assets/wifi-4.png", "render": "color"}
  },
  "transitions": {}
}
```

`id`为1–64字符的小写英文/数字/下划线/连字符标记。App按规范化manifest和资源字节计算实际内容身份；改包名不会覆盖旧库。`name`为1–64字符，`author`最多128字符，`license`必填且最多128字符。素材许可不因导入改变。

每项资源使用对象记录。`render=mask`使用源Alpha、跟随宿主实际前景色；`render=color`默认保留原RGB。App可分别设置范围/目标/状态的颜色与透明度；颜色继承与透明度继承独立，显式0透明度也有效。包不携带App颜色偏好或宿主查找代码。可选`sha256`必须为实际资源字节的64位小写摘要；App导入时补齐摘要，Provider、SystemUI与缓存会再次核验。

静态仅支持透明 **PNG** 与受限 **VectorDrawable XML**，拒绝WebP、SVG、APNG、AVD、字体、DEX、APK、脚本和URL。PNG最长边1024且须含真实透明像素；运行时按比例解码至最多256px。XML只接受`vector/group/path/clip-path`及明确Android几何/填充/描边属性；颜色直接写`#AARRGGBB`，禁止DTD、实体、资源/主题引用及外链。外部XML先解析为自有节点模型，不直接inflate成Drawable。

### beta95/code188 的静态可见高度

后台解码后，以所有 **Alpha > 0** 的真实像素计算可见边界；XML 使用栅格化后的像素。极低 Alpha 的艺术边缘仍计入边界，不按主观阈值裁掉。绘制以原生图形区域的高度为锚点，按可见宽高比等比缩放、居中，超过可用宽度时限宽。透明画布的宽高不再把窄图案再次缩小；不拉伸、不改 OEM View 尺寸，也不改变已有 Canvas 变换。

原文件、原始位图 RGB/Alpha 与完整画布保留，只在绘制时使用缓存的可见源区域。预览使用同一解码规则去掉外围透明留白；这是显示归一，不是重写素材。空白或无法得到有效边界的图案在运行时保留原生。边界只在后台计算，热绘制不读文件、不扫描像素、不逐帧生成裁剪图。

动态图形本版不按每帧可见边界归一，以免播放时尺寸跳动；静态端点的规则不能当作整段动画已完成高度适配。制作时保持动画全程画布与端点一致，并检查真实宿主效果。[详细边界](docs/V3-VALIDATION.zh-CN.md)仍适用。

动态为受限纯图形 **Lottie JSON**，仅接受shape layer及group/path/fill/stroke/transform/ellipse/rectangle。至少一项包含真实变化的两帧；静态或不变关键帧不能冒充动画。禁止图片、文字、表达式、mask/effects、父层、3D、时间重映射和外部资源。稳定切换≤800ms，真实瞬态≤1500ms。

```json
"transitions": {
  "tile.flashlight.off_to_on": {
    "source": "assets/flashlight-on.json",
    "from": "off", "to": "on", "reversible": false
  }
}
```

`off_to_on/on_to_off`必须提供精确静态两端；`transient`须`from=transient`、`to=on/off`且不能反播。首次绑定、换来源、回收复用显示静态末态。播放还取决于真实宿主、原生许可、可见性和生命周期；3个动画文件不表示所有目标已可播或实机通过。

## 角色和真实状态

[roles.json](roles.json)是生产Registry的177角色、89目标快照，包含`hint/wifi/cellular/battery/tile/slider/media/device/footer`。`supported`是该版源码接入状态，不是每台ROM或视觉效果的验收结果。未知但语法安全的角色只可保留为候选，包不能定义原生类、方法、Tile spec或新增宿主。

- 相机/麦克风`.on`为**允许访问**，`.off`为**阻止访问**，不能把“隐私屏蔽开启”画成`.on`。
- 旋转`.on`为自动旋转、`.off`为旋转锁定。蓝牙磁贴开启不等于耳机已连接。
- 支付、扫码、计算器、锁屏和电源等只有`.default`操作入口。铃声用`silent/vibrate/ring`；录屏用`unavailable/idle/recording`。
- `tile.cast`没有当前OEM stock factory分支；`controls/wallet`复杂服务入口仍保留原生。品牌照片、自定义媒体动作、第三方TileService不会因有图案就成为适配目标。
- 电池图只画外形和进度，不嵌百分数字、字母或闪电，避免与原生重复。

允许部分状态包；已登记目标的非法状态（如`wifi.5`、`tile.alipay.on`）必须拒绝。

## 制作和验证

压缩包≤24MiB、条目≤1024、单文件≤1MiB、展开总量≤48MiB；manifest≤256KiB、XML≤128KiB、Lottie≤256KiB、说明/许可各≤64KiB。只允许普通文件和安全路径，拒绝加密、链接、特殊文件、穿越、重复和大小写冲突路径。Android另支持未加密单卷RAR4/RAR5；本仓库工具只预检ZIP，RAR交实际App验证。

```powershell
python -m pip install -r requirements.txt
python tools/generate_original.py
python tools/validate_pack.py dist/c17-rounded-27.zip dist/c17-rounded-27-png.zip
python tools/check_validator.py
```

生成器读当前角色快照，新增目标缺少绘图函数时直接失败，绝不补通用占位。ZIP顺序、时间、属性固定，同输入可复现。更新快照须从模块生产Registry导出，不手写新宿主规则。

[schema](manifest.schema.json)仅供字段提示；[验证器](tools/validate_pack.py)还检查严格JSON、真实PNG CRC/Alpha、XML路径、Lottie预算、SHA及静态端点，并附畸形负样例。[验证边界](docs/V3-VALIDATION.zh-CN.md)：**桌面预检不能替代Android严格生产parser、真实事务、RAR JNI、OEM播放或手机视觉验收**。

## 许可和发布状态

规范、新桌面验证器与历史教学资源保留[MIT](LICENSE)。**C17示例库图案和生成器为GPL-3.0-only**，源文件及包内已注明，[完整GPL文本](LICENSES/GPL-3.0-only.txt)保留。它们不因放入此仓库改为MIT，第三方素材也保留自身许可。

本仓库发布制作规范、校验工具与示例；模块版本与手机效果以模块发布说明及实际验收为准。本仓库不接收PUI/OEM原始或转换素材。
