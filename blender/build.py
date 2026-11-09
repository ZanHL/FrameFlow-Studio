import bpy, math, pathlib
from mathutils import Vector
root=pathlib.Path(__file__).resolve().parents[1]/'projects/engine001'
bpy.ops.object.select_all(action='SELECT'); bpy.ops.object.delete(use_global=False)
def mat(n,c):
 m=bpy.data.materials.new(n); m.diffuse_color=(*c,1); return m
silver=mat('Silver',(.55,.65,.75)); blue=mat('Intake',(.03,.4,.9)); orange=mat('Power',(.95,.3,.04))
def cube(n,loc,scale,m):
 bpy.ops.mesh.primitive_cube_add(size=1,location=loc); o=bpy.context.object; o.name=n; o.scale=scale; o.data.materials.append(m); return o
piston=cube('Piston',(0,0,3),(1.4,1, .5),silver)
rod=cube('Connecting rod',(0,0,1.5),(.2,.3,2),orange)
crank=cube('Crankshaft',(0,0,0),(1.8,.5,.3),silver)
for x in [-.9,.9]: cube('Cylinder cutaway rail',(x,.35,2.5),(.1,.4,3),blue)
for f in range(1,242):
 t=(f-1)/240*4*math.pi; r=.65; l=2.3
 p=Vector((r*math.sin(t),0,r*math.cos(t))); s=Vector((0,0,r*math.cos(t)+math.sqrt(l*l-r*r*math.sin(t)**2)))
 piston.location=s; piston.keyframe_insert('location',frame=f)
 rod.location=(p+s)/2; rod.scale.z=(s-p).length; rod.rotation_euler=(s-p).to_track_quat('Z','Y').to_euler(); rod.keyframe_insert('location',frame=f); rod.keyframe_insert('rotation_euler',frame=f)
 crank.rotation_euler.y=t; crank.keyframe_insert('rotation_euler',frame=f)
scene=bpy.context.scene
bpy.ops.object.camera_add(location=(6,-10,6)); cam=bpy.context.object; cam.rotation_euler=(Vector((0,0,1.5))-cam.location).to_track_quat('-Z','Y').to_euler(); cam.data.type='ORTHO'; cam.data.ortho_scale=7.5; scene.camera=cam
bpy.ops.object.light_add(type='AREA',location=(2,-4,7)); bpy.context.object.data.energy=1500; bpy.context.object.data.shape='DISK'; bpy.context.object.data.size=5
scene.world.color=(.15,.15,.15); scene.render.engine='CYCLES'; scene.cycles.samples=8
scene.render.resolution_x=640; scene.render.resolution_y=360; scene.render.resolution_percentage=100; scene.render.fps=24; scene.frame_end=240
scene.render.image_settings.file_format='PNG'; scene.render.filepath=str(root/'previews/model.png'); scene.frame_set(1)
bpy.ops.wm.save_as_mainfile(filepath=str(root/'scenes/engine_v001.blend')); bpy.ops.render.render(write_still=True)
print('BLENDER_TEST_OK')
