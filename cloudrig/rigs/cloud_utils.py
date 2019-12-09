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

def make_name(prefixes=[], base="", suffixes=[]):
	# In our naming convention, prefixes are separated by dashes and suffixes by periods, eg: DSP-FK-UpperArm_Parent.L.001
	# Trailing zeroes should be avoided though, but that's not done by this function(for now?)
	name = ""
	for pre in prefixes:
		name += pre+"-"
	name += base
	for suf in suffixes:
		name += "."+suf
	return name

def slice_name(name):
	prefixes = name.split("-")[:-1]
	suffixes = name.split(".")[1:]
	base = name.split("-")[-1].split(".")[0]
	return [prefixes, base, suffixes]
