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

def register():
	from bpy.utils import register_class
	regenerate_rigify_rigs.register()
	refresh_drivers.register()
	mirror_rigify.register()

	cloud_generator.register()
	ui.register()

def unregister():
	"""Hopefully one day Rigify will call unregister() for feature sets that are removed. Until then, this is useless."""
	from bpy.utils import unregister_class
	regenerate_rigify_rigs.unregister()
	refresh_drivers.unregister()
	mirror_rigify.unregister()

	cloud_generator.unregister()
	ui.unregister()

register()