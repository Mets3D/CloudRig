"Version: 1.4"
"2020-01-24"

import bpy
from bpy.props import *
from mathutils import Vector, Matrix
from math import *

### CODE FROM RIGIFY ###
import math
import traceback
from mathutils import Euler, Quaternion
from rna_prop_ui import rna_idprop_quote_path

class POSE_OT_rigify_switch_parent(bpy.types.Operator):
	# Credit for all code in this class to Rigify.
	bl_idname = "pose.rigify_switch_parent"
	bl_label = "Switch Parent (Keep Transform)"
	bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
	bl_description = "Switch parent, preserving the bone position and orientation"

	bones:		 StringProperty(name="Control Bone")
	prop_bone:	StringProperty(name="Property Bone")
	prop_id:	  StringProperty(name="Property")
	parent_names: StringProperty(name="Parent Names")
	locks:		bpy.props.BoolVectorProperty(name="Locked", size=3, default=[False,False,False])

	parent_items = [('0','None','None')]

	selected: bpy.props.EnumProperty(
		name='Selected Parent',
		items=lambda s,c: POSE_OT_rigify_switch_parent.parent_items
	)
	
	def execute(self, context):
		obj = context.active_object
		self.keyflags = self.get_autokey_flags(context, ignore_keyset=True)
		self.keyflags_switch = self.add_flags_if_set(self.keyflags, {'INSERTKEY_AVAILABLE'})

		try:
			matrices = []
			bones = self.bones.split(", ")
			for bone in bones:
				matrices.append( self.save_frame_state(context, obj, bone) )
			
			self.apply_frame_state(context, obj, matrices, bones)

		except Exception as e:
			traceback.print_exc()
			self.report({'ERROR'}, 'Exception: ' + str(e))

		return {'FINISHED'}

	def save_frame_state(self, context, obj, bone):
		return self.get_transform_matrix(obj, bone, with_constraints=False)

	def apply_frame_state(self, context, obj, old_matrices, bones):
		# Change the parent
		# TODO: Instead of relying on scene settings(auto-keying, keyingset, etc) maybe it would be better to have a custom boolean to decide whether to insert keyframes or not. Ask animators.
		self.set_custom_property_value(
			obj, self.prop_bone, self.prop_id, int(self.selected),
			keyflags=self.keyflags_switch
		)

		context.view_layer.update()

		# Set the transforms to restore position
		for i, bone in enumerate(bones):
			old_matrix = old_matrices[i]
			self.set_transform_from_matrix(
				obj, bone, old_matrix, keyflags=self.keyflags,
				no_loc=self.locks[0], no_rot=self.locks[1], no_scale=self.locks[2]
			)

	def draw(self, _context):
		col = self.layout.column()
		col.prop(self, 'selected', expand=True)

	def invoke(self, context, event):
		pose = context.active_object.pose

		if (not pose or not self.parent_names
			#or self.bone not in pose.bones
			or self.prop_bone not in pose.bones
			or self.prop_id not in pose.bones[self.prop_bone]):
			self.report({'ERROR'}, "Invalid parameters")
			return {'CANCELLED'}

		parents = self.parent_names.split(", ")
		pitems = [(str(i), name, name) for i, name in enumerate(parents)]

		POSE_OT_rigify_switch_parent.parent_items = pitems

		self.selected = str(pose.bones[self.prop_bone][self.prop_id])

		if hasattr(self, 'draw'):
			return context.window_manager.invoke_props_popup(self, event)
		else:
			return self.execute(context)
	
	######################
	## Keyframing tools ##
	######################

	def get_keying_flags(self, context):
		"Retrieve the general keyframing flags from user preferences."
		prefs = context.preferences
		ts = context.scene.tool_settings
		flags = set()
		# Not adding INSERTKEY_VISUAL
		if prefs.edit.use_keyframe_insert_needed:
			flags.add('INSERTKEY_NEEDED')
		if prefs.edit.use_insertkey_xyz_to_rgb:
			flags.add('INSERTKEY_XYZ_TO_RGB')
		if ts.use_keyframe_cycle_aware:
			flags.add('INSERTKEY_CYCLE_AWARE')
		return flags

	def get_autokey_flags(self, context, ignore_keyset=False):
		"Retrieve the Auto Keyframe flags, or None if disabled."
		ts = context.scene.tool_settings
		if ts.use_keyframe_insert_auto and (ignore_keyset or not ts.use_keyframe_insert_keyingset):
			flags = self.get_keying_flags(context)
			if context.preferences.edit.use_keyframe_insert_available:
				flags.add('INSERTKEY_AVAILABLE')
			if ts.auto_keying_mode == 'REPLACE_KEYS':
				flags.add('INSERTKEY_REPLACE')
			return flags
		else:
			return None

	def add_flags_if_set(self, base, new_flags):
		"Add more flags if base is not None."
		if base is None:
			return None
		else:
			return base | new_flags

	def get_4d_rotlock(self, bone):
		"Retrieve the lock status for 4D rotation."
		if bone.lock_rotations_4d:
			return [bone.lock_rotation_w, *bone.lock_rotation]
		else:
			return [all(bone.lock_rotation)] * 4

	def keyframe_transform_properties(self, obj, bone_name, keyflags, *, ignore_locks=False, no_loc=False, no_rot=False, no_scale=False):
		"Keyframe transformation properties, taking flags and mode into account, and avoiding keying locked channels."
		bone = obj.pose.bones[bone_name]

		def keyframe_channels(prop, locks):
			if ignore_locks or not all(locks):
				if ignore_locks or not any(locks):
					bone.keyframe_insert(prop, group=bone_name, options=keyflags)
				else:
					for i, lock in enumerate(locks):
						if not lock:
							bone.keyframe_insert(prop, index=i, group=bone_name, options=keyflags)

		if not (no_loc or bone.bone.use_connect):
			keyframe_channels('location', bone.lock_location)

		if not no_rot:
			if bone.rotation_mode == 'QUATERNION':
				keyframe_channels('rotation_quaternion', self.get_4d_rotlock(bone))
			elif bone.rotation_mode == 'AXIS_ANGLE':
				keyframe_channels('rotation_axis_angle', self.get_4d_rotlock(bone))
			else:
				keyframe_channels('rotation_euler', bone.lock_rotation)

		if not no_scale:
			keyframe_channels('scale', bone.lock_scale)

	###############################
	## Assign and keyframe tools ##
	###############################

	def set_custom_property_value(self, obj, bone_name, prop, value, *, keyflags=None):
		"Assign the value of a custom property, and optionally keyframe it."
		from rna_prop_ui import rna_idprop_ui_prop_update
		bone = obj.pose.bones[bone_name]
		bone[prop] = value
		rna_idprop_ui_prop_update(bone, prop)
		if keyflags is not None:
			bone.keyframe_insert(rna_idprop_quote_path(prop), group=bone.name, options=keyflags)

	def get_transform_matrix(self, obj, bone_name, *, space='POSE', with_constraints=True):
		"Retrieve the matrix of the bone before or after constraints in the given space."
		bone = obj.pose.bones[bone_name]
		if with_constraints:
			return obj.convert_space(pose_bone=bone, matrix=bone.matrix, from_space='POSE', to_space=space)
		else:
			return obj.convert_space(pose_bone=bone, matrix=bone.matrix_basis, from_space='LOCAL', to_space=space)

	def set_transform_from_matrix(self, obj, bone_name, matrix, *, space='POSE', ignore_locks=False, no_loc=False, no_rot=False, no_scale=False, keyflags=None):
		"Apply the matrix to the transformation of the bone, taking locked channels, mode and certain constraints into account, and optionally keyframe it."
		bone = obj.pose.bones[bone_name]

		def restore_channels(prop, old_vec, locks, extra_lock):
			if extra_lock or (not ignore_locks and all(locks)):
				setattr(bone, prop, old_vec)
			else:
				if not ignore_locks and any(locks):
					new_vec = Vector(getattr(bone, prop))

					for i, lock in enumerate(locks):
						if lock:
							new_vec[i] = old_vec[i]

					setattr(bone, prop, new_vec)

		# Save the old values of the properties
		old_loc = Vector(bone.location)
		old_rot_euler = Vector(bone.rotation_euler)
		old_rot_quat = Vector(bone.rotation_quaternion)
		old_rot_axis = Vector(bone.rotation_axis_angle)
		old_scale = Vector(bone.scale)

		# Compute and assign the local matrix
		if space != 'LOCAL':
			matrix = obj.convert_space(pose_bone=bone, matrix=matrix, from_space=space, to_space='LOCAL')

		bone.matrix_basis = matrix

		# Restore locked properties
		restore_channels('location', old_loc, bone.lock_location, no_loc or bone.bone.use_connect)

		if bone.rotation_mode == 'QUATERNION':
			restore_channels('rotation_quaternion', old_rot_quat, self.get_4d_rotlock(bone), no_rot)
			bone.rotation_axis_angle = old_rot_axis
			bone.rotation_euler = old_rot_euler
		elif bone.rotation_mode == 'AXIS_ANGLE':
			bone.rotation_quaternion = old_rot_quat
			restore_channels('rotation_axis_angle', old_rot_axis, self.get_4d_rotlock(bone), no_rot)
			bone.rotation_euler = old_rot_euler
		else:
			bone.rotation_quaternion = old_rot_quat
			bone.rotation_axis_angle = old_rot_axis
			restore_channels('rotation_euler', old_rot_euler, bone.lock_rotation, no_rot)

		restore_channels('scale', old_scale, bone.lock_scale, no_scale)

		# Keyframe properties
		if keyflags is not None:
			self.keyframe_transform_properties(
				obj, bone_name, keyflags, ignore_locks=ignore_locks,
				no_loc=no_loc, no_rot=no_rot, no_scale=no_scale
			)

