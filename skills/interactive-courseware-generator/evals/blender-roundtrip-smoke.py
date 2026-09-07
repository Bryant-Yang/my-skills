"""Blender environment smoke test; does not validate arbitrary teaching models."""
import argparse
import sys
import bpy
import json
from pathlib import Path
from mathutils import Vector
parser = argparse.ArgumentParser()
parser.add_argument('--output-dir', required=True)
args = parser.parse_args(sys.argv[sys.argv.index('--') + 1:])
out = Path(args.output_dir).resolve()
out.mkdir(parents=True, exist_ok=False)
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
scene=bpy.context.scene
scene.unit_settings.system='METRIC'
scene.unit_settings.scale_length=1.0
bpy.ops.mesh.primitive_cube_add(size=1)
obj=bpy.context.object
obj.name='teaching_block'
obj.dimensions=(0.120,0.040,0.020)
bpy.context.view_layer.update()
bpy.ops.object.transform_apply(location=False,rotation=False,scale=True)
expected=[0.020,0.040,0.120]
pre=sorted(obj.dimensions)
assert all(abs(a-b)<1e-6 for a,b in zip(pre,expected)),pre
bpy.ops.wm.save_as_mainfile(filepath=str(out/'model.blend'))
bpy.ops.export_scene.gltf(filepath=str(out/'model.glb'),export_format='GLB')
assert (out/'model.blend').stat().st_size>0
assert (out/'model.glb').stat().st_size>0
bpy.ops.object.select_all(action='SELECT')
bpy.ops.object.delete(use_global=False)
bpy.ops.import_scene.gltf(filepath=str(out/'model.glb'))
obj=bpy.data.objects.get('teaching_block')
assert obj is not None
bpy.context.view_layer.update()
coords=[obj.matrix_world @ Vector(v) for v in obj.bound_box]
post=sorted(max(v[i] for v in coords)-min(v[i] for v in coords) for i in range(3))
errors=[abs(a-b) for a,b in zip(post,expected)]
assert max(errors)<1e-6,post
result={'blender':bpy.app.version_string,'expected_dimensions_m_sorted':expected,'before_export_m_sorted':pre,'after_import_m_sorted':post,'max_error_m':max(errors),'tolerance_m':1e-6,'name_preserved':True,'scope':'parameterized cuboid only; no assembly, animation, page or learner test'}
(out/'result.json').write_text(json.dumps(result,indent=2)+'\n')
print('COURSEWARE_BPY_RESULT',json.dumps(result))
