# 0.1.11 闹钟液态衔接优化

0.1.10 真机反馈：联动已修复，液态动画已恢复，但感觉停顿。原补播重新执行 beginPress，包含 20ms 按压延迟，玻璃等待首帧时白滑块也未跟随玻璃弹簧。新版仅修改复用后的视觉补播：立即 showGlass 并在首步 startFlight，形变与位移并行（补播形变进入释放的等待为 100ms，而非重新模拟 180ms 按压）；首帧未就绪时白滑块跟随同一弹簧，落地时同步终点。原 Shader、真实手势时序和弹簧系数不改。复用保护、行校验、真实状态提交与 Bug 2 的首帧保护均保留。

主队列列表刷新、GPU 首帧和重复复用仍可能造成停顿；需真机测量。未进行 iOS 编译或真机验证。

---

# 0.1.10 闹钟液态动画恢复

0.1.9 真机反馈：其他开关已不联动，但本开关的液态动画消失。源码中 finishPress 在原生 valueChanged 回调后检查 releaseGeneration；列表配置的强制 reset 会使该 generation 失效。正常释放动画可能尚未开始就被取消。

本版保留所有 0.1.9 复用重置和原生即时同步。在操作前记录 table + indexPath、目标原生值、表格结构和当前 binding/reset 版本；真实事件立即提交且只提交一次。配置完成后下一主队列回合检查该可见行的当前 cell，只有原动画被 reset 或换绑时才补播。新操作替代旧凭证，凭证有效期 650ms，编辑、离屏、状态不一致、结构变化、正在触摸、无匹配 cell 时不补播。补播只使用原 press/release 的玻璃、滑块和颜色过渡，不发送 valueChanged 或第二次触觉反馈。复用仍可立即清理补播。未使用私有 alarm ID，若列表在同一行数下重新排序，indexPath 不是持久身份；需要真机复测。

保留 Bug 2 的首帧降级、无 PNG、无设置面板、默认启用、原渲染参数及构建参数。源码检查和模型测试不是 UIKit 真机验证。

---

# 0.1.9 修复记录

## Frida 真机证据（0.1.8）

- 5699 ms: 第一行 overlay `0xc0ab811b0` 提交开启。
- 5803 ms: 原第五行原生控件被 `MTAAlarmTableViewCell refreshUI:animated:` / `MTAAlarmTableViewController tableView:cellForRowAtIndexPath:` 配置为开启。
- 5914 ms: 原第一行原生控件被配置为关闭。
- 6069–6070 ms: 行对象顺序改变；原第一行对象位于第四行，插件仍显示开启，原生值为关闭；新第一行插件显示关闭，原生值为开启。
- 6317 ms: 插件开始同步两者；6405 ms 采样确认值一致。
- 15445 ms: 第四行 `0xc0a82b7e0` 的 fill layer 收到 0.38 秒 opacity 动画，栈来自 `TheseusSwitch.updateTrackColor(animated:duration:)` 和 `finishPress` 的延迟闭包。
- 整份日志统计 12 次可见行对象顺序变化、12 条不一致 VALUE 采样。日志工具本身有开销，时间不能作为精确用户感知时长。上述证据支持列表复用+旧动画的解释，不证明所有残余视觉异常均来自同一原因。

## 修复

1. 仅 Clock 中原生状态立即同步，不再使用 100ms 值门控；其他 App 仍保留合并异步同步。普通同值刷新仍不重新启动动画。
2. Clock 的 MTAAlarmTableViewCell `prepareForReuse` 开始前与 MTAAlarmTableViewController `tableView:cellForRowAtIndexPath:` 返回前，按当前原生值强制重置该 cell 内已绑定开关，即使值相同。只重置插件自身图层，不操作父列表动画。初次 hook 未找到类时在主队列重试一次。若其他系统版本不含这些类，仍保留立即同步的基础防护。
3. Swift reset 使 releaseGeneration 和 glassPresentationGeneration 失效，停止旧 display link，撤销旧 glass、thumb 和 fill 动画。手势/辅助功能提交回调返回后再次检查 generation，避免同步复用后又创建旧释放动画。
4. 不改变原版 Shader、尺寸、颜色、弹簧参数、白滑块降级逻辑；保留 0.1.8 的无设置、无 PNG 和默认启用。

## 回归与限制

- 测试第一行慢速开关、快速连点、单独操作第四行、滚动和编辑后再切换、长按拖动及之前 Bug 2 的 App。
- 闹钟重新配置单元格时允许截短当前开关释放动画尾部，这是防止旧动画跟随被复用 cell 的取舍；没有禁用正常手势动画，也没有停止列表本身的动画。
- 可继续使用原 Frida 脚本；`NG_CLOCK_TRACE=1 make build ARCH=arm64e` 可附加 cellReuseReset 诊断。静态检查和日志分析并非 iOS 编译或真机测试。
