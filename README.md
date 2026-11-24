# TheseusSwitch — 0.1.13 坐标同步修复 / 无设置面板

基于 0.1.8 真机 Frida 日志。闹钟列表重新配置时 UISwitch 与其 overlay 被复用到不同的行；旧延迟状态门控与旧释放动画可能跨越复用边界。0.1.9 在 Clock 中同步原生值、在 prepareForReuse 和 cellForRowAtIndexPath 完成时重置该单元格的旧视觉状态（包括同值），并在用户回调返回后校验交互 generation。保留白色滑块降级、无 PNG、无设置面板和默认启用，不改变 Shader、尺寸、颜色、弹簧参数或编译优化级别。0.1.10 保留上述保护，用户操作时按表格和可见 indexPath 创建短期视觉补播凭证，若原动画被复用清理则在当前行重播，不重复提交状态。0.1.11 仅优化补播：立即启动玻璃和位移弹簧，首帧前白滑块跟随位移，形变与滑动并行。详见 BUG-NOTES.md。

## 0.1.13 坐标同步修复

基于 0.1.12。非 Clock 进程新增 UISwitch 的 setFrame:、setBounds:、setCenter:、setTransform: Hook，在原生 setter 返回后同步已绑定的同级替换视图。仅更新几何和隐藏状态，不创建 binding、不改变值、不触发动画、不启动轮询；Clock 不安装这些 Hook。空 bounds 暂时隐藏覆盖层，正常布局恢复。共享几何函数保留 63×28 尺寸，并在非 Clock 修正 convertPoint 与 transform 重复计入平移的问题。Swift、Metal、缓存、玻璃承载层、闹钟逻辑均保持原件。不能保证修复所有越界：非 Clock 页面级玻璃可能脱离滚动裁剪，宿主直接修改 CALayer 或特殊子类不调用父类也可能绕过 setter。附独立只读 Frida 脚本用于区分。未完成 iOS 编译与真机验证。运行 `python3 tests/geometry-policy.py` 验证仿射中心数学模型与源码契约；诊断脚本见 `diagnostics/`。

## 0.1.12 内存优化

基于用户确认效果正常的 0.1.11，只调整渲染资源生命周期，不改变动画参数、帧率、捕获分辨率、三帧在途机制、Shader、原生 Hook 或闹钟复用和补播逻辑。

- 每个渲染器的空闲 Metal 中间纹理池最多 8 MiB / 24 张；IOSurface 池最多 4 MiB / 12 张。单一规格仍最多 5 个。按实际资源分配字节数计账，跨规格统一限制；只限制空闲缓存，不限制活动 GPU 资源、drawable 或整个进程的内存。
- 停止渲染后保留 3 秒热缓存，随后清理纹理池、IOSurface、捕获位图、item-layer 位图和纹理、三个模糊核缓存。再次开始渲染立即取消计划清理。进入后台或收到内存警告时立即清理。
- 使用缓存 generation 防止旧 GPU 回调重新填充已清空的缓存；保留 GPU 原有事件同步和三缓冲。失败的捕获在无 GPU 使用时回收；不足三张的纹理环和失败的模糊核缓冲可在后续尝试重新分配。
- 保留 CAMetalLayer 和最近一次呈现，不强制清空 drawable 或销毁开关视图，以免影响动画首帧；长时间静置后首次交互可能重新分配中间资源，需真机确认首帧延迟。
- 运行 `python3 tests/memory-cache-policy.py`（需要主机 Swift）验证真实缓存实现的容量、释放、generation 和并发。另运行 `python3 tests/clock-replay-policy.py` 保留闹钟回归模型验证。

详见 MEMORY-NOTES.md。未测量真机 RSS/phys_footprint，不能保证具体内存下降比例。

## 来源与完整性

以下来源信息沿用输入压缩包 README 中的原始记录，本次未访问原始仓库或历史归档：

- 基线提交：`25cbb795c9f0f645c8a933d7e04da88454912320`
- 对应树：`1077bffb9bd4a272041298abaab1b883ec8b60c5`
- Theseus 上游：https://github.com/valzevul/Theseus
- 上游提交：`71ca1c127a4e7fe3387361f160c4890dbd427f66`
- 上游作者：Vadim Drobinin；原插件集成：Ning。

本次移除未参与原插件构建的 `TheseusSlider.swift` 和 `TheseusTabBar.swift`。35 个保留的上游文件（另有 UPSTREAM.json）中，27 个与上游清单一致；Vendor/local-patches.json 记录八个含本地修复的文件及前后哈希。`Vendor/manifest.json` 为输入清单删除上述两项后的子集；保留上游 LICENSE、NOTICE 和署名。`Vendor/Theseus/Package.swift` 保持原件，仅供参考；实际构建入口为 Makefile 和 tools/build.py。共享渲染与 Metal shader 保留；沿用 0.1.4 渲染成功通知条件，0.1.6 另外在时钟 App 中缩小捕获源，0.1.8 在时钟中将玻璃及阴影承载层归属单个开关，其他 App 维持原承载层；Shader 保持不变。

## 内容与行为

