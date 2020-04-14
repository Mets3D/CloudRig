rigify_info = {
	"name": "CloudRig"
}

from .operators import regenerate_rigify_rigs
from .operators import refresh_drivers
from . import ui
from . import cloud_generator

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
		# First, unregister the feature set, if there is an unregister() in its __init__.py.
		
		module = get_module_safe(self.featureset)
		print("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA REMOVING FEATURE SET")
		if module and hasattr(module, 'unfuck') and callable(module.unfuck):
			print("AAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAAA HAS unfuck")
			module.unfuck()

		addon_prefs = context.preferences.addons['rigify'].preferences
		rigify_config_path = get_install_path()
		if rigify_config_path:
			set_path = os.path.join(rigify_config_path, self.featureset)
			if os.path.exists(set_path):
				rmtree(set_path)

		addon_prefs.update_external_rigs(force=True)
		return {'FINISHED'}


# TODO: Not sure how to get Rigify to call our register() and unregister() for us.
from bpy.utils import register_class
from bpy.utils import unregister_class

def register():
	regenerate_rigify_rigs.register()
	refresh_drivers.register()
	ui.register()
	cloud_generator.register()

	unregister_class(DATA_OT_rigify_remove_feature_set)
	register_class(DATA_OT_rigify_remove_and_unregister_feature_set)

def unfuck():
	print("Unregistering CloudRig...")
	regenerate_rigify_rigs.unregister()
	refresh_drivers.unregister()
	ui.unregister()
	cloud_generator.unregister()

	unregister_class(DATA_OT_rigify_remove_and_unregister_feature_set)
	register_class(DATA_OT_rigify_remove_feature_set)

register()