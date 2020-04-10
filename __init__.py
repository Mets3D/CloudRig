rigify_info = {
	"name": "CloudRig"
}

import bpy
from bpy.props import BoolProperty, StringProperty, EnumProperty
from .operators import regenerate_rigify_rigs
from .operators import refresh_drivers
from rigify import ui as rigify_ui

def is_cloud_metarig(rig):
	if rig.type=='ARMATURE' and 'rig_id' not in rig.data:
		for b in rig.pose.bones:
			if 'cloud' in b.rigify_type and b.rigify_type!='cloud_bone':
				return True
	return False

def draw_cloud_generator_options(self, context):
	layout = self.layout
	obj = context.object

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

# TODO: Not sure how to get Rigify to call our register() and unregister() for us.
def register():
	bpy.types.Armature.cloudrig_options = BoolProperty(
		name		 = "CloudRig Settings"
		,description = "Show CloudRig Settings"
		,default	 = False
	)
	bpy.types.Armature.cloudrig_create_root = BoolProperty(
		name		 = "Create Root"
		,description = "Create the root control"
		,default	 = True
	)
	bpy.types.Armature.cloudrig_double_root = BoolProperty(
		name		 = "Double Root"
		,description = "Create two root controls"
		,default	 = False
	)
	bpy.types.Armature.cloudrig_custom_script = StringProperty(
		name		 = "Custom Script"
		,description = "Execute a python script after the rig is generated"
	)
	bpy.types.Armature.cloudrig_mechanism_movable = BoolProperty(
		name		 = "Movable Helpers"
		,description = "Whether helper bones can be moved or not"
		,default	 = True
	)
	bpy.types.Armature.cloudrig_mechanism_selectable = BoolProperty(
		name		 = "Selectable Helpers"
		,description = "Whether helper bones can be selected or not"
		,default	 = True
	)
	bpy.types.Armature.cloudrig_properties_bone = BoolProperty(
		name		 = "Properties Bone"
		,description = "Specify a bone to store Properties on. This bone doesn't have to exist in the metarig"
		,default	 = True
	)

	separators = [
		(".", ".", "."),
		("-", "-", "-"),
		("_", "_", "_"),
	]
	bpy.types.Armature.cloudrig_prefix_separator = EnumProperty(
		name		 = "Prefix Separator"
		,description = "Character that separates prefixes in the bone names"
		,items 		 = separators
		,default	 = "-"
	)
	bpy.types.Armature.cloudrig_suffix_separator = EnumProperty(
		name		 = "Suffix Separator"
		,description = "Character that separates suffixes in the bone names"
		,items 		 = separators
		,default	 = "."
	)
	
	regenerate_rigify_rigs.register()
	refresh_drivers.register()

	bpy.types.DATA_PT_rigify_buttons.append(draw_cloud_generator_options)

	bpy.types.DATA_PT_rigify_bone_groups.draw_old = bpy.types.DATA_PT_rigify_bone_groups.draw
	bpy.types.DATA_PT_rigify_bone_groups.draw = draw_cloud_bone_group_options

	bpy.types.DATA_PT_rigify_layer_names.draw_old = bpy.types.DATA_PT_rigify_layer_names.draw
	bpy.types.DATA_PT_rigify_layer_names.draw = draw_cloud_layer_names

def unregister():
	ArmStore = bpy.types.Armature
	del ArmStore.cloudrig_create_root
	del ArmStore.cloudrig_double_root
	del ArmStore.cloudrig_options
	del ArmStore.cloudrig_custom_script
	del ArmStore.cloudrig_mechanism_selectable
	del ArmStore.cloudrig_mechanism_movable
	del ArmStore.cloudrig_prefix_separator
	del ArmStore.cloudrig_suffix_separator

	regenerate_rigify_rigs.unregister()
	refresh_drivers.unregister()

	bpy.types.DATA_PT_rigify_buttons.remove(draw_cloud_generator_options)

register()