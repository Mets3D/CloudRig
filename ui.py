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
	layout = self.layout
	obj = context.object

	if not is_cloud_metarig(context.object):
		self.draw_old(context)
		return
	
	if obj.mode not in {'POSE', 'OBJECT'}:
		return

	layout.operator("pose.cloudrig_generate", text="Generate CloudRig")

	cloudrig = obj.data.cloudrig

	icon = 'TRIA_DOWN' if cloudrig.options else 'TRIA_RIGHT'
	layout.prop(cloudrig, "options", toggle=True, icon=icon)
	if not cloudrig.options: return
	
	layout.prop(obj.data, "rigify_target_rig")
	layout.prop_search(cloudrig, "custom_script", bpy.data, "texts")

	root_row = layout.row()
	root_row.prop(cloudrig, "create_root")
	if cloudrig.create_root:
		root_row.prop(cloudrig, "double_root")

	mech_row = layout.row()
	mech_row.prop(cloudrig, "mechanism_selectable")
	if cloudrig.mechanism_selectable:
		mech_row.prop(cloudrig, "mechanism_movable")

	layout.prop(obj.data, "rigify_force_widget_update")

	naming_row = layout.row()
	naming_row.column().label(text="Prefix Separator")
	naming_row.column().prop(cloudrig, "prefix_separator", text="")
	naming_row.column().label(text="Suffix Separator")
	naming_row.column().prop(cloudrig, "suffix_separator", text="")
	
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

	cloudrig = obj.data.cloudrig
	layout.separator()

	icon = 'TRIA_DOWN' if cloudrig.override_options else 'TRIA_RIGHT'
	layout.prop(cloudrig, "override_options", toggle=True, icon=icon)
	if cloudrig.override_options:
		layout.prop(cloudrig, "override_def_layers")
		if cloudrig.override_def_layers:
			layout.prop(cloudrig, "def_layers", text="")

		layout.prop(cloudrig, "override_mch_layers")
		if cloudrig.override_mch_layers:
			layout.prop(cloudrig, "mch_layers", text="")

		layout.prop(cloudrig, "override_org_layers")
		if cloudrig.override_org_layers:
			layout.prop(cloudrig, "org_layers", text="")

class CloudRigLayerInit(bpy.types.Operator):
	"""Initialize armature rigify layers"""

	bl_idname = "pose.cloudrig_layer_init"
	bl_label = "Add Rigify Layers (CloudRig)"
	bl_options = {'UNDO', 'INTERNAL'}

	def execute(self, context):
		obj = context.object
		arm = obj.data
		for i in range(len(arm.rigify_layers), len(arm.layers)):
			arm.rigify_layers.add()

		return {'FINISHED'}

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
	ui_label_with_linebreak(layout, "Organize Layers panel layout. Layers without a name and layers beginning with $ will not be shown.")
	ui_label_with_linebreak(layout, "In the generated rig, the same layers will be active and protected as on the metarig.")

	# Ensure that the layers exist
	if len(arm.rigify_layers) != len(arm.layers):
		layout.operator("pose.cloudrig_layer_init")
		return

	# UI
	main_row = layout.row(align=True).split(factor=0.05)
	col_number = main_row.column()
	col_layer = main_row.column()

	for i in range(len(arm.rigify_layers)):
		if i in (0, 16):
			col_number.label(text="")
			text = ("Top" if i==0 else "Bottom") + " Row"
			row = col_layer.row()
			row.label(text=text)

		row = col_layer.row(align=True)
		col_number.label(text=str(i+1) + '.')
		rigify_layer = arm.rigify_layers[i]
		icon = 'RESTRICT_VIEW_OFF' if arm.layers[i] else 'RESTRICT_VIEW_ON'
		row.prop(arm, "layers", index=i, text="", toggle=True, icon=icon)
		icon = 'FAKE_USER_ON' if arm.layers_protected[i] else 'FAKE_USER_OFF'
		row.prop(arm, "layers_protected", index=i, text="", toggle=True, icon=icon)
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

def ui_label_with_linebreak(layout, text):
	words = text.split(" ")
	word_index = 0

	lines = [""]
	line_index = 0

	cur_line_length = 0
	# Try to determine maximum allowed characters in this line, based on pixel width of the area. 
	# Not a great solution, but better than nothing.
	max_line_length = bpy.context.area.width/8

	while word_index < len(words):
		word = words[word_index]

		if cur_line_length + len(word)+1 < max_line_length:
			word_index += 1
			cur_line_length += len(word)+1
			lines[line_index] += word + " "
		else:
			cur_line_length = 0
			line_index += 1
			lines.append("")
	
	for line in lines:
		layout.label(text=line)

def register():
	from bpy.utils import register_class
	register_class(CloudGenerate)
	register_class(CloudRigLayerInit)
	
	
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
	unregister_class(CloudRigLayerInit)
	
	# Restore Rigify panels' draw functions.
	bpy.types.DATA_PT_rigify_buttons.draw = bpy.types.DATA_PT_rigify_buttons.draw_old
	bpy.types.DATA_PT_rigify_bone_groups.draw = bpy.types.DATA_PT_rigify_bone_groups.draw_old
	bpy.types.DATA_PT_rigify_layer_names.draw = bpy.types.DATA_PT_rigify_layer_names.draw_old