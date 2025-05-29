import bpy
import sys
import os
import math
import mathutils
import argparse

# blender --background --python material_views.py -- --folder "C:/你的資料夾" --num_views 12

parser = argparse.ArgumentParser()
parser.add_argument('--folder', required=True)
parser.add_argument('--num_views', type=int, default=12)
args = parser.parse_args(sys.argv[sys.argv.index("--") + 1:])
folder = args.folder
num_views = args.num_views

model_path = os.path.join(folder, "model.glb")
output_dir = os.path.join(folder, "output_material")
os.makedirs(output_dir, exist_ok=True)

bpy.ops.wm.read_factory_settings(use_empty=True)
scene = bpy.context.scene
scene.render.engine = 'CYCLES'
scene.cycles.feature_set = 'EXPERIMENTAL'

bpy.ops.import_scene.gltf(filepath=model_path)
objs = [o for o in bpy.context.scene.objects if o.type == 'MESH']
if not objs:
    raise RuntimeError("cannot find mesh")

# === Auto scale model ===
target_scale = 1
max_dim = max(max(obj.dimensions) for obj in objs)
scale_factor = target_scale / max_dim
for obj in objs:
    obj.scale = [s * scale_factor for s in obj.scale]
    bpy.context.view_layer.objects.active = obj
    bpy.ops.object.transform_apply(scale=True)

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

bpy.ops.object.light_add(type='SUN', location=(
    center.x, center.y, center.z + 5))
bpy.context.object.data.energy = 10
for dx, dz in [(2, 2), (-2, 2)]:
    bpy.ops.object.light_add(type='POINT', location=(
        center.x + dx, center.y, center.z + dz))
    bpy.context.object.data.energy = 300

if not scene.world:
    scene.world = bpy.data.worlds.new("World")
scene.world.use_nodes = True
scene.world.node_tree.nodes["Background"].inputs[1].default_value = 3.0


def load_image_auto(nodes, image_path, label, colorspace='sRGB'):
    if not os.path.exists(image_path):
        print(f"[SKIP] texture not found: {image_path}")
        return None
    tex = nodes.new('ShaderNodeTexImage')
    tex.image = bpy.data.images.load(image_path)
    tex.label = label
    tex.image.colorspace_settings.name = colorspace
    tex.extension = 'REPEAT'
    tex.interpolation = 'Smart'
    return tex


def clamp_scalar(nodes, links, image_tex):
    clamp = nodes.new('ShaderNodeClamp')
    links.new(image_tex.outputs["Color"], clamp.inputs["Value"])
    return clamp.outputs["Result"]


for obj in objs:
    for poly in obj.data.polygons:
        poly.use_smooth = True
    mat = bpy.data.materials.new(name="SVBRDF_Bump_Displacement")
    mat.use_nodes = True
    nodes = mat.node_tree.nodes
    links = mat.node_tree.links
    nodes.clear()

    output = nodes.new("ShaderNodeOutputMaterial")
    bsdf = nodes.new("ShaderNodeBsdfPrincipled")
    # Specular should be 0.0 for SVBRDF
    bsdf.inputs['Specular'].default_value = 0.0
    links.new(bsdf.outputs['BSDF'], output.inputs['Surface'])

    base = load_image_auto(nodes, os.path.join(
        folder, "basecolor_final.png"), "BaseColor")
    diff = load_image_auto(nodes, os.path.join(
        folder, "diffuse_final.png"), "Diffuse")
    if base and diff:
        mix = nodes.new("ShaderNodeMixRGB")
        mix.inputs["Fac"].default_value = 0.5
        links.new(base.outputs["Color"], mix.inputs["Color1"])
        links.new(diff.outputs["Color"], mix.inputs["Color2"])
        links.new(mix.outputs["Color"], bsdf.inputs["Base Color"])
    elif base:
        links.new(base.outputs["Color"], bsdf.inputs["Base Color"])
    elif diff:
        links.new(diff.outputs["Color"], bsdf.inputs["Base Color"])

    # normal + height
    current_normal = None
    normal = load_image_auto(nodes, os.path.join(
        folder, "normal_final.png"), "Normal", 'Non-Color')
    if normal:
        normal_map = nodes.new("ShaderNodeNormalMap")
        links.new(normal.outputs["Color"], normal_map.inputs["Color"])
        current_normal = normal_map

    height = load_image_auto(nodes, os.path.join(
        folder, "height_final.png"), "Height", 'Non-Color')
    if height:
        bump1 = nodes.new("ShaderNodeBump")
        bump1.inputs["Strength"].default_value = 1.0
        bump1.inputs["Distance"].default_value = 1.0
        links.new(height.outputs["Color"], bump1.inputs["Height"])
        if current_normal:
            links.new(current_normal.outputs["Normal"], bump1.inputs["Normal"])
        current_normal = bump1

    disp = load_image_auto(nodes, os.path.join(
        folder, "displacement_final.png"), "Displacement", 'Non-Color')
    if disp:
        bump2 = nodes.new("ShaderNodeBump")
        bump2.inputs["Strength"].default_value = 0.8
        bump2.inputs["Distance"].default_value = 0.5
        links.new(disp.outputs["Color"], bump2.inputs["Height"])
        if current_normal:
            links.new(current_normal.outputs["Normal"], bump2.inputs["Normal"])
        current_normal = bump2

    if current_normal:
        links.new(current_normal.outputs["Normal"], bsdf.inputs["Normal"])

    # RMS maps
    metal = load_image_auto(nodes, os.path.join(
        folder, "metallic_final.png"), "Metallic", 'Non-Color')
    if metal:
        links.new(clamp_scalar(nodes, links, metal), bsdf.inputs["Metallic"])
    rough = load_image_auto(nodes, os.path.join(
        folder, "roughness_final.png"), "Roughness", 'Non-Color')
    if rough:
        links.new(clamp_scalar(nodes, links, rough), bsdf.inputs["Roughness"])
    spec = load_image_auto(nodes, os.path.join(
        folder, "specular_final.png"), "Specular", 'Non-Color')
    if spec:
        links.new(clamp_scalar(nodes, links, spec), bsdf.inputs["Specular"])

    mat.cycles.displacement_method = 'BUMP'
    obj.data.materials.clear()
    obj.data.materials.append(mat)

scene.render.image_settings.file_format = 'PNG'
scene.render.resolution_x = 1280
scene.render.resolution_y = 960
scene.render.resolution_percentage = 100
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

# Clean up unused data
for image in bpy.data.images:
    if not image.users:
        bpy.data.images.remove(image)

bpy.ops.file.pack_all()
blend_path = os.path.abspath(os.path.join(output_dir, "material_check.blend"))
bpy.ops.wm.save_as_mainfile(filepath=blend_path)

video_path = os.path.join(output_dir, "output_video.mp4")
scene.frame_start = 0
scene.frame_end = num_views - 1
scene.sequence_editor_create()

for s in scene.sequence_editor.sequences_all:
    scene.sequence_editor.sequences.remove(s)

bpy.ops.sequencer.image_strip_add(
    directory=output_dir,
    files=[{"name": f"render_{i:03d}.png"} for i in range(num_views)],
    relative_path=True,
    frame_start=0
)

scene.render.image_settings.file_format = 'FFMPEG'
scene.render.ffmpeg.format = 'MPEG4'
scene.render.ffmpeg.codec = 'H264'
scene.render.ffmpeg.constant_rate_factor = 'HIGH'
scene.render.ffmpeg.ffmpeg_preset = 'GOOD'
scene.render.fps = 24
scene.render.filepath = video_path
bpy.ops.render.render(animation=True)
