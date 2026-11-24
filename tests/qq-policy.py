from pathlib import Path
r = Path(__file__).resolve().parents[1]
n = (r/'src/NGSwitch.m').read_text()
t = (r/'src/Tweak.m').read_text()
b = (r/'src/TheseusBridge.swift').read_text()
s = (r/'Vendor/Theseus/Sources/Theseus/Components/TheseusSwitch.swift').read_text()
assert 'com.tencent.mqq' in n and 'com.tencent.qq' in n
assert 'if (NGIsQQ() && (!binding || binding.overlay.superview != parent)' in n
assert 'existing.overlay.hidden = YES' in n
assert 'if (NGIsClock() || NGIsQQ())' in n
assert 'setIsolatesQQCapture:' in n and 'setIsolatesQQCapture' in b
assert 'if isolatesQQCapture { return self }' not in s
assert 'return pageSourceView' in s
assert 'if (NGIsClock() || NGIsQQ())' in n
assert 'NGQQHasSwitchOverlay(s)' in t
assert 'NGWithoutAnimation(commitNativeValue);' in n
assert 'if isolatesClockCapture || isolatesQQCapture { return self }' in s
assert s.count('guard !(isolatesClockCapture || isolatesQQCapture) || interactionGeneration == releaseGeneration') == 2
assert 'com.tencent.mqq' in t and 'com.tencent.qq' in t
assert 'if (!NGIsClock()) return NO;' in n
assert 'if (NGIsQQ())' in n and 'NGRemoveSwitch(source);' in n
print('PASS QQ-only binding, local glass, reattachment, opacity and callback guards (source contracts; not device test)')