def get_rigs():
	""" Find all cloudrig armatures in the file."""
	return [o for o in bpy.data.objects if o.type=='ARMATURE' and 'cloudrig' in o]

def get_rig():
	"""If the active object is a cloudrig, return it."""
	rig = bpy.context.object
	if rig and rig.type == 'ARMATURE' and 'cloudrig' in rig:
		return rig

def get_char_bone(rig):
	for b in rig.pose.bones:
		if b.name.startswith("Properties_Character"):
			return b

def pre_depsgraph_update(scene, depsgraph=None):
	""" Runs before every depsgraph update. Is used to handle user input by detecting changes in the rig properties. """
	for rig in get_rigs():
		# Grabbing relevant data (Hardcoded for Rain - general solutions eat too much performance)
		outfit_props = rig.pose.bones.get("Properties_Outfit_Default")
		if not outfit_props: return
		if "Skin" not in outfit_props: return

		skin = outfit_props["Skin"]		
		
		# Init flags
		if('update_skin' not in rig):
			rig['update_skin'] = 0
		if('prev_skin' not in rig):
			rig['prev_skin'] = skin
		
		if skin != rig['prev_skin']:
			# Changing the scene should be done in post_depsgraph_update, otherwise we can easily cause an infinite loop of depsgraph updates.
			# So we just set a flag and read it from there.
			#rig['update_skin'] = 1
			rig['prev_skin'] = skin
			# An exception to this is material changes. If those are done in post_depsgraph_update, they don't show up in the viewport.
			update_viewport_colors(rig, skin)

