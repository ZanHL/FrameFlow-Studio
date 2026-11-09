import bpy, math, pathlib
from mathutils import Vector
R=pathlib.Path(__file__).resolve().parents[1]/'projects/engine001'
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
def material(n,c):
 m=bpy.data.materials.new(n);m.diffuse_color=(*c,1);return m
silver=material('Brushed silver',(.55,.65,.72)); dark=material('Cylinder housing',(.075,.15,.22)); blue=material('Intake blue',(.03,.4,.9)); purple=material('Exhaust purple',(.55,.15,.7)); gold=material('Connecting rod brass',(.85,.45,.08));white=material('Ceramic',(.9,.92,.95))
def cyl(n,a,b,r,m):
 a,b=Vector(a),Vector(b);bpy.ops.mesh.primitive_cylinder_add(vertices=48,radius=r,depth=(b-a).length,location=(a+b)/2);o=bpy.context.object;o.name=n;o.rotation_euler=(b-a).to_track_quat('Z','Y').to_euler();o.data.materials.append(m);be=o.modifiers.new('Edge highlights','BEVEL');be.width=.025;be.segments=3;o.modifiers.new('Normals','WEIGHTED_NORMAL');return o
def box(n,p,s,m):
 bpy.ops.mesh.primitive_cube_add(size=1,location=p);o=bpy.context.object;o.name=n;o.scale=s;o.data.materials.append(m);return o
# Static mid-stroke pose for structural review; animation generated only after G2.
r=.65;l=2.3;t=math.pi/3;p=Vector((r*math.sin(t),0,r*math.cos(t)));s=Vector((0,0,p.z+math.sqrt(l*l-p.x*p.x)))
cyl('Piston',(0,0,s.z-.22),(0,0,s.z+.22),.7,silver)
for z in [-.14,.03,.15]:cyl('Piston ring',(0,0,s.z+z),(0,0,s.z+z+.035),.715,dark)
cyl('Piston pin',(0,-.8,s.z),(0,.8,s.z),.13,gold)
cyl('Connecting rod',p,s,.13,gold)
for name,q,rad in [('Big end',p,.24),('Small end',s,.2)]:cyl(name,q+Vector((0,-.2,0)),q+Vector((0,.2,0)),rad,silver)
cyl('Main crankshaft',(0,-.8,0),(0,.8,0),.18,silver)
cyl('Crank pin',p+Vector((0,-.35,0)),p+Vector((0,.35,0)),.16,silver)
for y in [-.32,.32]:cyl('Crank web',(0,y,0),(p.x,y,p.z),.2,gold)
cyl('Flywheel',(0,.5,0),(0,.7,0),1,dark)
# Rear half of cylinder exposes mechanism.
verts=[];faces=[]
for z in [1.35,3.55]:
 for i in range(33):
  a=i*math.pi/32;verts.append((.82*math.cos(a),.82*math.sin(a),z))
for i in range(32):faces.append((i,i+1,i+34,i+33))
mesh=bpy.data.meshes.new('Cutaway mesh');mesh.from_pydata(verts,[],faces);o=bpy.data.objects.new('Cylinder rear cutaway',mesh);bpy.context.collection.objects.link(o);o.data.materials.append(dark);o.modifiers.new('Wall thickness','SOLIDIFY').thickness=.1
box('Cylinder head',(0,.25,3.65),(1.85,.95,.25),silver)
for x,m,n in [(-.43,blue,'Intake'),(.43,purple,'Exhaust')]:
 cyl(n+' valve stem',(x,0,3.35),(x,0,4.05),.055,silver);cyl(n+' valve head',(x,0,3.33),(x,0,3.4),.22,m);cyl(n+' port',(x,.25,3.85),(x,.9,3.85),.18,m)
cyl('Spark plug',(0,0,3.65),(0,0,4.15),.1,white)
box('Display base',(0,.15,-1.15),(3.4,2.3,.2),dark)
scene=bpy.context.scene
bpy.ops.object.camera_add(location=(5,-10,5));cam=bpy.context.object;cam.rotation_euler=(Vector((0,0,1.5))-cam.location).to_track_quat('-Z','Y').to_euler();cam.data.type='ORTHO';cam.data.ortho_scale=10.8;scene.camera=cam
for loc,power in [((2,-4,7),1800),((-4,-2,3),1100)]:
 bpy.ops.object.light_add(type='AREA',location=loc);o=bpy.context.object;o.data.energy=power;o.data.size=5;o.rotation_euler=(Vector((0,0,2))-o.location).to_track_quat('-Z','Y').to_euler()
scene.world.color=(.14,.14,.14);scene.render.engine='CYCLES';scene.cycles.device='CPU';scene.cycles.samples=16;scene.render.resolution_x=960;scene.render.resolution_y=640;scene.render.resolution_percentage=100
scene.render.image_settings.file_format='PNG';scene.render.filepath=str(R/'previews/model_v002.png')
bpy.ops.wm.save_as_mainfile(filepath=str(R/'scenes/engine_v002.blend'));bpy.ops.render.render(write_still=True);print('MODEL_V002_OK')
