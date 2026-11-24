TheseusBoundsTrace — TheseusSwitch 0.1.12 / 0.1.13

用途：只读记录 UISwitch、NGTheseusSwitch、TheseusView、GlassKnobShadowView 的几何、窗口、可见性和祖先裁剪信息。不修改属性，不安装 Hook，不记录页面文字、开关值或触摸内容。每 500ms 在主线程扫描一次，有记录上限和变更去重；短暂动画可能漏采样，扫描本身也会增加少量开销。

使用：解压至 Downloads，打开有问题的 App。
  cd ~/Downloads
  frida-ps -Uai
  frida -U -N com.apple.Preferences -l TheseusBoundsTrace.js -o bounds-debug.log
将 com.apple.Preferences 替换成目标 App 的 Identifier。如果目标是 SpringBoard，可使用 -n SpringBoard 替代 -N ...。
看到 [TSB] READY 后，正常页面静置 2 秒，进入异常页面静置 2 秒，上下滚动并停留，长按异常开关约 1 秒再松手，返回上一页。按 Ctrl+C，发送 bounds-debug.log 和发生异常的 App、页面、插件版本。可附录屏。

NATIVE: 原生 UISwitch（插件正常替换时 alpha=0 是预期行为）
OVERLAY: 替换的完整开关；centerDelta 为候选同级原生开关和覆盖层的窗口坐标中心差。
GLASS: 玻璃或阴影，可能不在开关的同一父视图。
OUTSIDE_WINDOW: 模型矩形完全离开窗口；滚动列表正常离屏也会出现。
CLIPPED_BY_ANCESTOR: 模型矩形被祖先裁剪完全遮挡。
ANCESTOR_INVISIBLE / SELF_INVISIBLE: 隐藏或低透明度；并非一定是错误。
CENTER_DELTA_GT_2PT: 候选中心差超过 2pt，仅是诊断线索；邻接关系不是绑定身份证明。
presentation: 可用时记录 Core Animation 呈现坐标；visible: 模型矩形的轴对齐裁剪估计，不是逐像素可见性。
SNAP truncated=true: 遍历达到上限，不能把未记录的视图视为已移除。

已做 Node 语法检查，未在 iOS/Frida 真机运行。Frida CLI 需提供 ObjC bridge。
