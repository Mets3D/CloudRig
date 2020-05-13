import bpy
import os
from ..definitions.driver import Driver
from ..definitions.custom_props import CustomProp

class CloudUtilities:
	# Utility functions that probably won't be overriden by a sub-class because they perform a very specific task.
	# If a class inherits this class, it's also expected to inherit CloudBaseRig - These are only split up for organizational purposes.

	def add_ui_data(self, ui_area, row_name, col_name, info, default=0.0, _min=0.0, _max=1.0):
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

	# TODO: Move this to cloud_fk_chain.py?
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
		self.add_ui_data("fk_hinges", category, limb_name, info, default=default_value)

		# Create Hinge helper bone
		BODY_MECH = 8
		hng_bone = self.bone_infos.bone(
			name			= hng_name
			,source			= bone
			,bone_group 	= bone.bone_group
			,layers			= bone.layers
			,hide_select	= self.mch_disable_select
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
		var1.targets[0].data_path = f'pose.bones["{prop_bone.name}"]["{prop_name}"]'

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
		return hng_bone

	def register_parent(self, bone, name):
		if name in self.parent_candidates:
			print(f"WARNING: OVERWRITING REGISTERED PARENT: {bone.name}, {name}")
		self.parent_candidates[name] = bone

	def get_parent_candidates(self, candidates={}):
		""" Go recursively up the rig element hierarchy. Collect and return a list of the registered parent bones from each rig."""
		
		for parent_name in self.parent_candidates.keys():
			candidates[parent_name] = self.parent_candidates[parent_name]

		if self.rigify_parent and hasattr(self.rigify_parent, "get_parent_candidates"):
			return self.rigify_parent.get_parent_candidates(candidates)
		
		return candidates

	def load_widget(self, name):
		""" Load custom shapes by appending them from a blend file, unless they already exist in this file. """
		# If it's already loaded, return it.
		wgt_name = "WGT-"+name
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
			return
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
			print(f"No parents to be rigged for {child_bone.name}.")
			return found_parents

		# Create parent bone for the bone that stores the Armature constraint.
		# NOTE: Bones with Armature constraints should never be exposed to the animator directly because it breaks snapping functionality!
		arm_con_bone = self.create_parent_bone(child_bone)
		arm_con_bone.name = "Parents_" + child_bone.name
		arm_con_bone.custom_shape = None
		# BODY_MECH = 8
		# arm_con_bone.bone_group = self.generator.bone_groups.ensure(
		# 	name = "Parent Switching Helpers"
		# 	,layers = [BODY_MECH]
		# )

		targets = []
		for pn in parent_names:
			if pn not in parent_candidates.keys():
				continue
			pb = parent_candidates[pn]
			targets.append({
				"subtarget" : pb.name
			})

			drv = Driver()
			drv.expression = f"parent=={len(targets)-1}"
			var = drv.make_var("parent")
			var.type = 'SINGLE_PROP'
			var.targets[0].id_type = 'OBJECT'
			var.targets[0].id = self.obj
			var.targets[0].data_path = f'pose.bones["{prop_bone.name}"]["{prop_name}"]'

			data_path = f'constraints["Armature"].targets[{len(targets)-1}].weight'
			
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
			name				= parent_name 
			,source				= child
			,custom_shape		= child.custom_shape
			,custom_shape_scale = child.custom_shape_scale * 1.1
			,bone_group			= child.bone_group
			,layers				= child.layers
			,parent 			= child.parent
			,hide_select		= self.mch_disable_select
		)

		child.parent = parent_bone
		return parent_bone

	def create_dsp_bone(self, parent, center=False):
		"""Create a bone to be used as another control's custom_shape_transform."""
		dsp_name = "DSP-" + parent.name
		dsp_bone = self.bone_infos.bone(
			name			= dsp_name
			,source			= parent
			,bbone_width	= parent.bbone_width*0.5
			,only_transform = True
			,custom_shape	= None
			,parent			= parent
			,bone_group		= self.bone_groups["Display Transform Helpers"]
			,layers			= self.bone_layers["Display Transform Helpers"]
			,hide_select	= self.mch_disable_select
		)
		parent.dsp_bone = dsp_bone
		if center:
			dsp_bone.put(parent.center, scale_length=0.3, scale_width=1.5)
		parent.custom_shape_transform = dsp_bone
		return dsp_bone

	def meta_bone(self, bone_name, pose=False):
		""" Find and return a bone in the metarig. """
		if self.obj.mode=='EDIT' and not pose:
			return self.generator.metarig.data.edit_bones.get(bone_name)
		else:
			return self.generator.metarig.pose.bones.get(bone_name)

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

	def vector_along_bone_chain(self, chain, length=0, index=-1):
		return vector_along_bone_chain(chain, length, index)

	@staticmethod
	def datablock_from_str(collprop, string):
		return datablock_from_str(collprop, string)

	@staticmethod
	def set_layers(obj, layerlist, additive=False):
		return set_layers(obj, layerlist, additive)

	@staticmethod
	def lock_transforms(obj, loc=True, rot=True, scale=True):
		return lock_transforms(obj, loc, rot, scale)

	def add_prefix_to_name(self, name, new_prefix):
		""" The most common case of making a bone name based on another one is to add a prefix to it. """
		sliced_name = self.slice_name(name)
		sliced_name[0].append(new_prefix)
		return self.make_name(*sliced_name)

	def make_name(self, prefixes=[], base="", suffixes=[]):
		return make_name(prefixes, base, suffixes, self.generator.prefix_separator, self.generator.suffix_separator)
	
	def slice_name(self, name):
		return slice_name(name, self.generator.prefix_separator, self.generator.suffix_separator)
	
	@staticmethod
	def ensure_visible(obj):
		return EnsureVisible(obj)
	
	@staticmethod
	def flip_name(from_name, only=True, must_change=False):
		return flip_name(from_name, only, must_change)
	
	@staticmethod
	def flat_vector(vec):
		return flat(vec)

