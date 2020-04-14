import bpy
from . import cloud_generator
from rigify.utils.errors import MetarigError
from rigify.ui import rigify_report_exception
import traceback

def is_cloud_metarig(rig):
	if rig.type=='ARMATURE' and 'rig_id' not in rig.data:
		for b in rig.pose.bones:
			if 'cloud' in b.rigify_type and b.rigify_type!='cloud_bone':
				return True
	return False

def draw_cloud_generator_options(self, context):
	if not is_cloud_metarig(context.object):
		self.draw_old(context)
		return

	layout = self.layout
	obj = context.object

	layout.operator("pose.cloudrig_generate", text="Generate CloudRig")

	if obj.mode in {'POSE', 'OBJECT'} and is_cloud_metarig(obj):
		icon = 'TRIA_DOWN' if obj.data.cloudrig_options else 'TRIA_RIGHT'
		layout.prop(obj.data, "cloudrig_options", toggle=True, icon=icon)
		if not obj.data.cloudrig_options: return
		
		layout.prop_search(obj.data, "cloudrig_custom_script", bpy.data, "texts")

		root_row = layout.row()
		root_row.prop(obj.data, "cloudrig_create_root")
		if obj.data.cloudrig_create_root:
			root_row.prop(obj.data, "cloudrig_double_root")

		mech_row = layout.row()
		mech_row.prop(obj.data, "cloudrig_mechanism_selectable")
		if obj.data.cloudrig_mechanism_selectable:
			mech_row.prop(obj.data, "cloudrig_mechanism_movable")

		naming_row = layout.row()
		naming_row.column().label(text="Prefix Separator")
		naming_row.column().prop(obj.data, "cloudrig_prefix_separator", text="")
		naming_row.column().label(text="Suffix Separator")
		naming_row.column().prop(obj.data, "cloudrig_suffix_separator", text="")

def draw_cloud_bone_group_options(self, context):
	""" Hijack Rigify's Bone Group panel and replace it with our own. """
	obj = context.object
	# If the current rig doesn't have any cloudrig elements, draw Rigify's UI.
	if not is_cloud_metarig(obj):
		bpy.types.DATA_PT_rigify_bone_groups.draw_old(self, context)
		return
	
	# Otherwise we draw our own.
	layout = self.layout
	color_row = layout.row(align=True)
	color_row.prop(obj.data, "rigify_colors_lock", text="Unified Select/Active Colors")
	if obj.data.rigify_colors_lock:
		color_row.prop(obj.data.rigify_selection_colors, "select", text="")
		color_row.prop(obj.data.rigify_selection_colors, "active", text="")
		# TODO: If possible, we would draw a BoolVectorProperty layer selector for each existing bonegroup in the metarig.

def draw_cloud_layer_names(self, context):
	""" Hijack Rigify's Layer Names panel and replace it with our own. """
	obj = context.object
	# If the current rig doesn't have any cloudrig elements, draw Rigify's UI.
	if not is_cloud_metarig(obj):
		bpy.types.DATA_PT_rigify_layer_names.draw_old(self, context)
		return
	
	obj = context.object
	arm = obj.data
	layout = self.layout

	# UI
	main_row = layout.row(align=True).split(factor=0.05)
	col_number = main_row.column()
	col_layer = main_row.column()
	for i in range(28):
		col_number.label(text=str(i+1) + '.')
		rigify_layer = arm.rigify_layers[i]
		row = col_layer.row()
		icon = 'RESTRICT_VIEW_OFF' if arm.layers[i] else 'RESTRICT_VIEW_ON'
		row.prop(arm, "layers", index=i, text="", toggle=True, icon=icon)
		row.prop(rigify_layer, "name", text="")
		row.prop(rigify_layer, "row", text="UI Row")

class CloudGenerate(bpy.types.Operator):
	"""Generates a rig from the active metarig armature using the CloudRig generator"""

	bl_idname = "pose.cloudrig_generate"
	bl_label = "CloudRig Generate Rig"
	bl_options = {'UNDO'}
	bl_description = 'Generates a rig from the active metarig armature using the CloudRig generator'

	def execute(self, context):
		try:
			cloud_generator.generate_rig(context, context.object)
		except MetarigError as rig_exception:
			traceback.print_exc()

			rigify_report_exception(self, rig_exception)
		except Exception as rig_exception:
			traceback.print_exc()

			self.report({'ERROR'}, 'Generation has thrown an exception: ' + str(rig_exception))
		finally:
			bpy.ops.object.mode_set(mode='OBJECT')

		return {'FINISHED'}

def register():
	from bpy.utils import register_class
	register_class(CloudGenerate)
	
	# Hijack Rigify panels' draw functions.
	bpy.types.DATA_PT_rigify_buttons.draw_old = bpy.types.DATA_PT_rigify_buttons.draw
	bpy.types.DATA_PT_rigify_buttons.draw = draw_cloud_generator_options

	bpy.types.DATA_PT_rigify_bone_groups.draw_old = bpy.types.DATA_PT_rigify_bone_groups.draw
	bpy.types.DATA_PT_rigify_bone_groups.draw = draw_cloud_bone_group_options

	bpy.types.DATA_PT_rigify_layer_names.draw_old = bpy.types.DATA_PT_rigify_layer_names.draw
	bpy.types.DATA_PT_rigify_layer_names.draw = draw_cloud_layer_names

def unregister():
	from bpy.utils import unregister_class
	unregister_class(CloudGenerate)
	
	# Restore Rigify panels' draw functions.
	bpy.types.DATA_PT_rigify_buttons.draw = bpy.types.DATA_PT_rigify_buttons.draw_old
	bpy.types.DATA_PT_rigify_bone_groups.draw = bpy.types.DATA_PT_rigify_bone_groups.draw_old
	bpy.types.DATA_PT_rigify_layer_names.draw = bpy.types.DATA_PT_rigify_layer_names.draw_old