viewport_color_definitions = {
	"Rain" : {
		"MAT-rain.hair" : [0.048172, 0.031896, 0.020289],
		"MAT-rain.hairband" : [0.092253, 0.322308, 0.428690],
		"MAT-rain.eyebrows" : [0.048172, 0.031896, 0.020289],
		"MAT-rain.top" : [0.800000, 0.800000, 0.800000],
	},
	"Hail" : {
		"MAT-rain.hair" : [0.018500, 0.293081, 0.313989],
		"MAT-rain.hairband" : [0.013702, 0.036004, 0.054995],
		"MAT-rain.eyebrows" : [0.005661, 0.035762, 0.038372],
		"MAT-rain.top" : [0.012983, 0.035601, 0.054480],
	}
}

def update_viewport_colors(rig, skin):
	skin_name = "Rain" if skin == 1 else "Hail"
	skin_colors = viewport_color_definitions[skin_name]

	for mat_name in skin_colors.keys():
		col_prop = rig.rig_colorproperties.get(mat_name)
		if col_prop:
			col_prop.color = skin_colors[mat_name]
			col_prop.default = skin_colors[mat_name]

class Snap_FK2IK(bpy.types.Operator):
	"""Snap FK to IK chain"""
	bl_idname = "armature.snap_fk_to_ik"
	bl_label = "Snap FK to IK"
	bl_options = {'REGISTER', 'UNDO'}
	# TODO: prop_bone should be passed instead of being hardcoded to a "Properties_IKFK" bone.

	fk_bones: StringProperty()
	ik_bones: StringProperty()

	def execute(self, context):
		armature = context.object
		fk_bones = list(map(armature.pose.bones.get, self.fk_bones.split(", ")))
		ik_bones = list(map(armature.pose.bones.get, self.ik_bones.split(", ")))

		for i, fkb in enumerate(fk_bones):
			fk_bones[i].matrix = ik_bones[i].matrix
			context.evaluated_depsgraph_get().update()

		# Deselect all bones
		for b in context.selected_pose_bones:
			b.bone.select=False
			
		# Select affected bones
		for b in fk_bones:
			b.bone.select=True

		return {'FINISHED'}

