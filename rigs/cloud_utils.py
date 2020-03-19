import bpy
import os
from .. import layers
from ..definitions.driver import Driver
from ..definitions.custom_props import CustomProp

class CloudUtilities:
	# Utility functions that probably won't be overriden by a sub-class because they perform a very specific task.
	# If a class inherits this class, it's also expected to inherit CloudBaseRig - These are only split up for organizational purposes.

	def store_ui_data(self, ui_area, row_name, col_name, info, default=0.0, _min=0.0, _max=1.0):
		""" Store some data in the rig, organized in a way which the UI script expects. 
		ui_area: One of a list of pre-defined strings that the UI script recognizes, that describes a panel or area in the UI. Eg, "fk_hinges", "ik_switches".
		row_name: A row in the UI area.
		col_name: A column within the row.
		info: The info to store, usually a dictionary. At minimum, this is {prop_bone : "Name of Properties Bone", prop_id : "Name of Property that controls this setting"}
		The values from info param are used to create a custom property on prop_bone, named prop_id.
		"""
		if ui_area not in self.obj.data:
			self.obj.data[ui_area] = {}

		if row_name not in self.obj.data[ui_area]:
			self.obj.data[ui_area][row_name] = {}

		self.obj.data[ui_area][row_name][col_name] = info
		
		# Create custom property.
		prop_bone = self.bone_infos.find(info['prop_bone'])
		prop_id = info['prop_id']
		prop_bone.custom_props[prop_id] = CustomProp(
			prop_id, 
			default=default, 
			_min=_min,
			_max=_max
		)

	def hinge_setup(self, bone, category, *, 
		prop_bone, prop_name, default_value=0.0, 
		parent_bone=None, head_tail=0, 
		hng_name=None, limb_name=None
	):
		# Initialize some defaults
		if not hng_name:
			sliced = slice_name(bone.name)
			sliced[0].insert(0, "HNG")
			hng_name = make_name(*sliced)
		if not parent_bone:
			parent_bone = bone.parent
		if not limb_name:
			limb_name = "Hinge: " + self.side_suffix + " " + slice_name(bone.name)[1]
		
		info = {
			"prop_bone"			: prop_bone.name,
			"prop_id" 			: prop_name,

			"operator" : "pose.snap_simple",
			"bones" : [bone.name]
		}

		# Store UI info
		self.store_ui_data("fk_hinges", category, limb_name, info, default=default_value)

		# Create Hinge helper bone
		hng_bone = self.bone_infos.bone(
			name			= hng_name,
			source			= bone, 
			bone_group 		= 'Body: FK Helper Bones',
			hide_select		= self.mch_disable_select
		)

		# Hinge Armature constraint
		hng_bone.add_constraint(self.obj, 'ARMATURE', 
			targets = [
				{
					"subtarget" : 'root'
				},
				{
					"subtarget" : str(parent_bone)
				}
			],
		)

		# Hinge Armature constraint driver
		drv1 = Driver()
		drv1.expression = "var"
		var1 = drv1.make_var("var")
		var1.type = 'SINGLE_PROP'
		var1.targets[0].id_type='OBJECT'
		var1.targets[0].id = self.obj
		var1.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (str(prop_bone), prop_name)

		drv2 = drv1.clone()
		drv2.expression = "1-var"

		data_path1 = 'constraints["Armature"].targets[0].weight'
		data_path2 = 'constraints["Armature"].targets[1].weight'
		
		hng_bone.drivers[data_path1] = drv1
		hng_bone.drivers[data_path2] = drv2

		# Hinge Copy Location constraint
		hng_bone.add_constraint(self.obj, 'COPY_LOCATION', true_defaults=True,
			target = self.obj,
			subtarget = str(parent_bone),
			head_tail = head_tail
		)

		# Parenting
		bone.parent = hng_bone

	def register_parent(self, bone, name):
		if name in self.parent_candidates:
			print("WARNING: OVERWRITING REGISTERED PARENT: %s, %s" %(bone.name, name))
		self.parent_candidates[name] = bone

	def get_parent_candidates(self, candidates={}):
		""" Go recursively up the rig element hierarchy. Collect and return a list of the registered parent bones from each rig."""
		
		for parent_name in self.parent_candidates.keys():
			candidates[parent_name] = self.parent_candidates[parent_name]

		if self.rigify_parent and hasattr(self.rigify_parent, "get_parent_candidates"):
			return self.rigify_parent.get_parent_candidates(candidates)
		
		return candidates

	def select_layers(self, layerlist, additive=False):
		layers.set_layers(self.obj.data, layerlist, additive)

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
		else:
			wgt_ob = new_wgt_ob

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
			if 'SCRIPT_ID' in line:
				line = line.replace("SCRIPT_ID", self.script_id)
			text.write(line)
		readfile.close()

		# Run UI script
		exec(text.as_string(), {})

		return text

	def rig_child(self, child_bone, parent_names, prop_bone, prop_name):
		""" Rig a child with multiple switchable parents, using Armature constraint and drivers.
		This requires:
			child_bone: The child bone.
			parent_names: Parent identifiers(NOT BONE NAMES!) to search for among registered parent identifiers (These are hard-coded identifiers such as 'Hips', 'Torso', etc.)
			prop_bone: Bone which stores the property that controls the parent switching.
			prop_name: Name of said property on the prop_bone.
		Return list of parent names for which a registered parent candidate was found and rigged.
		"""

		# Test that at least one of the parents exists.
		parent_candidates = self.get_parent_candidates()
		found_parents = []
		for pn in parent_names:
			if pn in list(parent_candidates.keys()):
				found_parents.append(pn)
		if len(found_parents) == 0: 
			print("No parents to be rigged for %s." %child_bone.name)
			return found_parents

		# Create parent bone for the bone that stores the Armature constraint.
		# NOTE: Bones with Armature constraints should never be exposed to the animator directly because it breaks snapping functionality!
		arm_con_bone = self.create_parent_bone(child_bone)
		arm_con_bone.name = "Parents_" + child_bone.name
		arm_con_bone.custom_shape = None
		arm_con_bone.bone_group = "Body: IK-MCH - IK Mechanism Bones"

		targets = []
		for pn in parent_names:
			if pn not in parent_candidates.keys():
				continue
			pb = parent_candidates[pn]
			targets.append({
				"subtarget" : pb.name
			})

			drv = Driver()
			drv.expression = "parent==%d" %(len(targets)-1)
			var = drv.make_var("parent")
			var.type = 'SINGLE_PROP'
			var.targets[0].id_type = 'OBJECT'
			var.targets[0].id = self.obj
			var.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (prop_bone.name, prop_name)

			data_path = 'constraints["Armature"].targets[%d].weight' %(len(targets)-1)
			
			arm_con_bone.drivers[data_path] = drv

		# Add armature constraint
		arm_con_bone.add_constraint(self.obj, 'ARMATURE', 
			targets = targets
		)

		return found_parents

	def create_parent_bone(self, child):
		"""Copy a bone, prefix it with "P", make the bone shape a bit bigger and parent the bone to this copy."""
		sliced = slice_name(child.name)
		sliced[0].append("P")
		parent_name = make_name(*sliced)
		parent_bone = self.bone_infos.bone(
			parent_name, 
			child, 
			custom_shape = child.custom_shape,
			custom_shape_scale = child.custom_shape_scale*1.1,
			bone_group = child.bone_group,
			parent = child.parent,
			hide_select	= self.mch_disable_select
		)

		child.parent = parent_bone
		return parent_bone

	def create_dsp_bone(self, parent, center=False):
		"""Create a bone to be used as another control's custom_shape_transform."""
		dsp_name = "DSP-" + parent.name
		dsp_bone = self.bone_infos.bone(
			name = dsp_name, 
			source = parent,
			bbone_width = parent.bbone_width*0.5,
			only_transform = True,
			custom_shape = None, 
			parent = parent,
			bone_group = 'DSP - Display Transform Helpers',
			hide_select	= self.mch_disable_select
		)
		parent.dsp_bone = dsp_bone
		if center:
			dsp_bone.put(parent.center, scale_length=0.3, scale_width=1.5)
		parent.custom_shape_transform = dsp_bone
		return dsp_bone

	def make_bbone_scale_drivers(self, boneinfo):
		bi = boneinfo
		armature = self.obj

		my_d = Driver()
		my_d.expression = "var/scale"
		my_var = my_d.make_var("var")
		my_var.type = 'TRANSFORMS'
		
		var_tgt = my_var.targets[0]
		var_tgt.id = armature
		var_tgt.transform_space = 'WORLD_SPACE'
		
		scale_var = my_d.make_var("scale")
		scale_var.type = 'TRANSFORMS'
		scale_tgt = scale_var.targets[0]
		scale_tgt.id = armature
		scale_tgt.transform_space = 'WORLD_SPACE'
		scale_tgt.transform_type = 'SCALE_Y'
		
		# Scale In X/Y
		if (bi.bbone_handle_type_start == 'TANGENT' and bi.bbone_custom_handle_start):
			var_tgt.bone_target = bi.bbone_custom_handle_start

			var_tgt.transform_type = 'SCALE_X'
			bi.drivers["bbone_scaleinx"] = my_d.clone()

			var_tgt.transform_type = 'SCALE_Z'
			bi.drivers["bbone_scaleiny"] = my_d.clone()
		
		# Scale Out X/Y
		if (bi.bbone_handle_type_end == 'TANGENT' and bi.bbone_custom_handle_end):
			var_tgt.bone_target = bi.bbone_custom_handle_end
			
			var_tgt.transform_type = 'SCALE_Z'
			bi.drivers["bbone_scaleouty"] = my_d.clone()

			var_tgt.transform_type = 'SCALE_X'
			bi.drivers["bbone_scaleoutx"] = my_d.clone()

		### Ease In/Out
		my_d = Driver()
		my_d.expression = "scale-Y"

		scale_var = my_d.make_var("scale")
		scale_var.type = 'TRANSFORMS'
		scale_tgt = scale_var.targets[0]
		scale_tgt.id = armature
		scale_tgt.transform_type = 'SCALE_Y'
		scale_tgt.transform_space = 'LOCAL_SPACE'

		Y_var = my_d.make_var("Y")
		Y_var.type = 'TRANSFORMS'
		Y_tgt = Y_var.targets[0]
		Y_tgt.id = armature
		Y_tgt.transform_type = 'SCALE_AVG'
		Y_tgt.transform_space = 'LOCAL_SPACE'

		# Ease In
		if (bi.bbone_handle_type_start == 'TANGENT' and bi.bbone_custom_handle_start):
			Y_tgt.bone_target = scale_tgt.bone_target = bi.bbone_custom_handle_start
			bi.drivers["bbone_easein"] = my_d.clone()

		# Ease Out
		if (bi.bbone_handle_type_end == 'TANGENT' and bi.bbone_custom_handle_end):
			Y_tgt.bone_target = scale_tgt.bone_target = bi.bbone_custom_handle_end
			bi.drivers["bbone_easeout"] = my_d.clone()

	def ensure_bone_group(self, name, group_def={}):
		ensure_bone_group(self.obj, name, group_def)

	def init_bone_groups(self):
		"""Go through every boneinfo and check for bone groups that don't exist on the rig yet.
		Check for them on the metarig first. If it exists there, use the colors from there, 
		otherwise create the bonegroup on both rigs with the default settings found in group_defs.
		"""
		metarig = self.generator.metarig
		rig = self.obj

		group_defs = layers.group_defs

		for bi in self.bone_infos.bones:
			bg_name = bi.bone_group
			if bg_name == "": continue

			group_def = dict()
			# Find definition for this group.
			if bg_name in group_defs:
				group_def = dict(group_defs[bg_name])
			
			# Try getting the bone group from the metarig.
			meta_bg = metarig.pose.bone_groups.get(bg_name)
			if meta_bg and meta_bg.color_set=='CUSTOM':
				# If it exists, override the definition.
				group_def['normal'] = meta_bg.colors.normal.copy()
				group_def['select'] = meta_bg.colors.select.copy()
				group_def['active'] = meta_bg.colors.active.copy()
			else:
				ensure_bone_group(metarig, bg_name, group_def)
			
			# Ensure bone group exists on the generated rig.
			self.ensure_bone_group(bg_name, group_def)

	@staticmethod
	def lock_transforms(obj, loc=True, rot=True, scale=True):
		return lock_transforms(obj, loc, rot, scale)

	@staticmethod
	def make_name(prefixes=[], base="", suffixes=[]):
		return make_name(prefixes, base, suffixes)
	
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


def lock_transforms(obj, loc=True, rot=True, scale=True):
	if type(loc)==list:
		obj.lock_location = loc
	else:
		obj.lock_location = [loc, loc, loc]

	if type(rot)==list:
		obj.lock_rotation = rot[:3]
		if len(rot)==4:
			obj.lock_rotation_w = rot[-1]
	else:
		obj.lock_rotation = [rot, rot, rot]
		obj.lock_rotation_w = rot

	if type(scale)==list:
		obj.lock_scale = scale
	else:
		obj.lock_scale = [scale, scale, scale]

def ensure_bone_group(armature, name, group_def={}):
	"""Find or create and return a bone group on the armature."""
	bg = armature.pose.bone_groups.get(name)
	if bg:
		return bg

	bg = armature.pose.bone_groups.new(name=name)
	for prop in ['normal', 'select', 'active']:
		if prop in group_def:
			bg.color_set='CUSTOM'
			setattr(bg.colors, prop, group_def[prop][:])
	return bg