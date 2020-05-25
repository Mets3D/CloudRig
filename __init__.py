rigify_info = {
	"name": "CloudRig"
}

from .operators import regenerate_rigify_rigs
from .operators import refresh_drivers
from .operators import mirror_rigify
from . import cloud_generator
from . import ui

import bpy, os
from bpy.props import StringProperty


# This allows you to right click on a button and link to documentation
def cloudrig_manual_map():
	url_manual_prefix = "https://gitlab.com/blender/CloudRig/-/wikis/"
	url_manual_mapping = (
		("bpy.ops.pose.cloudrig_generate", "Custom-Properties"),
		("cloudrigproperties*", "")
	)
	return url_manual_prefix, url_manual_mapping

def register():
	from bpy.utils import register_class, register_manual_map
	regenerate_rigify_rigs.register()
	refresh_drivers.register()
	mirror_rigify.register()

	cloud_generator.register()
	ui.register()

	register_manual_map(cloudrig_manual_map)

def unregister():
	"""Hopefully one day Rigify will call unregister() for feature sets that are removed. Until then, this is useless."""
	from bpy.utils import unregister_class, unregister_manual_map
	unregister_manual_map(cloudrig_manual_map)

	regenerate_rigify_rigs.unregister()
	refresh_drivers.unregister()
	mirror_rigify.unregister()

	cloud_generator.unregister()
	ui.unregister()

register()