class Snap_IK2FK(bpy.types.Operator):
	"""Snap IK to FK chain"""
	"""Credit for most code (for figuring out the pole target matrix) to Rigify."""	# TODO: The resulting pole target location appears to be a tiny bit imprecise.
	bl_idname = "armature.snap_ik_to_fk"
	bl_label = "Snap IK to FK"
	bl_options = {'REGISTER', 'UNDO'}

	fk_bones: StringProperty()
	ik_bones: StringProperty()
	ik_pole: StringProperty()
	double_ik_control: BoolProperty(default=True, description="Set to True if there is a double IK control.")
	
	def perpendicular_vector(self, v):
		""" Returns a vector that is perpendicular to the one given.
			The returned vector is _not_ guaranteed to be normalized.
		"""
		# Create a vector that is not aligned with v.
		# It doesn't matter what vector.  Just any vector
		# that's guaranteed to not be pointing in the same
		# direction.
		if abs(v[0]) < abs(v[1]):
			tv = Vector((1,0,0))
		else:
			tv = Vector((0,1,0))

		# Use cross prouct to generate a vector perpendicular to
		# both tv and (more importantly) v.
		return v.cross(tv)

	def set_pose_translation(self, pose_bone, mat):
		""" Sets the pose bone's translation to the same translation as the given matrix.
			Matrix should be given in bone's local space.
		"""
		if pose_bone.bone.use_local_location == True:
			pose_bone.location = mat.to_translation()
		else:
			loc = mat.to_translation()

			rest = pose_bone.bone.matrix_local.copy()
			if pose_bone.bone.parent:
				par_rest = pose_bone.bone.parent.matrix_local.copy()
			else:
				par_rest = Matrix()

			q = (par_rest.inverted() @ rest).to_quaternion()
			pose_bone.location = q @ loc

	def get_pose_matrix_in_other_space(self, mat, pose_bone):
		""" Returns the transform matrix relative to pose_bone's current
			transform space.  In other words, presuming that mat is in
			armature space, slapping the returned matrix onto pose_bone
			should give it the armature-space transforms of mat.
			TODO: try to handle cases with axis-scaled parents better.
		"""
		rest = pose_bone.bone.matrix_local.copy()
		rest_inv = rest.inverted()
		if pose_bone.parent:
			par_mat = pose_bone.parent.matrix.copy()
			par_inv = par_mat.inverted()
			par_rest = pose_bone.parent.bone.matrix_local.copy()
		else:
			par_mat = Matrix()
			par_inv = Matrix()
			par_rest = Matrix()

		# Get matrix in bone's current transform space
		smat = rest_inv @ (par_rest @ (par_inv @ mat))

		# Compensate for non-local location
		#if not pose_bone.bone.use_local_location:
		#	loc = smat.to_translation() @ (par_rest.inverted() @ rest).to_quaternion()
		#	smat.translation = loc

		return smat

	def rotation_difference(self, mat1, mat2):
		""" Returns the shortest-path rotational difference between two
			matrices.
		"""
		q1 = mat1.to_quaternion()
		q2 = mat2.to_quaternion()
		angle = acos(min(1,max(-1,q1.dot(q2)))) * 2
		if angle > pi:
			angle = -angle + (2*pi)
		return angle

	def match_pole_target(self, ik_first, ik_last, pole, match_bone, length):
		""" Places an IK chain's pole target to match ik_first's
			transforms to match_bone.  All bones should be given as pose bones.
			You need to be in pose mode on the relevant armature object.
			ik_first: first bone in the IK chain
			ik_last:  last bone in the IK chain
			pole:  pole target bone for the IK chain
			match_bone:  bone to match ik_first to (probably first bone in a matching FK chain)
			length:  distance pole target should be placed from the chain center
		"""
		a = ik_first.matrix.to_translation()
		b = ik_last.matrix.to_translation() + ik_last.vector

		# Vector from the head of ik_first to the
		# tip of ik_last
		ikv = b - a

		# Get a vector perpendicular to ikv
		pv = self.perpendicular_vector(ikv).normalized() * length

		def set_pole(pvi):
			""" Set pole target's position based on a vector
				from the arm center line.
			"""
			# Translate pvi into armature space
			ploc = a + (ikv/2) + pvi

			# Set pole target to location
			mat = self.get_pose_matrix_in_other_space(Matrix.Translation(ploc), pole)
			self.set_pose_translation(pole, mat)

			bpy.ops.object.mode_set(mode='OBJECT')
			bpy.ops.object.mode_set(mode='POSE')

		set_pole(pv)

		# Get the rotation difference between ik_first and match_bone
		angle = self.rotation_difference(ik_first.matrix, match_bone.matrix)

		# Try compensating for the rotation difference in both directions
		pv1 = Matrix.Rotation(angle, 4, ikv) @ pv
		set_pole(pv1)
		ang1 = self.rotation_difference(ik_first.matrix, match_bone.matrix)

		pv2 = Matrix.Rotation(-angle, 4, ikv) @ pv
		set_pole(pv2)
		ang2 = self.rotation_difference(ik_first.matrix, match_bone.matrix)

		# Do the one with the smaller angle
		if ang1 < ang2:
			set_pole(pv1)
			
	@classmethod
	def poll(cls, context):
		if context.object and context.object.type=='ARMATURE': 
			return True

	def execute(self, context):
		armature = context.object

		fk_bones = list(map(armature.pose.bones.get, self.fk_bones.split(", ")))
		ik_bones = list(map(armature.pose.bones.get, self.ik_bones.split(", ")))

		ik_pole = armature.pose.bones.get(self.ik_pole)

		# Snap the last IK control to the last FK control.
		last_fk_bone = fk_bones[-1]
		last_ik_bone = ik_bones[-1]
		select_bones = [last_ik_bone, ik_pole]
		if self.double_ik_control:
			ik_parent_bone = last_ik_bone.parent
			ik_parent_bone.matrix = last_fk_bone.matrix
			select_bones.append(ik_parent_bone)
			context.evaluated_depsgraph_get().update()
		last_ik_bone.matrix = last_fk_bone.matrix
		context.evaluated_depsgraph_get().update()
		
		first_ik_bone = fk_bones[0]
		first_fk_bone = ik_bones[0]
		self.match_pole_target(first_ik_bone, last_ik_bone, ik_pole, first_fk_bone, 0.5)
		context.evaluated_depsgraph_get().update()

		# Deselect all bones
		for b in context.selected_pose_bones:
			b.bone.select=False

		# Select affected bones
		for b in select_bones:
			b.bone.select=True

		return {'FINISHED'}

class IKFK_Toggle(bpy.types.Operator):
	"Toggle between IK and FK, and snap the controls accordingly. This will NOT place any keyframes, but it will select the affected bones"
	bl_idname = "armature.ikfk_toggle"
	bl_label = "Toggle IK/FK"
	bl_options = {'REGISTER', 'UNDO'}
	
	prop_bone: StringProperty()
	prop_name: StringProperty()

	fk_bones: StringProperty()
	ik_bones: StringProperty()
	ik_pole: StringProperty()
	double_ik_control: BoolProperty(default=True)

	@classmethod
	def poll(cls, context):
		if context.object and context.object.type=='ARMATURE' and context.mode=='POSE': 
			return True

	def execute(self, context):
		if self.prop_bone != "":
			armature = context.object

			prop_bone = armature.pose.bones.get(self.prop_bone)
			if prop_bone[self.prop_name] < 1:
				bpy.ops.armature.snap_ik_to_fk(fk_bones=self.fk_bones, ik_bones=self.ik_bones, ik_pole=self.ik_pole, double_ik_control=self.double_ik_control)
				prop_bone[self.prop_name] = 1.0
			else:
				bpy.ops.armature.snap_fk_to_ik(fk_bones=self.fk_bones, ik_bones=self.ik_bones)
				prop_bone[self.prop_name] = 0.0

		return {'FINISHED'}