def datablock_from_str(collprop, string):
	""" Workaround to T59106. Using PointerProperty causes error spam in console. """
	found = collprop.get(string)
	if found: return found

	while string.startswith(" "):
		string = string[1:]
	
	found = collprop.get(string)
	if found: return found

def make_name(prefixes=[], base="", suffixes=[], prefix_separator="-", suffix_separator="."):
	# In our naming convention, prefixes are separated by dashes and suffixes by periods, eg: DSP-FK-UpperArm_Parent.L.001
	# Trailing zeroes should be avoided though, but that's not done by this function(for now?)
	name = ""
	for pre in prefixes:
		name += pre + prefix_separator
	name += base
	for suf in suffixes:
		name += suffix_separator + suf
	return name

def slice_name(name, prefix_separator="-", suffix_separator="."):
	prefixes = name.split(prefix_separator)[:-1]
	suffixes = name.split(suffix_separator)[1:]
	base = name.split(prefix_separator)[-1].split(suffix_separator)[0]
	return [prefixes, base, suffixes]

def lock_transforms(obj, loc=True, rot=True, scale=True):
	if type(loc) in (list, tuple):
		obj.lock_location = loc
	else:
		obj.lock_location = [loc, loc, loc]

	if type(rot) in (list, tuple):
		obj.lock_rotation = rot[:3]
		if len(rot)==4:
			obj.lock_rotation_w = rot[-1]
	else:
		obj.lock_rotation = [rot, rot, rot]
		obj.lock_rotation_w = rot

	if type(scale) in (list, tuple):
		obj.lock_scale = scale
	else:
		obj.lock_scale = [scale, scale, scale]

def vector_along_bone_chain(chain, length=0, index=-1):
	"""On a bone chain, find the point a given length down the chain. Return its position and direction."""
	if index > -1:
		# Instead of using bone length, simply return the location and direction of a bone at a given index.
		
		# If the index is too high, return the tail of the bone.
		if index >= len(chain):
			b = chain[-1]
			return (b.tail.copy(), b.vec.normalized())
		
		b = chain[index]
		direction = b.vec.normalized()

		if index > 0:
			prev_bone = chain[index-1]
			direction = (b.vec + prev_bone.vec).normalized()
		return (b.head.copy(), direction)

	
	length_cumultative = 0
	for b in chain:
		if length_cumultative + b.length > length:
			length_remaining = length - length_cumultative
			direction = b.vec.normalized()
			loc = b.head + direction * length_remaining
			return (loc, direction)
		else:
			length_cumultative += b.length
	
	length_remaining = length - length_cumultative
	direction = chain[-1].vec.normalized()
	loc = chain[-1].tail + direction * length_remaining
	return (loc, direction)

def set_layers(obj, layerlist, additive=False):
	"""Layer setting function that can take either a list of booleans or a list of ints.
	In case of booleans, it must be a 32 length list, and we set the bone's layer list to the passed list.
	In case of ints, enable the layers with the indicies in the passed list.
	
	obj can either be a bone or an armature.
	"""
	layers = obj.layers[:]

	if not additive:
		layers = [False]*32
	
	for i, e in enumerate(layerlist):
		if type(e)==bool:
			assert len(layerlist)==32, f"ERROR: Layer assignment expected a list of 32 booleans, got {len(layerlist)}."
			layers[i] = e
		elif type(e)==int:
			layers[e] = True
	
	obj.layers = layers[:]

def recursive_search_layer_collection(collName, layerColl=None):
	# Recursivly transverse layer_collection for a particular name
	# This is the only way to set active collection as of 14-04-2020.
	if not layerColl:
		layerColl = bpy.context.view_layer.layer_collection
	
	found = None
	if (layerColl.name == collName):
		return layerColl
	for layer in layerColl.children:
		found = recursive_search_layer_collection(collName, layer)
		if found:
			return found

def set_active_collection(collection):
	layer_collection = recursive_search_layer_collection(collection.name)
	bpy.context.view_layer.active_layer_collection = layer_collection

