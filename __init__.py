rigify_info = {
	"name": "CloudRig"
}

from .operators import regenerate_rigify_rigs
from .operators import refresh_drivers
from . import ui

import bpy, os
from bpy.props import *
from rigify.feature_set_list import *

class DATA_OT_rigify_remove_and_unregister_feature_set(bpy.types.Operator):
	bl_idname = "wm.rigify_remove_feature_set"
	bl_label = "Remove External Feature Set"
	bl_description = "Remove external feature set (rigs, metarigs, ui templates)"
	bl_options = {"REGISTER", "UNDO", "INTERNAL"}

	featureset: StringProperty(maxlen=1024, options={'HIDDEN', 'SKIP_SAVE'})

	@classmethod
	def poll(cls, context):
		return True

	def invoke(self, context, event):
		return context.window_manager.invoke_confirm(self, event)

	def execute(self, context):
		addon_prefs = context.preferences.addons['rigify'].preferences
		print("Hijacked remove featureset operator, WOOHOOO")
		rigify_config_path = get_install_path()
		if rigify_config_path:
			set_path = os.path.join(rigify_config_path, self.featureset)
			if os.path.exists(set_path):
				rmtree(set_path)

		addon_prefs.update_external_rigs(force=True)
		return {'FINISHED'}


# TODO: Not sure how to get Rigify to call our register() and unregister() for us.
def register():
	from bpy.utils import register_class
	regenerate_rigify_rigs.register()
	refresh_drivers.register()
	ui.register()
	# register_class(DATA_OT_rigify_remove_and_unregister_feature_set)

def unregister():
	from bpy.utils import unregister_class
	regenerate_rigify_rigs.unregister()
	refresh_drivers.unregister()
	ui.unregister()
	unregister_class(DATA_OT_rigify_remove_and_unregister_feature_set)

register()