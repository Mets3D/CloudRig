rigify_info = {
	"name": "CloudRig"
}

import bpy
from bpy.props import *
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
		
		layout.prop(obj.data, "cloudrig_double_root")

# TODO: Not sure how to get Rigify to call our register() and unregister() for us.
def register():
	bpy.types.Armature.cloudrig_double_root = BoolProperty(name="Double Root",
		description="CloudRig: Create two root controls",
		default=False)
	bpy.types.Armature.cloudrig_options = BoolProperty(name="CloudRig Settings",
		description="Show CloudRig Settings",
		default=False)
	
	regenerate_rigify_rigs.register()
	refresh_drivers.register()

	bpy.types.DATA_PT_rigify_buttons.append(draw_cloud_generator_options)

def unregister():
	ArmStore = bpy.types.Armature
	del ArmStore.cloudrig_double_root
	del ArmStore.cloudrig_options

	regenerate_rigify_rigs.unregister()
	refresh_drivers.unregister()

	bpy.types.DATA_PT_rigify_buttons.remove(draw_cloud_generator_options)

register()