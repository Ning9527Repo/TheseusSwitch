'use strict';
// Read-only snapshot tracer. No hooks, setters, interception or retained views.
// Run in the affected app with Frida CLI; all UIKit reads are on main queue.
if (typeof ObjC === 'undefined' || !ObjC.available) {
    console.log('[TSB] ObjC bridge unavailable; use a Frida CLI with ObjC support.');
} else {
    const U = ObjC.classes;
    const LIMIT = 6000, MAX_RECORDS = 240, INTERVAL = 500;
    let pending = false, seq = 0, previous = new Map();
    const num = x => Number(x);
    const rnd = x => Math.round(num(x) * 100) / 100;
    const ptr = x => x ? x.handle.toString() : null;
    const cls = x => x ? x.$className : null;
    const present = x => x && !x.handle.isNull();
    function rect(x) {
        if (x.length === 2 && x[0].length === 2) return [rnd(x[0][0]), rnd(x[0][1]), rnd(x[1][0]), rnd(x[1][1])];
        if (x.length === 4) return Array.from(x, rnd);
        throw new Error('unexpected CGRect ABI: ' + JSON.stringify(x));
    }
    function array(x) {
        if (!present(x)) return [];
        const result = [], n = num(x.count());
        for (let i = 0; i < n; i++) result.push(x.objectAtIndex_(i));
        return result;
    }
    function rectIn(v, w) { return rect(v.convertRect_toView_(v.bounds(), w)); }
    function intersect(a, b) {
        if (!a || !b) return null;
        const x = Math.max(a[0], b[0]), y = Math.max(a[1], b[1]);
        const r = Math.min(a[0] + a[2], b[0] + b[2]);
        const d = Math.min(a[1] + a[3], b[1] + b[3]);
        return [rnd(x), rnd(y), rnd(Math.max(0,r-x)), rnd(Math.max(0,d-y))];
    }
    const empty = r => !r || r[2] <= 0 || r[3] <= 0;
    function presentation(v, w) {
        try {
            const p = v.layer().presentationLayer(), wp = w.layer().presentationLayer();
            if (!present(p) || !present(wp)) return null;
            return rect(p.convertRect_toLayer_(p.bounds(), wp));
        } catch (_) { return null; }
    }
    function kind(v) {
        const name = cls(v);
        if (/NGTheseusSwitch$/.test(name)) return 'OVERLAY';
        if (/TheseusView|GlassKnobShadowView/.test(name)) return 'GLASS';
        if (U.UISwitch && v.isKindOfClass_(U.UISwitch)) return 'NATIVE';
        return null;
    }
    function info(v, w, type, index) {
        const model = rectIn(v,w), windowBounds = rect(w.bounds());
        let visible = intersect(model,windowBounds);
        const ancestors = [];
        let parentHidden = false, parentAlpha = 1;
        for (let p = v.superview(), depth = 0; present(p) && depth < 40; p = p.superview(), depth++) {
            const clips = !!p.clipsToBounds() || !!p.layer().masksToBounds();
            const hidden = !!p.isHidden();
            const a = num(p.alpha());
            parentHidden = parentHidden || hidden;
            parentAlpha *= a;
            const r = rectIn(p,w);
            if (clips) visible = intersect(visible,r);
            if (depth < 14 || clips || hidden || a <= .01) {
                ancestors.push({id:ptr(p),class:cls(p),rect:r,clips,hidden,alpha:rnd(a)});
            }
            if (ptr(p) === ptr(w)) break;
        }
        const hidden = !!v.isHidden(), alpha = rnd(v.alpha());
        // Native alpha=0 is expected while Theseus is bound, not a visibility bug.
        const flags = [];
        if (empty(intersect(model,windowBounds))) flags.push('OUTSIDE_WINDOW');
        if (!empty(intersect(model,windowBounds)) && empty(visible)) flags.push('CLIPPED_BY_ANCESTOR');
        if (parentHidden || parentAlpha <= .01) flags.push('ANCESTOR_INVISIBLE');
        if (hidden || (type !== 'NATIVE' && alpha <= .01)) flags.push('SELF_INVISIBLE');
        let transform = null;
        try { transform = Array.from(v.transform(),rnd); } catch (_) {}
        return {type,id:ptr(v),class:cls(v),parent:ptr(v.superview()),index,window:ptr(w),windowBounds,
            frame:rect(v.frame()),bounds:rect(v.bounds()),model,presentation:presentation(v,w),visible,
            transform,hidden,alpha,layerOpacity:rnd(v.layer().opacity()),flags,ancestors};
    }
    function windows() {
        const app = U.UIApplication.sharedApplication(), result = new Map();
        function add(list) { for (const w of array(list)) result.set(ptr(w),w); }
        add(app.windows());
        try {
            const scenes = app.connectedScenes().allObjects();
            for (const scene of array(scenes)) {
                if (U.UIWindowScene && scene.isKindOfClass_(U.UIWindowScene)) add(scene.windows());
            }
        } catch (_) {}
        return Array.from(result.values());
    }
    function snapshot() {
        const records = [], seen = new Set();
        let visited = 0, truncated = false;
        for (const w of windows()) {
            const stack = [{v:w,index:0}];
            while (stack.length) {
                if (visited >= LIMIT || records.length >= MAX_RECORDS) { truncated = true; break; }
                const item = stack.pop(), v = item.v, id = ptr(v);
                if (seen.has(id)) continue;
                seen.add(id); visited++;
                const type = kind(v);
                if (type) {
                    // Omit idle hidden glass; record active or fading glass only.
                    if (type !== 'GLASS' || !v.isHidden()) records.push(info(v,w,type,item.index));
                    if (type === 'NATIVE') continue; // native implementation internals are irrelevant
                }
                const children = array(v.subviews());
                for (let i = children.length-1; i >= 0; i--) stack.push({v:children[i],index:i});
            }
            if (truncated) break;
        }
        // Candidate pairing only: a sibling immediately above a UISwitch is the
        // normal insertion pattern. Never assert that an ambiguous pair is bound.
        const byParent = new Map();
        for (const r of records) {
            if (r.type !== 'NATIVE') continue;
            if (!byParent.has(r.parent)) byParent.set(r.parent,[]);
            byParent.get(r.parent).push(r);
        }
        for (const r of records) {
            if (r.type !== 'OVERLAY') continue;
            const candidates = byParent.get(r.parent) || [];
            const adjacent = candidates.filter(n=>n.index+1===r.index);
            const n = adjacent.length===1 ? adjacent[0] : candidates.length===1 ? candidates[0] : null;
            if (!n) {r.pair='AMBIGUOUS_OR_MISSING'; continue;}
            r.pair = adjacent.length===1 ? 'ADJACENT_CANDIDATE' : 'ONLY_SIBLING_CANDIDATE';
            r.nativeCandidate = n.id;
            r.centerDelta = [rnd(r.model[0]+r.model[2]/2-n.model[0]-n.model[2]/2),rnd(r.model[1]+r.model[3]/2-n.model[1]-n.model[3]/2)];
            if (Math.hypot(...r.centerDelta)>2) r.flags.push('CENTER_DELTA_GT_2PT');
        }
        const current = new Map();
        let changed=0;
        for (const r of records) {
            const line=JSON.stringify(r);
            current.set(r.id,line);
            if (previous.get(r.id)!==line) {console.log('[TSB] '+r.type+' '+line);changed++;}
        }
        if (!truncated) {
            for (const id of previous.keys()) if (!current.has(id)) {console.log('[TSB] GONE '+id);changed++;}
            previous=current;
        } else {
            // Do not infer disappeared views from an incomplete traversal.
            for (const [id,line] of current) previous.set(id,line);
        }
        if (changed || truncated || seq%10===0) console.log('[TSB] SNAP '+JSON.stringify({seq,visited,records:records.length,changed,truncated,ms:Date.now()}));
        seq++;
    }
    function tick() {
        if (pending) return;
        pending=true;
        ObjC.schedule(ObjC.mainQueue,()=>{
            try {
                if(seq===0) console.log('[TSB] READY '+U.NSBundle.mainBundle().bundleIdentifier().toString()+' interval='+INTERVAL+'ms');
                snapshot();
            } catch(e) {console.log('[TSB] ERROR '+e.stack);}
            finally {pending=false;}
        });
    }
    tick();
    setInterval(tick,INTERVAL);
}