class Reset_Rig_Colors(bpy.types.Operator):
	"""Reset rig color properties to their stored default."""
	bl_idname = "object.reset_rig_colors"
	bl_label = "Reset Rig Colors"
	bl_options = {'REGISTER', 'UNDO'}

	@classmethod
	def poll(cls, context):
		return 'cloudrig' in context.object

	def execute(self, context):
		rig = context.object
		for cp in rig.rig_colorproperties:
			cp.color = cp.default
		return {'FINISHED'}

class Rig_ColorProperties(bpy.types.PropertyGroup):
	""" Store a ColorProperty that can be used to drive colors on the rig, and then be controlled even when the rig is linked.
	"""
	default: FloatVectorProperty(
		name='Default',
		description='',
		subtype='COLOR',
		min=0,
		max=1,
		options={'LIBRARY_EDITABLE'}
	)
	color: FloatVectorProperty(
		name='Color',
		description='',
		subtype='COLOR',
		min=0,
		max=1,
		options={'LIBRARY_EDITABLE'}
	)

class Rig_BoolProperties(bpy.types.PropertyGroup):
	""" Store a BoolProperty referencing an outfit/character property whose min==0 and max==1.
		This BoolProperty will be used to display the property as a toggle button in the UI.
	"""
	# This is currently only used for outfit/character settings, NOT rig settings. Those booleans are instead hard-coded into rig_properties.

	def update_id_prop(self, context):
		""" Callback function to update the corresponding ID property when this BoolProperty's value is changed. """
		rig = get_rig()
		rig_props = rig.rig_properties
		outfit_bone = rig.pose.bones.get("Properties_Outfit_"+rig_props.outfit)
		char_bone = get_char_bone(rig)
		for prop_owner in [outfit_bone, char_bone]:
			if(prop_owner != None):
				if(self.name in prop_owner):
					prop_owner[self.name] = self.value
		

	value: BoolProperty(
		name='Boolean Value',
		description='',
		update=update_id_prop,
		options={'LIBRARY_EDITABLE'}
	)

class Rig_Properties(bpy.types.PropertyGroup):
	""" PropertyGroup for storing fancy custom properties in.
		Character and Outfit specific properties will still be stored in their relevant Properties bones (eg. Properties_Outfit_Rain).
	"""

	def get_rig(self):
		""" Find the armature object that is using this instance (self). """

		for rig in get_rigs():
			if(rig.rig_properties == self):
				return rig

	def update_bool_properties(self, context):
		""" Create BoolProperties out of those outfit properties whose min==0 and max==1.
			These BoolProperties are necessarry because only BoolProperties can be displayed in the UI as toggle buttons.
		"""
		
		rig = self.get_rig()
		bool_props = rig.rig_boolproperties
		bool_props.clear()	# Nuke all the bool properties
		
		outfit_bone = rig.pose.bones.get("Properties_Outfit_" + self.outfit)
		char_bone = get_char_bone(rig)
		for prop_owner in [outfit_bone, char_bone]:
			if(prop_owner==None): continue
			for p in prop_owner.keys():
				if( type(prop_owner[p]) != int or p.startswith("_") ): continue
				my_min = prop_owner['_RNA_UI'].to_dict()[p]['min']
				my_max = prop_owner['_RNA_UI'].to_dict()[p]['max']
				if(my_min==0 and my_max==1):
					new_bool = bool_props.add()
					new_bool.name = p
					new_bool.value = prop_owner[p]
					new_bool.rig = rig
	
	def outfits(self, context):
		""" Callback function for finding the list of available outfits for the outfit enum.
			Based on naming convention. Bones storing an outfit's properties must be named "Properties_Outfit_OutfitName".
		"""
		rig = self.get_rig()

		outfits = []
		for b in rig.pose.bones:
			if b.name.startswith("Properties_Outfit_"):
				outfits.append(b.name.replace("Properties_Outfit_", ""))
		
		# Convert the list into what an EnumProperty expects.
		items = []
		for i, outfit in enumerate(outfits):
			items.append((outfit, outfit, outfit, i))	# Identifier, name, description, can all be the character name.
		
		# If no outfits were found, don't return an empty list so the console doesn't spam "'0' matches no enum" warnings.
		if(items==[]):
			return [(('identifier', 'name', 'description'))]
		
		return items
	
	def change_outfit(self, context):
		""" Update callback of outfit enum. """
		
		rig = self.get_rig()
		
		if( (self.outfit == '') ):
			self.outfit = self.outfits(context)[0][0]
		
		outfit_bone = rig.pose.bones.get("Properties_Outfit_"+self.outfit)
		
		if outfit_bone:
			# For outfit properties starting with "_", update the corresponding character property.
			char_bone = get_char_bone(rig)
			for key in outfit_bone.keys():
				if key.startswith("_") and key[1:] in char_bone:
					char_bone[key[1:]] = outfit_bone[key]

		self.update_bool_properties(context)

	outfit: EnumProperty(
		name="Outfit",
		items=outfits,
		update=change_outfit)
	
	render_modifiers: BoolProperty(
		name='render_modifiers',
		description='Enable SubSurf, Solidify, Bevel, etc. modifiers in the viewport')
	
	use_proxy: BoolProperty(
		name='use_proxy',
		description='Use Proxy Meshes')

