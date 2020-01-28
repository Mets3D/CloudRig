import bpy
import os
from .. import shared

class CloudUtilities:
	# Utility functions are the ones that probably won't be sub-classed because they perform a very specific task.

	def select_layers(self, layerlist, additive=False):
		shared.set_layers(self.obj.data, layerlist, additive)

	def load_widget(self, name):
		""" Load custom shapes by appending them from a blend file, unless they already exist in this file. """
		# If it's already loaded, return it.
		wgt_name = "WGT_"+name
		wgt_ob = bpy.data.objects.get(wgt_name)
		if not wgt_ob:
			# Loading bone shape object from file
			filename = "Widgets.blend"
			filedir = os.path.dirname(os.path.realpath(__file__))
			blend_path = os.path.join(filedir, filename)

			with bpy.data.libraries.load(blend_path) as (data_from, data_to):
				for o in data_from.objects:
					if o == wgt_name:
						data_to.objects.append(o)
			
			wgt_ob = bpy.data.objects.get(wgt_name)
			if not wgt_ob:
				print("WARNING: Failed to load bone shape: " + wgt_name)
		if wgt_ob not in self.widgets:
			self.widgets.append(wgt_ob)
		
		return wgt_ob

	def store_parent_switch_info(self, limb_name, child_names, parent_names, prop_bone, prop_name, category):
		info = {
			"child_names" : child_names,		# List of child bone names that will be affected by the parent swapping. Often just one.
			"parent_names" : parent_names,		# List of (arbitrary) names, in order, that should be displayed for each parent option in the UI.
			"prop_bone" : prop_bone,			# Name of the properties bone that contains the property that should be changed by the parent switch operator.
			"prop_name" : prop_name, 			# Name of the property
		}

		if "parents" not in self.obj:
			self.obj["parents"] = {}

		if category not in self.obj["parents"]:
			self.obj["parents"][category] = {}
		
		self.obj["parents"][category][limb_name] = info

	def make_name(self, prefixes=[], base="", suffixed=[]):
		return make_name(prefixed, base, suffixes)
	
	def slice_name(self, name):
		return slice_name(name)

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
