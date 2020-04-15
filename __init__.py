rigify_info = {
	"name": "CloudRig"
}

from .operators import regenerate_rigify_rigs
from .operators import refresh_drivers
from .operators import mirror_rigify
from . import ui
from . import cloud_generator

import bpy, os
from bpy.props import StringProperty

# We overwrite Rigify's Remove External Feature Set operator such that when a feature set is removed, its unregister() is called.
# This is a hack or rather a test, and ideally this would at some point be added to Rigify itself, along with calling the featureset's register() when it is loaded.
from shutil import rmtree
from rigify.feature_set_list import DATA_OT_rigify_remove_feature_set, get_module_safe, get_install_path
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
		featureset = self.featureset

		module = get_module_safe(featureset)
		if module and hasattr(module, 'unregister') and callable(module.unregister):
			module.unregister()

		addon_prefs = context.preferences.addons['rigify'].preferences
		rigify_config_path = get_install_path()
		if rigify_config_path:
			set_path = os.path.join(rigify_config_path, featureset)
			if os.path.exists(set_path):
				rmtree(set_path)

		addon_prefs.update_external_rigs(force=True)
		return {'FINISHED'}


from bpy.utils import register_class
from bpy.utils import unregister_class

def register():
	regenerate_rigify_rigs.register()
	refresh_drivers.register()
	ui.register()

	cloud_generator.register()
	mirror_rigify.register()

	unregister_class(DATA_OT_rigify_remove_feature_set)
	register_class(DATA_OT_rigify_remove_and_unregister_feature_set)

def unregister():
	print("Unregistering CloudRig...")
	regenerate_rigify_rigs.unregister()
	refresh_drivers.unregister()
	mirror_rigify.unregister()

	ui.unregister()
	cloud_generator.unregister()

	unregister_class(DATA_OT_rigify_remove_and_unregister_feature_set)
	register_class(DATA_OT_rigify_remove_feature_set)

# TODO: This register is only called when Blender is started, NOT when the feature set is added to Rigify. I'm not sure how that would be achieved.
register()