class RigUI(bpy.types.Panel):
	bl_space_type = 'VIEW_3D'
	bl_region_type = 'UI'
	bl_category = 'CloudRig'
	
	@classmethod
	def poll(cls, context):
		return 'cloudrig' in context.object

	def draw(self, context):
		layout = self.layout

class RigUI_Outfits(RigUI):
	bl_idname = "OBJECT_PT_rig_ui_properties"
	bl_label = "Outfits"

	@classmethod
	def poll(cls, context):
		if(not super().poll(context)):
			return False

		# Only display this panel if there is either an outfit with options, multiple outfits, or character options.
		rig = context.object
		if(not rig): return False
		rig_props = rig.rig_properties
		bool_props = rig.rig_boolproperties
		multiple_outfits = len(rig_props.outfits(context)) > 1
		outfit_properties_bone = rig.pose.bones.get("Properties_Outfit_"+rig_props.outfit)
		char_bone = get_char_bone(rig)

		return multiple_outfits or outfit_properties_bone or char_bone

	def draw(self, context):
		layout = self.layout
		rig = context.object

		rig_props = rig.rig_properties
		bool_props = rig.rig_boolproperties
		
		def add_props(prop_owner):
			props_done = []

			def get_text(prop_name, value):
				""" If there is a property on prop_owner named $prop_name, expect it to be a list of strings and return the valueth element."""
				text = prop_name.replace("_", " ")
				if "$"+prop_name in prop_owner and type(value)==int:
					return text + ": " + prop_owner["$"+prop_name][value]
				else:
					return text

			for prop_name in prop_owner.keys():
				if( prop_name in props_done or prop_name.startswith("_") ): continue
				# Int Props
				if(prop_name not in bool_props and type(prop_owner[prop_name]) in [int, float] ):
					layout.prop(prop_owner, '["'+prop_name+'"]', slider=True, 
						text = get_text(prop_name, prop_owner[prop_name])
					)
					props_done.append(prop_name)
			# Bool Props
			for bp in bool_props:
				if(bp.name in prop_owner.keys() and bp.name not in props_done):
					layout.prop(bp, 'value', toggle=True, 
						text = get_text(bp.name, prop_owner[bp.name])
					)

		# Add character properties to the UI, if any.
		char_bone = get_char_bone(rig)
		if( char_bone ):
			add_props(char_bone)
			layout.separator()

		# Add outfit properties to the UI, if any. Always add outfit selector.
		outfit_properties_bone = rig.pose.bones.get("Properties_Outfit_"+rig_props.outfit)
		layout.prop(rig_props, 'outfit')
		if( outfit_properties_bone != None ):
			add_props(outfit_properties_bone)

class RigUI_Layers(RigUI):
	bl_idname = "OBJECT_PT_rig_ui_layers"
	bl_label = "Layers"
	
	def draw(self, context):
		layout = self.layout
		rig = context.object
		data = rig.data
		
		row_ik = layout.row()
		row_ik.prop(data, 'layers', index=0, toggle=True, text='IK')
		row_ik.prop(data, 'layers', index=16, toggle=True, text='IK Secondary')
		
		row_fk = layout.row()
		row_fk.prop(data, 'layers', index=1, toggle=True, text='FK')
		row_fk.prop(data, 'layers', index=17, toggle=True, text='FK Secondary')
		
		layout.prop(data, 'layers', index=2, toggle=True, text='Stretch')
		
		row_face = layout.row()
		row_face.column().prop(data, 'layers', index=3, toggle=True, text='Face Primary')
		row_face.column().prop(data, 'layers', index=19, toggle=True, text='Face Extras')
		row_face.column().prop(data, 'layers', index=20, toggle=True, text='Face Tweak')
		
		layout.prop(data, 'layers', index=5, toggle=True, text='Fingers')
		
		layout.row().prop(data, 'layers', index=6, toggle=True, text='Hair')
		layout.row().prop(data, 'layers', index=7, toggle=True, text='Clothes')
		
		# Draw secret layers
		if('dev' in rig and rig['dev']==1):
			layout.separator()
			layout.prop(rig, '["dev"]', text="Secret Layers")
			layout.label(text="Body")
			row = layout.row()
			row.prop(data, 'layers', index=8, toggle=True, text='Mech')
			row.prop(data, 'layers', index=9, toggle=True, text='Adjust Mech')
			row = layout.row()
			row.prop(data, 'layers', index=24, toggle=True, text='Deform')
			row.prop(data, 'layers', index=25, toggle=True, text='Adjust Deform')

			layout.label(text="Head")
			row = layout.row()
			row.prop(data, 'layers', index=11, toggle=True, text='Mech')
			row.prop(data, 'layers', index=12, toggle=True, text='Unlockers')
			row = layout.row()
			row.prop(data, 'layers', index=27, toggle=True, text='Deform')
			row.prop(data, 'layers', index=28, toggle=True, text='Hierarchy')

			layout.label(text="Other")
			death_row = layout.row()
			death_row.prop(data, 'layers', index=30, toggle=True, text='Properties')
			death_row.prop(data, 'layers', index=31, toggle=True, text='Black Box')