- `src/Tweak.m`：原有九个 UISwitch Hook，非 Clock 额外四个几何 setter Hook，动态解析 MSHookMessageEx；保留继承方法本地化，避免修改 UIView 的方法实现。
- `src/NGSwitch.m`：无动画布局同步、每实例合并原生状态更新、程序化同步无动画；63×28 Theseus 原版控件同级覆盖层、值和 enabled 同步、每次逻辑变化一次 valueChanged、回调拒绝值回同步、重挂载、隐藏、alpha 和移除时恢复；Clock 原生差异立即同步；只对被操作的可见闹钟行执行视觉补播。
- `src/TheseusBridge.swift`：新增同尺寸布局跳过和无动画 frame 更新，不重写 Theseus 材质、颜色、动画、物理或尺寸默认值。
- `src/NGResources.m`、`TheseusBundle.swift`、`Bridge.h`：资源解析、Swift Bundle.module 桥接。
- `tests/clock-trace-analysis.py`：可在主机分析原始 Frida 日志的行顺序变化、状态差异和释放动画；不包含用户原始日志。
- 不包含 `prefs/`、PNG、插件偏好读写及 Darwin 偏好通知。
- `Vendor/Theseus/`：开关原版控件及全部渲染、动画、捕获、fallback 支持；原版 Metal shader 一份。
- `packaging/`：双变体配置、RootHide 链接接口/头文件及许可证、无 respring postinst。
- `tools/`：源检查、原生编译/签名/资源/打包脚本、独立 deb 结构和 Mach-O 验证器。

已移除 NGDock、壁纸捕获适配、Dock Hook、Dock Swift 桥接、Dock 设置和图标、Glassify 全部源码和 shader、Glassify Bundle 访问器。旧混合工程的 CI workflow 和模拟器 Harness 不随本独立工程发货，不能把旧工程测试结果当作新插件验证。

## 独立标识与依赖

名称 TheseusSwitch，包标识 `com.ning.theseusswitch`，输出 TheseusSwitch.dylib、注入 Filter plist、TheseusSwitchResources.bundle。忽略旧偏好文件；同标识正常 dpkg 升级应移除原包拥有的设置文件。为避免双重 UISwitch Hook，与 com.ning.glassswitchdock/com.ning.switch/com.ning.daynightswitch 冲突。

运行依赖：iOS >= 15、提供 MSHookMessageEx 的 mobilesubstrate 兼容实现；arm64e RootHide 额外依赖 roothide >= 0.0.1。SDK 原生 Foundation/UIKit/Metal/MetalKit/QuartzCore/CoreGraphics/CoreVideo/IOSurface/Accelerate 随系统使用，不随源码提供二进制。RootHide TBD 仅链接接口，不打包假库。

安装布局由 packaging/config.json 决定：arm64 rootless 前缀 /var/jb；arm64e RootHide 逻辑前缀为空。资源解析沿用基线 dladdr/realpath 对真实安装前缀的识别方式。RootHide 注入、路径映射及 hook engine 仍需真机验证。

## 静态检查与后续构建方法

默认 `make`/`make check` 仅运行 Python 静态检查，不编译、不连接网络。可运行：

```sh
python3 tools/project.py --output evidence/source-check.json
python3 -m py_compile tools/*.py
sh -n packaging/postinst
```

未来只有另行授权后，在 macOS + 完整 Xcode（建议 Xcode 26+，需新版 SDK 声明）和 Python 3.10+ 环境运行：

```sh
make build ARCH=arm64e  # RootHide；不是普通 rootless arm64e 包
make verify ARCH=arm64e
# 可选普通 rootless：make build ARCH=arm64
```

构建脚本用 Xcode swiftc 编译 31 个上游 Swift 源和 2 个集成 Swift 源，同模块链接 3 个 Objective-C 核心源；不编译 TheseusSlider/TheseusTabBar。编译一份 TheseusShaders.metal 到唯一 default.metallib。保留 Swift 驱动链接计划提取、实际 arm64e CPU subtype 检查、RootHide 显式依赖、原生 codesign、最终 deb 重解包检查。构建过程本身无需下载源码。不再需要 Preferences.framework 链接接口。`--smoke` 仅是模拟器编译模式，不执行 UIKit 测试，亦未在此次执行。

## 安装包体积分析

当前构建使用 Swift `-O` + whole-module optimization、Objective-C `-O2`、Metal `-O2`，主库强制装入 Swift 静态归档；未显式启用链接器 dead stripping 或签名前 strip。主 dylib 动态链接系统 Swift runtime 和系统 framework，并不把系统 framework 整份打包。DEB 另含 Metal library、签名和许可证（无设置面板），使用 gzip 压缩 tar payload。当前源码包不含已构建 DEB，不能确定每项编译产物实际字节数。

```sh
python3 tools/size-report.py dist/com.ning.theseusswitch_0.1.13_iphoneos-arm64e.deb
```

该工具显示包的真实字节数和每个安装文件的未压缩大小，并给出每文件单独 gzip 压缩的估算（不可相加为实际 DEB 大小）。原验证器生成的 metadata JSON 也含 members[].size。本版不修改体积相关编译参数，以避免改变现有运行效果；后续可评估 `-Osize`、链接器 dead stripping、签名前安全 strip，逐项复测 ABI、签名和液态效果。

## 已执行验证与限制

0.1.12 执行上游清单与本地补丁 SHA-256、Swift frontend 语法解析（不进行 UIKit 类型检查）、源文件/Hook/无设置静态检查、Python 语法、shell 语法、主机缓存测试、闹钟回归模型和 ZIP CRC 校验。历史日志分析来自输入版本，未重新获取原始日志。没有 iOS SDK，未编译 DEB 或执行真机测试。原日志分析结果见 evidence/clock-trace-summary.txt。0.1.10 保留单元格重置并在正确的可见行尝试恢复动画。行定位采用 table + indexPath + 原生值校验而非私有 alarm ID；列表结构变化、离屏、编辑中或凭证过期时不补播。其他 App 和正常交互动画参数没有改变。
