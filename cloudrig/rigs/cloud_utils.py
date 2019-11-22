import bpy
import os

def load_widget(name):
	""" Load custom shapes by appending them from a blend file, unless they already exist in this file. """
	# If it's already loaded, return it.
	wgt_name = "WGT_"+name
	wgt_ob = bpy.data.objects.get(wgt_name)
	if wgt_ob: return wgt_ob

	# Loading bone shape object from file
	filename = "Widgets.blend"
	filedir = os.path.dirname(os.path.realpath(__file__))
	blend_path = os.path.join(filedir, filename)

	with bpy.data.libraries.load(blend_path) as (data_from, data_to):
		for o in data_from.objects:
			if o == wgt_name:
				data_to.objects.append(o)
	
	wgt_ob = bpy.data.objects.get(wgt_name)
	if wgt_ob: return wgt_ob
	print("WARNING: Failed to load bone shape: " + wgt_name)

def make_dsp_bone(obj, parent):
	# Create a new bone.
	# Name is the original bone in full prefixed with DSP-.
	# Assign to DSP group.
	# Parent it to source bone.
	# Return it so it can be moved.
	pass
