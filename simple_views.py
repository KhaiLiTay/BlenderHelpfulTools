import bpy
import sys
import os
import math
import mathutils
import argparse

# blender --background --python simple_views.py -- --folder wood_original


parser = argparse.ArgumentParser()
parser.add_argument('--folder', required=True)
parser.add_argument('--num_views', type=int, default=12)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
folder = args.folder
num_views = args.num_views

model_path = os.path.join(folder, "model.glb")
output_dir = os.path.join(folder, "output")
os.makedirs(output_dir, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.feature_set = 'EXPERIMENTAL'
bpy.ops.import_scene.gltf(filepath=model_path)

objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
if not objs:
    raise RuntimeError("cannot find mesh")

# === Scale model to fit into normalized view ===
target_scale = 1.0
max_dim = max(max(obj.dimensions) for obj in objs)
scale_factor = target_scale / max_dim
for obj in objs:
    obj.scale = [s * scale_factor for s in obj.scale]
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(scale=True)

# === Calculate bounding box center ===
bbox_min = [float('inf')] * 3
bbox_max = [float('-inf')] * 3
for obj in objs:
    for v in obj.bound_box:
        coord = obj.matrix_world @ mathutils.Vector(v)
        for i in range(3):
            bbox_min[i] = min(bbox_min[i], coord[i])
            bbox_max[i] = max(bbox_max[i], coord[i])
center = mathutils.Vector(
    [(mi + ma) / 2 for mi, ma in zip(bbox_min, bbox_max)])

# === Setup camera rig ===
radius = 2.5
elevation = 1.2
bpy.ops.object.empty_add(type='PLAIN_AXES', location=center)
pivot = bpy.context.active_object

cam = bpy.data.objects.new("Camera", bpy.data.cameras.new("Camera"))
bpy.context.scene.collection.objects.link(cam)
scene.camera = cam
cam.parent = pivot
cam.location = (center.x + radius, center.y, center.z + elevation)
cam.rotation_euler = (math.radians(75), 0, math.pi)
track = cam.constraints.new(type='TRACK_TO')
track.target = pivot
track.track_axis = 'TRACK_NEGATIVE_Z'
track.up_axis = 'UP_Y'

# === Lighting setup ===
bpy.ops.object.light_add(type='SUN', location=(
    center.x, center.y, center.z + 5))
bpy.context.object.data.energy = 10
for dx, dz in [(2, 2), (-2, 2)]:
    bpy.ops.object.light_add(type='POINT', location=(
        center.x + dx, center.y, center.z + dz))
    bpy.context.object.data.energy = 300

# === Environment lighting ===
if not scene.world:
    scene.world = bpy.data.worlds.new("World")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs[1].default_value = 3.0

# === Render settings ===
scene.render.image_settings.file_format = 'PNG'
scene.render.resolution_x = 1280
scene.render.resolution_y = 960
scene.cycles.device = 'GPU' if bpy.context.preferences.addons.get(
    'cycles') else 'CPU'
scene.cycles.samples = 32
scene.cycles.use_adaptive_sampling = True
scene.cycles.use_denoising = True

for i in range(num_views):
    angle = i * 2 * math.pi / num_views
    cam.location = (
        center.x + radius * math.cos(angle),
        center.y + radius * math.sin(angle),
        center.z + elevation
    )
    cam.rotation_euler = (math.radians(75), 0, angle + math.pi)
    bpy.context.view_layer.update()
    scene.render.filepath = os.path.join(output_dir, f"render_{i:03d}.png")
    bpy.ops.render.render(write_still=True)