def flip_name(from_name, only=True, must_change=False):
	# based on BLI_string_flip_side_name in https://developer.blender.org/diffusion/B/browse/master/source/blender/blenlib/intern/string_utils.c
	# If only==True, only replace the first occurrence of a side identifier in the string, eg. "Left_Eyelid.L" would become "Right_Eyelid.L". With only==False, it would instead return "Right_Eyelid.R"
	# if must_change==True, raise an error if the string couldn't be flipped.

	l = len(from_name)	# Number of characters from left to right, that we still care about. At first we care about all of them.
	
	# Handling .### cases
	if("." in from_name):
		# Make sure there are only digits after the last period
		after_last_period = from_name.split(".")[-1]
		before_last_period = from_name.replace("."+after_last_period, "")
		all_digits = True
		for c in after_last_period:
			if( c not in "0123456789" ):
				all_digits = False
				break
		# If that is so, then we don't care about the characters after this last period.
		if(all_digits):
			l = len(before_last_period)
	
	new_name = from_name[:l]
	
	left = 				['left',  'Left',  'LEFT', 	'.l', 	  '.L', 		'_l', 				'_L',				'-l',	   '-L', 	'l.', 	   'L.',	'l_', 			 'L_', 			  'l-', 	'L-']
	right_placehold = 	['*rgt*', '*Rgt*', '*RGT*', '*dotl*', '*dotL*', 	'*underscorel*', 	'*underscoreL*', 	'*dashl*', '*dashL', '*ldot*', '*Ldot', '*lunderscore*', '*Lunderscore*', '*ldash*','*Ldash*']
	right = 			['right', 'Right', 'RIGHT', '.r', 	  '.R', 		'_r', 				'_R',				'-r',	   '-R', 	'r.', 	   'R.',	'r_', 			 'R_', 			  'r-', 	'R-']
	
	def flip_sides(list_from, list_to, new_name):
		for side_idx, side in enumerate(list_from):
			opp_side = list_to[side_idx]
			if(only):
				# Only look at prefix/suffix.
				if(new_name.startswith(side)):
					new_name = new_name[len(side):]+opp_side
					break
				elif(new_name.endswith(side)):
					new_name = new_name[:-len(side)]+opp_side
					break
			else:
				if("-" not in side and "_" not in side):	# When it comes to searching the middle of a string, sides must Strictly a full word or separated with . otherwise we would catch stuff like "_leg" and turn it into "_reg".
					# Replace all occurences and continue checking for keywords.
					new_name = new_name.replace(side, opp_side)
					continue
		return new_name
	
	new_name = flip_sides(left, right_placehold, new_name)
	new_name = flip_sides(right, left, new_name)
	new_name = flip_sides(right_placehold, right, new_name)
	
	# Re-add trailing digits (.###)
	new_name = new_name + from_name[l:]

	if(must_change):
		assert new_name != from_name, "Failed to flip string: " + from_name
	
	return new_name

def flat(vec):
	""" Return a copy of a vector with its two absolute lowest values set to 0. Useful for making vectors world-aligned. """
	new_vec = vec.copy()

	maxabs = 0
	max_index = 0
	for i, val in enumerate(vec):
		if abs(val) > maxabs:
			maxabs = abs(val)
			max_index = i

	for i in range(0, len(vec)):
		if i != max_index:
			new_vec[i] = 0

	return new_vec

class EnsureVisible:
	""" Ensure an object is visible, then reset it to how it was before. """

	def __init__(self, obj):
		""" Ensure an object is visible, and create this small object to manage that object's visibility-ensured-ness. """
		self.obj_name = obj.name
		self.obj_hide = obj.hide_get()
		self.obj_hide_viewport = obj.hide_viewport
		self.temp_coll = None
		
		if not obj.visible_get():
			obj.hide_set(False)
			obj.hide_viewport = False

		if not obj.visible_get():
			# If the object is still not visible, we need to move it to a visible collection. To not break other scripts though, we should restore the active collection afterwards.
			active_coll = bpy.context.collection

			coll_name = "temp_visible"
			temp_coll = bpy.data.collections.get(coll_name)
			if not temp_coll:
				temp_coll = bpy.data.collections.new(coll_name)
			if coll_name not in bpy.context.scene.collection.children:
				bpy.context.scene.collection.children.link(temp_coll)
		
			if obj.name not in temp_coll.objects:
				temp_coll.objects.link(obj)
			
			self.temp_coll = temp_coll

			set_active_collection(active_coll)
	
	def restore(self):
		""" Restore visibility settings to their original state. """
		obj = bpy.data.objects.get(self.obj_name)
		if not obj: return

		obj.hide_set(self.obj_hide)
		obj.hide_viewport = self.obj_hide_viewport

		# Remove object from temp collection
		if self.temp_coll and obj.name in self.temp_coll.objects:
			self.temp_coll.objects.unlink(obj)

			# Delete temp collection if it's empty now.
			if len(self.temp_coll.objects) == 0:
				bpy.data.collections.remove(self.temp_coll)
				self.temp_coll = None