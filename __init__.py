rigify_info = {
	"name": "CloudRig"
}

import bpy
from bpy.props import BoolProperty, StringProperty
from .operators import regenerate_rigify_rigs
from .operators import refresh_drivers

def draw_cloud_generator_options(self, context):
	layout = self.layout
	obj = context.object

	if obj.mode in {'POSE', 'OBJECT'}:
		# Check if any bones in the rig are assigned a cloudrig element.
		found_cloud_type = False
		for b in obj.pose.bones:
			if 'cloud' in b.rigify_type and b.rigify_type!='cloud_bone':
				found_cloud_type = True
				break
		if not found_cloud_type: return

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
	
	regenerate_rigify_rigs.register()
	refresh_drivers.register()

	bpy.types.DATA_PT_rigify_buttons.append(draw_cloud_generator_options)

def unregister():
	ArmStore = bpy.types.Armature
	del ArmStore.cloudrig_create_root
	del ArmStore.cloudrig_double_root
	del ArmStore.cloudrig_options
	del ArmStore.cloudrig_custom_script
	del ArmStore.cloudrig_mechanism_selectable
	del ArmStore.cloudrig_mechanism_movable

	regenerate_rigify_rigs.unregister()
	refresh_drivers.unregister()

	bpy.types.DATA_PT_rigify_buttons.remove(draw_cloud_generator_options)

register()