class RigUI_Settings(RigUI):
	bl_idname = "OBJECT_PT_rig_ui_settings"
	bl_label = "Settings"
	
	def draw(self, context):
		layout = self.layout
		rig = context.object

		rig_props = rig.rig_properties
		layout.row().prop(rig_props, 'render_modifiers', text='Enable Modifiers', toggle=True)

class RigUI_Settings_FKIK(RigUI):
	bl_idname = "OBJECT_PT_rig_ui_ikfk"
	bl_label = "FK/IK Switch"
	bl_parent_id = "OBJECT_PT_rig_ui_settings"

	def draw(self, context):
		layout = self.layout
		rig = context.object
		ikfk_props = rig.pose.bones.get('Properties_IKFK')

		ik_chains = rig["ik_chains"].to_dict()

		for cat_name in ik_chains.keys():
			category = ik_chains[cat_name]
			row = layout.row()
			for limb_name in category.keys():
				limb = category[limb_name]

				prop_bone = rig.pose.bones.get(limb['prop_bone'])
				if not prop_bone:
					print("WARNING: Limb definition has no prop_bone: %s, %s", cat_name, limb)

				col = row.column()
				sub_row = col.row(align=True)
				sub_row.prop(ikfk_props, '["' + limb["prop_name"] + '"]', slider=True, text=limb_name)
				switch = sub_row.operator(IKFK_Toggle.bl_idname, text="", icon='FILE_REFRESH')
				switch.fk_bones = ", ".join(limb["fk_names"])
				switch.ik_bones = ", ".join(limb["ik_names"])
				switch.ik_pole = limb["ik_pole_name"]
				switch.double_ik_control = limb["double_ik_control"]
				switch.prop_bone = limb["prop_bone"]
				switch.prop_name = limb["prop_name"]

class RigUI_Settings_IK(RigUI):
	bl_idname = "OBJECT_PT_rig_ui_ik"
	bl_label = "IK Settings"
	bl_parent_id = "OBJECT_PT_rig_ui_settings"

	def draw(self, context):
		layout = self.layout
		rig = context.object
		ikfk_props = rig.pose.bones.get('Properties_IKFK')

		# IK Stretch
		if 'ik_stretches' in rig:
			layout.label(text="IK Stretch")
			layout.prop(ikfk_props, '["ik_stretch_spine"]', slider=True, text='Stretchy Spine')
			layout.prop(ikfk_props, '["ik_stretch_arms"]',  slider=True, text='Stretchy Arms' )
			layout.prop(ikfk_props, '["ik_stretch_legs"]',  slider=True, text='Stretchy Legs' )

		# IK Hinge
		if 'ik_hinges' in rig:
			layout.label(text="IK Hinge")
			hand_row = layout.row()
			hand_row.prop(ikfk_props, '["ik_hinge_hand_left"]',  slider=True, text='Left Hand' )
			hand_row.prop(ikfk_props, '["ik_hinge_hand_right"]', slider=True, text='Right Hand')
			foot_row = layout.row()
			foot_row.prop(ikfk_props, '["ik_hinge_foot_left"]',  slider=True, text='Left Foot' )
			foot_row.prop(ikfk_props, '["ik_hinge_foot_right"]', slider=True, text='Right Foot')

		# IK Parents
		if 'parents' in rig:
			layout.label(text='Parents')
			ik_parents = rig['parents'].to_dict()
			for cat_name in ik_parents.keys():
				category = ik_parents[cat_name]
				row = layout.row()
				for limb_name in category.keys():
					limb = category[limb_name]
					prop_bone_name = limb['prop_bone']
					prop_bone = rig.pose.bones.get(prop_bone_name)
					if not prop_bone:
						print("WARNING: Limb definition has no prop_bone: %s, %s", cat_name, limb)
					
					col = row.column()
					sub_row = col.row(align=True)
					
					parent_names = limb['parent_names']
					prop_name = limb['prop_name']
					prop_value = prop_bone[prop_name]

					current_parent = parent_names[int(prop_value)]
					sub_row.prop(prop_bone, '["%s"]'%prop_name, slider=True, text=limb_name + ": " + current_parent)

					op = sub_row.operator('pose.rigify_switch_parent', text="", icon='COLLAPSEMENU')
					op.bones = ", ".join(limb['child_names'])
					op.prop_bone = prop_bone.name
					op.prop_id = prop_name
					op.parent_names = ", ".join(parent_names)
					op.locks = (False, False, False)

		# IK Pole Follow
		if 'ik_pole_follows' in rig:
			layout.label(text='IK Pole Follow')
			pole_row = layout.row()
			pole_row.prop(ikfk_props, '["ik_pole_follow_hands"]', slider=True, text='Arms')
			pole_row.prop(ikfk_props, '["ik_pole_follow_feet"]',  slider=True, text='Legs')

