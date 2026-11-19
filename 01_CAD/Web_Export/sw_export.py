import win32com.client, pythoncom, sys, os, json, numpy as np
CD = win32com.client.CDispatch
def g(o, name, *a):
    v = getattr(o, name)
    if isinstance(v, CD) and not a: return v
    return v(*a) if callable(v) else v
def mpv(o, attr='MaterialPropertyValues'):
    try:
        v = getattr(o, attr)
        if v is None: return None
        v = list(v)
        if len(v) >= 3 and v[0] >= 0: return v
    except Exception: pass
    return None
sw = win32com.client.Dispatch("SldWorks.Application")
doc = sw.ActiveDoc
out = sys.argv[1]
EV = "Exploded View4"
doc.ShowExploded2(False, EV)
g(doc,"EditRebuild3")
comps = [c for c in doc.GetComponents(False)]
leaf = []
for c in comps:
    ch = g(c, 'GetChildren')
    if ch: continue
    if g(c,'IsSuppressed') or c.IsHidden(True): continue
    leaf.append(c)
def T(c): return [float(x) for x in c.Transform2.ArrayData[:13]]
collapsed = {c.Name2: T(c) for c in leaf}
topname = {}
for c in leaf:
    p = c; 
    while g(p,'GetParent') is not None: p = g(p,'GetParent')
    topname[c.Name2] = p.Name2
# explode steps
cfg = doc.ConfigurationManager.ActiveConfiguration
steps = []
for i in range(g(cfg,'GetNumberOfExplodeSteps')):
    st = cfg.GetExplodeStep(i)
    k = g(st,'GetNumOfComponents')
    steps.append({'name': st.Name, 'dist': st.ExplodeDistance, 'comps': [st.GetComponentName(j) for j in range(k)]})
doc.ShowExploded2(True, EV)
exploded = {c.Name2: T(c) for c in leaf}
doc.ShowExploded2(False, EV)
data = {'steps': steps, 'parts': []}
binbuf = bytearray()
for c in leaf:
    md = g(c,'GetModelDoc2')
    dcol = mpv(md) if md else None
    ccol = mpv(c)
    bodies = c.GetBodies2(0) or []
    groups = {}
    for b in bodies:
        bcol = mpv(b, 'MaterialPropertyValues2')
        for f in (g(b,"GetFaces") or []):
            t = f.GetTessTriangles(True); n = g(f,"GetTessNorms")
            if not t: continue
            fcol = mpv(f)
            col = fcol or bcol or ccol or dcol or [0.7,0.7,0.7,1,1,0.5,0.3,0,0]
            key = tuple(round(x,4) for x in col[:3]) + (round(col[7],3) if len(col)>7 else 0,)
            gp = groups.setdefault(key, {'p':[], 'n':[]})
            gp['p'].extend(t); gp['n'].extend(n if n else [0.0]*len(t))
    prims = []
    for key, gp in groups.items():
        p = np.asarray(gp['p'], np.float32); n = np.asarray(gp['n'], np.float32)
        prims.append({'color': list(key[:3]), 'transp': key[3], 'off': len(binbuf), 'count': len(p)//3})
        binbuf += p.tobytes(); binbuf += n.tobytes()
    data['parts'].append({'name': c.Name2, 'top': topname[c.Name2], 'file': os.path.basename(g(c,'GetPathName')),
        'T': collapsed[c.Name2], 'TE': exploded[c.Name2], 'box': list(c.GetBox(False, False)), 'prims': prims})
    print(c.Name2, sum(p['count'] for p in prims)//3, 'tris', [p['color'] for p in prims], 'moved' if np.abs(np.array(exploded[c.Name2])-np.array(collapsed[c.Name2])).max()>1e-6 else '')
open(out+'.json','w',encoding='utf-8').write(json.dumps(data, ensure_ascii=False, indent=1))
open(out+'.bin','wb').write(binbuf)
print('bytes', len(binbuf))
