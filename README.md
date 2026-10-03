# C17 状态栏图标库规范

配套模块：[SANWU5/c17-statusbar](https://github.com/SANWU5/c17-statusbar)。本规范用于新增图标库功能，模块正式安装包以主仓库 Releases 为准。

此仓库定义 C17 模块可导入的图标包格式，并提供原创教学示例。它不包含手机截图、用户配置、日志、原始 SystemUI 文件或第三方 PUI 模块资源。

C17 默认保留系统与模块现有图标。导入不会自动启用；用户可命名、排序、重命名、删除或禁用已导入的库。新库默认供逐项选择使用，可另开“整库自动匹配”。整库匹配从列表顶端向下查找，每个库没有资源时继续查下一库，最后使用原有系统/PUI 外观。已有整库配置保留原行为。最多保存 32 个库、同时启用 16 个库。

## 按图标选择图案

模块中的入口为 **配置 → 其他 → 自定义系统图标**。在“管理图标库”导入并启用来源库，再进入“逐项替换图标”，选择目标图标与来源图案。来源可以是任何已启用库中的合法图案，选中后显示缩略图供确认；无需整套替换。

例如，保持“整库自动匹配”关闭，只给蓝牙选择图案，已有 Wi-Fi、电池和蜂窝信号便不会被该库替换。也可分别指定 Wi-Fi 信号档位或电池电量档位。逐项指定优先于整库排序；蓝牙的 `.on` / `.off` 指定优先于通用 `hint.bluetooth`。删除该项指定后恢复自动匹配，来源库被禁用、删除或图片不可读取时，在启用整库匹配的库中按顺序回退，最后使用原生外观。

这一入口在主模块的本地待验收版本中，是否已发布以主仓库 Releases 为准。包格式仍为 version 1，制作者无需增加配置脚本，也不能通过图标包改变系统图标的显示条件。

## 制作与分发

ZIP 或未加密的单卷 RAR4/RAR5 内应有一个 `manifest.json`。文件可处于根目录，也可整体放入一个文件夹；不接受含多个 manifest 的归档。RAR 解码由 Android 的 libarchive 提供，遇到不支持的加密、分卷或损坏归档会拒绝导入，请改用 ZIP。

```text
manifest.json
assets/
  bluetooth.png
  wifi-0.png
  wifi-1.png
  ...
LICENSE.txt
README.md
```

```json
{
  "format": "c17-statusbar-icons",
  "version": 1,
  "name": "我的简约图标",
  "author": "作者名称",
  "license": "CC0-1.0",
  "render": "mask",
  "icons": {
    "hint.bluetooth": "assets/bluetooth.png"
  }
}
```

`name` 为 1–64 字符，作者最多 128 字符，`license` 必填并保留资源自身许可。`render` 当前仅支持 `mask`：使用透明 PNG/WebP 的 Alpha 通道，实际颜色继续遵循模块或系统的浅深色、活动状态和用户设置。图片中的 RGB 不用于替换系统着色。建议 128×128 或 256×256 透明画布、白色主体、相同视觉边距；不建议四周留下大片透明空白。图片最大 1024×1024，导入后保持比例归一化为最大 256 像素 PNG。禁止 SVG、Drawable XML、字体、DEX、APK、脚本和远程图片 URL。

资源路径只能为 `assets/<文件名>.png` 或 `.webp`；文件名使用英文字母、数字、下划线、连字符。最多 128 项图标、256 个归档条目，压缩文件最多 8 MB，单文件最多 1 MB，展开总内容最多 16 MB。归档内链接、路径穿越和加密文件不能用于资源导入。

## 图标标识与状态

| 范围 | 标识 | 规则 |
| --- | --- | --- |
| 原生提示图标 | `hint.bluetooth`、`hint.location` 等 | 通用图标，可用 `.on` / `.off` 提供状态差异；缺状态时回退通用图标 |
| Wi-Fi | `wifi.none`、`wifi.0` … `wifi.4` | 如声明该系列，六个状态必须全部提供 |
| 蜂窝信号 | `cellular.none`、`cellular.0` … `cellular.4` | 如声明该系列，六个状态必须全部提供；双卡按各卡原始信号分别绘制 |
| 电池 | `battery.0`、`battery.10` … `battery.100` | 如声明该系列，11 个状态必须全部提供；使用向下十位取整的电量档位 |
| 充电电池 | `battery.charging.0` … `battery.charging.100` | 可省略整套，缺失时使用普通电池；如声明则 11 状态完整，并提供普通电池系列 |

原生提示图标槽名：`bluetooth`、`location`、`alarm_clock`、`zen`、`volume`、`hotspot`、`headset`、`rotate`、`vpn`、`nfc`、`cast`、`screen_record`、`microphone`、`camera`、`privacy_call`、`usb`、`hd`、`airplane`。

例如蓝牙使用 `hint.bluetooth`；按原生启用状态分开设计时，使用 `hint.bluetooth.on` 和 `hint.bluetooth.off`。未知的 `hint.<slot>` 可以保留在包内，当前模块不会据此反射类或改变其他控件；只有实际适配过的原生槽位会使用。通知 App 图标、时间、网速文字、网络文字、数据箭头和电池内文字不属于此图标包范围，继续使用原有独立功能。

电池图片只包含背景外形和电量进度，不要画入百分数字、字母或闪电；动态百分数和充电指示继续由原生控件绘制，避免重复。当前蒙版版本使用电池轮廓色统一着色，不支持一张图片分别应用原生进度色和背景色；文字与充电指示仍使用各自颜色。不同档位的画布、外形位置应一致，充电版本可以改变外形但同样不画闪电。

整套系列可不提供，例如只制作蓝牙和定位是合法的；但不能只提供某一个 Wi-Fi 档位，避免联网状态变化时突然换回另一种外观。正在过渡中的原生动画、图标尺寸、布局和间距由 C17 运行时保持；此规范不能保证第三方 ROM 未适配的控件都能替换。

目前适配的 ColorOS 17 在 Wi-Fi 未连接时隐藏状态栏 Wi-Fi 图标，因此不会绘制 `wifi.none`，也不会把数据活动箭头的 `wifi_none` 资源当作该图标。该字段仍须随 Wi-Fi 系列提供，兼容既有规范；逐项设置页只列当前可绘制的目标。提示图标的系统隐藏条件同样保留，除已适配的蓝牙状态外，通用 `hint.<slot>` 是其他提示图标的主要匹配入口。

运行时先合并优先图标映射，只对实际使用的资源做后台解码。缓存限制为 4M 像素 Alpha 蒙版（约 4 MB）；超出预算、损坏或无法读取的图片会继续尝试下一库，再回退系统。上层已完全覆盖的库不会额外解码相同图标。

## GitHub 下载

在 App 输入 `owner/repo` 或 GitHub 仓库网址：优先选择最新发布的 `icon-pack.zip`，其次 `icon-pack.rar`；没有上述名字时，仅有一个 ZIP/RAR 附件才会选择。若有多个候选，请输入具体附件下载网址。仓库没有发布时尝试默认分支源代码 ZIP，仍要求归档里只有一个 manifest，因此包含多个示例的本规范仓库应下载 Releases 的单独示例包，而不是整仓库导入。

可直接输入 GitHub Release、raw.githubusercontent.com 或 codeload.github.com 的公开 ZIP/RAR 下载网址。无需 GitHub Token，不支持私人仓库。下载每次重定向检查官方 HTTPS 主机、限制大小和超时；下载的临时压缩包在处理后删除。导入后的库保存在 App 私有存储，卸载由系统删除。配置仅保存顺序与库 ID，不包含图标字节；迁移设备时需重新导入。

## 示例和验证

[PUI 资源对应表](docs/PUI-RESOURCE-MAPPING.zh-CN.md)记录所提供 ColorOS 17 包中的状态栏资源类别、可对应角色和缺项，仅包含清点结果，不转载素材。

`examples/minimal-hints/` 是可与现有默认样式混用的最小示例；`examples/complete-outline/` 覆盖上述全部状态。`dist/icon-pack.zip` 为完整示例，`dist/hints-only.zip` 为最小示例。它们仅演示规范和透明蒙版，不是 PUI 图标转载。

执行 `python tools/build_examples.py` 可使用 Pillow 重新生成示例和 ZIP。执行 `python tools/validate_pack.py dist/icon-pack.zip` 可检查目录、状态覆盖和图片规格；Android App 的导入检查为最终准入依据。本地工具不伪称验证过 Android RAR JNI 或真实 SystemUI 视觉效果。

规范文本、工具与原创示例资源均按 MIT License 分发，见 `LICENSE`。第三方制作和导入的图标保留各自许可，不因导入而自动变为 MIT。

## 联系

作者 aiingjie · GitHub [SANWU5](https://github.com/SANWU5) · 酷安 konwo · QQ 2726344450。交流、合作或自愿捐赠可联系作者；模块永久免费，捐赠渠道见模块“关于”页。