class RigUI_Settings_FK(RigUI):
	bl_idname = "OBJECT_PT_rig_ui_fk"
	bl_label = "FK Settings"
	bl_parent_id = "OBJECT_PT_rig_ui_settings"

	def draw(self, context):
		layout = self.layout
		rig = context.object
		rig_props = rig.rig_properties
		ikfk_props = rig.pose.bones.get('Properties_IKFK')
		face_props = rig.pose.bones.get('Properties_Face')

		# FK Hinge
		if 'fk_hinges' in rig:
			layout.label(text='FK Hinge')
			hand_row = layout.row()
			hand_row.prop(ikfk_props, '["fk_hinge_arm_left"]',  slider=True, text='Left Arm' )
			hand_row.prop(ikfk_props, '["fk_hinge_arm_right"]', slider=True, text='Right Arm')
			foot_row = layout.row()
			foot_row.prop(ikfk_props, '["fk_hinge_leg_left"]',  slider=True, text='Left Leg' )
			foot_row.prop(ikfk_props, '["fk_hinge_leg_right"]', slider=True, text='Right Leg')

			# Head settings
			layout.separator()
			layout.prop(face_props, '["neck_hinge"]', slider=True, text='Neck Hinge')
			layout.prop(face_props, '["head_hinge"]', slider=True, text='Head Hinge')

class RigUI_Settings_Face(RigUI):
	bl_idname = "OBJECT_PT_rig_ui_face"
	bl_label = "Face Settings"
	bl_parent_id = "OBJECT_PT_rig_ui_settings"

	def draw(self, context):
		layout = self.layout
		rig = context.object
		face_props = rig.pose.bones.get('Properties_Face')

		if 'face_settings' in rig:
			# Eyelid settings
			layout.prop(face_props, '["sticky_eyelids"]',	text='Sticky Eyelids',  slider=True)
			layout.prop(face_props, '["sticky_eyesockets"]', text='Sticky Eyerings', slider=True)

			layout.separator()
			# Mouth settings
			layout.prop(face_props, '["teeth_follow_mouth"]', text='Teeth Follow Mouth', slider=True)

			layout.label(text="Eye Target Parent")
			row = layout.row()
			eye_parents = ['Root', 'Torso', 'Torso_Loc', 'Head']
			row.prop(ikfk_props, '["eye_target_parent"]',  text=eye_parents[ikfk_props["eye_target_parent"]], slider=True)

class RigUI_Settings_Misc(RigUI):
	bl_idname = "OBJECT_PT_rig_ui_misc"
	bl_label = "Misc"
	bl_parent_id = "OBJECT_PT_rig_ui_settings"

	def draw(self, context):
		layout = self.layout
		rig = context.object
		rig_props = rig.rig_properties
		ikfk_props = rig.pose.bones.get('Properties_IKFK')
		face_props = rig.pose.bones.get('Properties_Face')

		if 'misc_settings' in rig:
			layout.label(text="Grab Parents")
			row = layout.row()
			grab_parents = ['Root', 'Hand']
			row.prop(ikfk_props, '["grab_parent_left"]',  text="Left Hand [" + grab_parents[ikfk_props["grab_parent_left"]] + "]", slider=True)
			row.prop(ikfk_props, '["grab_parent_right"]',  text="Right Hand [" + grab_parents[ikfk_props["grab_parent_right"]] + "]", slider=True)

class RigUI_Viewport_Display(RigUI):
	bl_idname = "OBJECT_PT_rig_ui_viewport_display"
	bl_label = "Viewport Display"

	def draw(self, context):
		layout = self.layout
		rig = context.object
		layout.operator(Reset_Rig_Colors.bl_idname, text="Reset Colors")
		layout.separator()
		for cp in rig.rig_colorproperties:
			layout.prop(cp, "color", text=cp.name)

classes = (
	POSE_OT_rigify_switch_parent,

	Rig_ColorProperties,
	Rig_BoolProperties,
	Rig_Properties,
	RigUI_Outfits,
	# RigUI_Layers,
	Snap_IK2FK,
	Snap_FK2IK,
	IKFK_Toggle,
	# Reset_Rig_Colors,
	RigUI_Settings,
	RigUI_Settings_FKIK,
	RigUI_Settings_IK,
	# RigUI_Settings_FK,
	# RigUI_Settings_Face,
	# RigUI_Settings_Misc,
	# RigUI_Viewport_Display,
)

from bpy.utils import register_class
for c in classes:
	register_class(c)

bpy.types.Object.rig_properties = bpy.props.PointerProperty(type=Rig_Properties)
bpy.types.Object.rig_boolproperties = bpy.props.CollectionProperty(type=Rig_BoolProperties)
bpy.types.Object.rig_colorproperties = bpy.props.CollectionProperty(type=Rig_ColorProperties)

# bpy.app.handlers.depsgraph_update_post.append(post_depsgraph_update)
bpy.app.handlers.depsgraph_update_pre.append(pre_depsgraph_update)

# Certain render settings must be enabled for Rain!
bpy.context.scene.eevee.use_ssr = True
bpy.context.scene.eevee.use_ssr_refraction = True