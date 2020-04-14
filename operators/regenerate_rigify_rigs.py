import bpy

from ..ui import is_cloud_metarig
from ..rigs.cloud_utils import EnsureVisible

def safe_generate(context, metarig, target_rig):
	# Generating requires the metarig to be the active object, and the target rig to be visible.
	
	meta_visible = EnsureVisible(metarig)
	rig_visible = EnsureVisible(target_rig)

	# Generate.
	context.view_layer.objects.active = metarig
	if is_cloud_metarig(metarig):
		bpy.ops.pose.cloudrig_generate()
	else:
		bpy.ops.pose.rigify_generate()

	meta_visible.restore()
	rig_visible.restore()

def rigify_cleanup(context, rig):
	# TODO: This should be taken care of by CloudGenerator.
	""" Rigify does some nasty things so late in the generation process that it cannot be handled from a custom featureset's code, so I'll put it here. """
	# Delete driver on pass_index
	rig.driver_remove("pass_index")
	# Delete rig_ui.py from blend file
	text = bpy.data.texts.get("rig_ui.py")
	if text:
		bpy.data.texts.remove(text)

class Regenerate_Rigify_Rigs(bpy.types.Operator):
	""" Regenerate all Rigify rigs in the file. (Only works on metarigs that have an existing target rig.) """
	bl_idname = "object.regenerate_all_rigify_rigs"
	bl_label = "Regenerate All Rigify Rigs"
	bl_options = {'REGISTER', 'UNDO'}

	def execute(self, context):
		for o in bpy.data.objects:
			if o.type!='ARMATURE': continue
			if o.data.rigify_target_rig:
				metarig = o
				target_rig = o.data.rigify_target_rig
				if target_rig:
					safe_generate(context, metarig, target_rig)
				# rigify_cleanup(context, target_rig)

		bpy.ops.object.refresh_drivers(selected_only=False)

		return { 'FINISHED' }

def register():
	from bpy.utils import register_class
	register_class(Regenerate_Rigify_Rigs)

def unregister():
	from bpy.utils import unregister_class
	unregister_class(Regenerate_Rigify_Rigs)