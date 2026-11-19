import json, numpy as np, sys, struct
src, dst = sys.argv[1], sys.argv[2]
d = json.load(open(src+'.json', encoding='utf-8')); buf = open(src+'.bin','rb').read()
fix = lambda s: s.replace('�', 'ó')
LABELS = [  # (file prefix, label, material class)
 ('Base', 'Base de ventosas · Al 6061-T6', 'alu'),
 ('Acople de Robot - Copy', 'Acople de robot (brida) · Al 6061-T6', 'alu'),
 ('Acople de Robot', 'Acople superior · Al 6061-T6', 'alu'),
 ('Vacuum Generator', 'Generador de vacío FESTO VN-10-H', 'plastic'),
 ('T conex', 'Conector en T', 'plastic'),
 ('racores', 'Racor neumático G1/8', 'plastic'),
 ('tuberia', 'Tubería Ø6 mm', 'tube'),
 ('Cable^', 'Manguera neumática Ø6 mm', 'tube'),
 ('spin tite', 'Inserto spin-tite', 'brass'),
 ('ventosa', 'Ventosa de fuelle Ø25 mm', 'rubber'),
 ('pan head', 'Tornillo cabeza redonda M4', 'steel'),
]
PBR = {'alu':(0.75,0.32),'plastic':(0.05,0.45),'tube':(0.0,0.35),'brass':(0.85,0.3),'rubber':(0.0,0.8),'steel':(0.95,0.25)}
def classify(f):
    for pre,lab,cl in LABELS:
        if f.startswith(pre): return lab, cl
    return f, 'plastic'
def mat_rs(T):
    T=np.array(T); R=T[:9].reshape(3,3); t=T[9:12]; return R,t
def gl_matrix(R,t):
    return [R[0,0],R[0,1],R[0,2],0, R[1,0],R[1,1],R[1,2],0, R[2,0],R[2,1],R[2,2],0, t[0],t[1],t[2],1]
# assembly center from collapsed geometry
allpts=[]
for p in d['parts']:
    R,t=mat_rs(p['T'])
    for pr in p['prims']:
        allpts.append(np.frombuffer(buf,np.float32,pr['count']*3,pr['off']).reshape(-1,3)@R+t)
allpts=np.concatenate(allpts); lo,hi=allpts.min(0),allpts.max(0)
C=np.array([(lo[0]+hi[0])/2, lo[1], (lo[2]+hi[2])/2])   # center XZ, floor at min Y
print('size mm', (hi-lo)*1000)
# step lookup by top-level comp name
stepmap={}
for i,s in enumerate(d['steps']):
    for n in s['comps']: stepmap.setdefault(fix(n),[]).append(i)
bin_=bytearray(); views=[]; accs=[]; meshes=[]; mats=[]; matidx={}; meshidx={}; nodes=[]
def add_view(b, target):
    while len(bin_)%4: bin_.append(0)
    views.append({'buffer':0,'byteOffset':len(bin_),'byteLength':len(b),'target':target}); bin_.extend(b); return len(views)-1
def get_mat(color, cl):
    key=(tuple(color),cl)
    if key not in matidx:
        m,r=PBR[cl]
        mats.append({'name':f'{cl}_{len(mats)}','pbrMetallicRoughness':{'baseColorFactor':[*[(c/12.92 if c<=0.04045 else ((c+0.055)/1.055)**2.4) for c in color],1.0],'metallicFactor':m,'roughnessFactor':r},'doubleSided':True})
        matidx[key]=len(mats)-1
    return matidx[key]
for p in d['parts']:
    f=fix(p['file']); lab,cl=classify(f)
    mkey=f
    if mkey not in meshidx:
        prims=[]
        for pr in p['prims']:
            n=pr['count']
            P=np.frombuffer(buf,np.float32,n*3,pr['off']).reshape(-1,3)
            N=np.frombuffer(buf,np.float32,n*3,pr['off']+n*12).reshape(-1,3)
            key=np.round(np.c_[P*1e5,N*1e3]).astype(np.int64)
            _,first,inv=np.unique(key,axis=0,return_index=True,return_inverse=True)
            P2=P[first].astype(np.float32); N2=N[first]; ln=np.linalg.norm(N2,axis=1,keepdims=True); ln[ln==0]=1; N2=(N2/ln).astype(np.float32)
            idx=inv.ravel().astype(np.uint16 if len(first)<65536 else np.uint32)
            pv=add_view(P2.tobytes(),34962); accs.append({'bufferView':pv,'componentType':5126,'count':len(P2),'type':'VEC3','min':P2.min(0).tolist(),'max':P2.max(0).tolist()}); pa=len(accs)-1
            nv=add_view(N2.tobytes(),34962); accs.append({'bufferView':nv,'componentType':5126,'count':len(N2),'type':'VEC3'}); na=len(accs)-1
            iv=add_view(idx.tobytes(),34963); accs.append({'bufferView':iv,'componentType':5123 if idx.dtype==np.uint16 else 5125,'count':len(idx),'type':'SCALAR'}); ia=len(accs)-1
            prims.append({'attributes':{'POSITION':pa,'NORMAL':na},'indices':ia,'material':get_mat(pr['color'],cl)})
        meshes.append({'name':f.rsplit('.',1)[0],'primitives':prims}); meshidx[mkey]=len(meshes)-1
    R,t=mat_rs(p['T']); RE,tE=mat_rs(p['TE'])
    top=fix(p['top']); name=fix(p['name']).split('/')[-1]
    nodes.append({'name':name,'mesh':meshidx[mkey],'matrix':gl_matrix(R,t-C),
        'extras':{'label':lab,'cls':cl,'file':f,'steps':stepmap.get(top,[]),'explodedMatrix':gl_matrix(RE,tE-C)}})
gltf={'asset':{'version':'2.0','generator':'SolidWorks 2025 API -> custom exporter','copyright':'Grupo 6 - Universidad EAFIT'},
 'scene':0,'scenes':[{'name':'Emsamblaje','nodes':[len(nodes)],'extras':{'steps':[{'name':s['name'],'comps':[fix(c) for c in s['comps']]} for s in d['steps']],'units':'m'}}],
 'nodes':nodes+[{'name':'Emsamblaje','children':list(range(len(nodes)))}],
 'meshes':meshes,'materials':mats,'accessors':accs,'bufferViews':views,'buffers':[{'byteLength':len(bin_)}]}
while len(bin_)%4: bin_.append(0)
js=json.dumps(gltf,ensure_ascii=False,separators=(',',':')).encode('utf-8')
while len(js)%4: js+=b' '
glb=struct.pack('<III',0x46546C67,2,12+8+len(js)+8+len(bin_))+struct.pack('<II',len(js),0x4E4F534A)+js+struct.pack('<II',len(bin_),0x004E4942)+bin_
open(dst,'wb').write(glb); print('GLB bytes',len(glb),'meshes',len(meshes),'nodes',len(nodes),'mats',len(mats))
