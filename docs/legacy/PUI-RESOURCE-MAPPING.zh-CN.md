# PUI ColorOS 17 资源与图标角色对应表

清点版本：`PUI Theme For ColorOS 17_v17.0.0.128_4.zip`，2026-10-03。

本页记录资源名称与格式，供图标作者理解状态含义。它不包含 PUI 的 APK、图形文件或资源代码。包内署名为“天伞桜&PanL”；所提供文件中未找到再分发许可，PUI 图形不作为本仓库的 MIT 示例。

## 文件结构

该包使用 Android RRO 资源覆盖，共 91 个覆盖 APK，涉及 43 个目标包，其中 27 个面向 SystemUI。不是可直接导入 C17 的图片图标包。共计 1,025 个逻辑 drawable 和 32 个逻辑 mipmap；物理文件包括 965 个 XML、50 个 PNG 和 27 个 WebP，数量差异来自资源别名和密度变体。

以下为与当前状态栏协议相关的主要资源：

| 覆盖包 | 资源 | 对应 C17 角色或限制 |
| --- | --- | --- |
| PuiThemeSignalIcon | `stat_signal_wifi_signal_0_os17` … `stat_signal_wifi_signal_4_os17` | `wifi.0` … `wifi.4`；未找到明确的断开图案 |
| PuiThemeSignalIcon | `stat_signal_signal_lte_single_0_os17` … `stat_signal_signal_lte_single_4_os17` | `cellular.0` … `cellular.4` |
| PuiThemeSignalIcon | `stat_signal_signal_null_lte` | `cellular.none` 候选，需与有信号图案选择同一视觉系列 |
| PuiThemeStatusIcon | `stat_sys_data_bluetooth`、`stat_sys_data_bluetooth_connected` | `hint.bluetooth.off`、`hint.bluetooth.on` |
| PuiThemeStatusIcon | `stat_sys_location`、`stat_sys_alarm`、`stat_sys_dnd` | `hint.location`、`hint.alarm_clock`、`hint.zen` |
| PuiThemeStatusIcon | `stat_sys_headset`、`stat_sys_vpn_ic`、`stat_sys_nfc`、`stat_sys_airplane_mode` | `hint.headset`、`hint.vpn`、`hint.nfc`、`hint.airplane` |
| PuiThemeStatusIcon | `stat_sys_ringer_silent`、`stat_sys_ringer_vibrate` | 都属于音量提示；当前通用 `hint.volume` 不区分静音与振动 |
| PuiThemeHDSignalIcon | `stat_signal_volte` 等 | `hint.hd` 候选；协议不区分这些双卡 VoLTE 变体 |
| PuiThemeBatteryHorizontal、PuiThemeBatteryVerticalIcon | 电池外框、背景和进度组件 | 动态组件；没有 `battery.0` … `battery.100` 的 11 档静态图案 |

Wi-Fi 与蜂窝图案主要为 XML vector、inset 或资源引用。取得素材许可后，制作者仍需将其转换成规范要求的透明 PNG/WebP，校验完整状态组和一致的视觉边距；C17 不加载包中的 APK 或执行脚本。

## 避免混淆

- `stat_signal_activity_wifi_none_os17` 是数据活动箭头占位，不能当作 `wifi.none`。当前适配的 ColorOS 17 未连接 Wi-Fi 时隐藏图标，模块保留这一行为。
- `stat_bt_battery_*` 是蓝牙附件电量，不是手机电池。
- PuiThemeSignalLOGO 中的 2G / 3G / 4G / 5G 图片属于网络制式标签，不在当前图标包替换范围内。
- PuiThemeQuickPanelIcon 的 114 个 drawable 属于控制中心磁贴，不是状态栏提示图标。
- `usb_notification_icon` 是通知来源的图形，不能仅凭名称认定它对应状态栏的 `hint.usb`。

制作者可制作原创图案，并沿用这些状态语义。图标文件仍须遵循各自许可；图标包格式不授予第三方素材的使用权。
