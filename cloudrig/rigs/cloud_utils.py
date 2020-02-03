import bpy
import os
from .. import shared

class CloudUtilities:
	# Utility functions that probably won't be overriden by a sub-class because they perform a very specific task.

	def register_parent(self, bone, name):
		if name in self.parent_candidates:
			print("WARNING: OVERWRITING REGISTERED PARENT: %s, %s" %(bone.name, name))
		self.parent_candidates[name] = bone

	def get_parent_candidates(self, candidates={}):
		""" Go recursively up the rig element hierarchy. Collect and return a list of the registered parent bones from each rig."""
		
		for parent_name in self.parent_candidates.keys():
			candidates[parent_name] = self.parent_candidates[parent_name]

		if self.rigify_parent:
			return self.rigify_parent.get_parent_candidates(candidates)
		
		return candidates

	def select_layers(self, layerlist, additive=False):
		shared.set_layers(self.obj.data, layerlist, additive)

	def load_widget(self, name):
		""" Load custom shapes by appending them from a blend file, unless they already exist in this file. """
		# If it's already loaded, return it.
		wgt_name = "WGT_"+name
		wgt_ob = bpy.data.objects.get(wgt_name)
		
		exists = wgt_ob is not None
		overwrite = self.generator.metarig.data.rigify_force_widget_update

		if exists and not overwrite:
			return wgt_ob

		# If it exists, and we want to update it, rename it while we append the new one...
		if wgt_ob:
			wgt_ob.name = wgt_ob.name + "_temp"
			wgt_ob.data.name = wgt_ob.data.name + "_temp"
		

		# Loading bone shape object from file
		filename = "Widgets.blend"
		filedir = os.path.dirname(os.path.realpath(__file__))
		blend_path = os.path.join(filedir, filename)

		with bpy.data.libraries.load(blend_path) as (data_from, data_to):
			for o in data_from.objects:
				if o == wgt_name:
					data_to.objects.append(o)
		
		new_wgt_ob = bpy.data.objects.get(wgt_name)
		if not new_wgt_ob:
			print("WARNING: Failed to load bone shape: " + wgt_name)
		elif wgt_ob:
			# Update original object with new one's data, then delete new object.
			old_data_name = wgt_ob.data.name
			wgt_ob.data = new_wgt_ob.data
			wgt_ob.name = wgt_name
			bpy.data.meshes.remove(bpy.data.meshes.get(old_data_name))
			bpy.data.objects.remove(new_wgt_ob)

		if wgt_ob not in self.widgets:
			self.widgets.append(wgt_ob)
		
		return wgt_ob

	def load_ui_script(self):
		# Check if it already exists
		script_name = "cloudrig.py"
		text = bpy.data.texts.get(script_name)
		# If not, create it.
		if not text:
			text = bpy.data.texts.new(name=script_name)
		
		text.clear()
		text.use_module = True

		filename = script_name
		filedir = os.path.dirname(os.path.realpath(__file__))
		filedir = os.path.split(filedir)[0]

		readfile = open(os.path.join(filedir, filename), 'r')

		for line in readfile:
			text.write(line)
		readfile.close()

		# Run UI script
		exec(text.as_string(), {})

		return text

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

	@staticmethod
	def make_name(prefixes=[], base="", suffixed=[]):
		return make_name(prefixed, base, suffixes)
	
	@staticmethod
	def slice_name(name):
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
