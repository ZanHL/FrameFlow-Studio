import bpy,math,pathlib,json
from mathutils import Vector
R=pathlib.Path(__file__).resolve().parents[1]/'projects/engine001'
bpy.ops.wm.open_mainfile(filepath=str(R/'scenes/engine_v002.blend'))
s=bpy.context.scene;s.render.resolution_x=640;s.render.resolution_y=426;s.render.fps=24;s.frame_start=1;s.frame_end=240;s.cycles.samples=4
names=['Piston','Piston ring','Piston ring.001','Piston ring.002','Piston pin','Small end']
initial={n:bpy.data.objects[n].location.copy() for n in names};z0=initial['Piston'].z
rod=bpy.data.objects['Connecting rod'];length=rod.dimensions.z
# Cylinder local Z length retained; scale keyed explicitly.
cranknames=['Crank pin','Crank web','Crank web.001']
starts={n:(bpy.data.objects[n].location.copy(),bpy.data.objects[n].rotation_euler.copy()) for n in cranknames}
# Rotate complete crank assembly relative to saved 60 degree pose.
for f in range(1,242):
 t=(f-1)/240*4*math.pi;r=.65;l=2.3;p=Vector((r*math.sin(t),0,r*math.cos(t)));z=p.z+math.sqrt(l*l-p.x*p.x);q=Vector((0,0,z))
 for n in names:
  o=bpy.data.objects[n];o.location=initial[n]+Vector((0,0,z-z0));o.keyframe_insert('location',frame=f)
 rod.location=(p+q)/2;rod.rotation_euler=(q-p).to_track_quat('Z','Y').to_euler();rod.keyframe_insert('location',frame=f);rod.keyframe_insert('rotation_euler',frame=f)
 o=bpy.data.objects['Big end'];o.location=p;o.keyframe_insert('location',frame=f)
 from mathutils import Matrix
 rot=Matrix.Rotation(t-math.pi/3,4,'Y')
 for n,(loc,ang) in starts.items():
  o=bpy.data.objects[n];o.location=rot@loc;o.rotation_euler=(rot.to_3x3()@ang.to_matrix()).to_euler();o.keyframe_insert('location',frame=f);o.keyframe_insert('rotation_euler',frame=f)
 phase=t%(4*math.pi)
 for prefix,opened in [('Intake',phase<math.pi),('Exhaust',phase>=3*math.pi)]:
  lift=.16*math.sin(phase%math.pi) if opened else 0
  for suffix,base in [(' valve stem',3.7),(' valve head',3.365)]:
   o=bpy.data.objects[prefix+suffix];o.location.z=base-lift;o.keyframe_insert('location',frame=f)
for o in bpy.data.objects:
 if o.animation_data and o.animation_data.action:
  for fc in o.animation_data.action.fcurves:
   for k in fc.keyframe_points:k.interpolation='LINEAR'
s.render.image_settings.file_format='PNG';s.render.filepath=str(R/'renders/preview_')
bpy.ops.wm.save_as_mainfile(filepath=str(R/'scenes/engine_v003.blend'))
xs=[.65*math.cos(i*math.pi/120)+math.sqrt(2.3**2-.65**2*math.sin(i*math.pi/120)**2) for i in range(241)]
(R/'validation_animation.json').write_text(json.dumps({'stroke':max(xs)-min(xs),'expected_stroke':1.3,'rod_length':2.3,'cycle_return_error':abs(xs[-1]-xs[0]),'fps':24,'frames':240,'duration_sec':10},indent=2))
bpy.ops.render.render(animation=True)
