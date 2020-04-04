import bpy
from bpy.props import *
from mathutils import Vector, Matrix
from math import *

import json

import math
import traceback
from mathutils import Euler, Quaternion
from rna_prop_ui import rna_idprop_quote_path

# During rig generation, SCRIPT_ID is replaced with the name of the blend file in which the rig was generated.
# The same value is saved in the generated rig's 'cloudrig' property, which allows matching UI scripts to the rigs that were generated with them
# This is useful when linking multiple characters that were generated at different times with different versions, into a single scene.
# So that each rig would use the script that belongs to it.
script_id = "SCRIPT_ID"

class Snap_Simple(bpy.types.Operator):
	bl_idname = "pose.snap_simple"
	bl_label = "Snap Simple"
	bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
	bl_description = "Toggle a custom property while ensuring that some bones stay in place"

	bones:		 StringProperty(name="Control Bone")
	prop_bone:	StringProperty(name="Property Bone")
	prop_id:	  StringProperty(name="Property")

	select_bones: BoolProperty(name="Select Affected Bones", default=True)

	locks:		bpy.props.BoolVectorProperty(name="Locked", size=3, default=[False,False,False])

	@classmethod
	def poll(cls, context):
		return context.pose_object

	def execute(self, context):
		rig = context.pose_object or context.active_object
		# TODO: Instead of relying on scene settings(auto-keying, keyingset, etc) maybe it would be better to have a custom boolean to decide whether to insert keyframes or not. Ask animators.
		self.keyflags = self.get_autokey_flags(context, ignore_keyset=True)
		self.keyflags_switch = self.add_flags_if_set(self.keyflags, {'INSERTKEY_AVAILABLE'})

		bone_names = json.loads(self.bones)
		bones = get_bones(rig, self.bones)

		try:
			matrices = []
			for bone_name in bone_names:
				matrices.append( self.save_frame_state(context, rig, bone_name) )
			
			self.apply_frame_state(context, rig, matrices, bone_names)

		except Exception as e:
			traceback.print_exc()
			self.report({'ERROR'}, 'Exception: ' + str(e))

		self.set_selection(context, bones)

		return {'FINISHED'}

	def set_selection(self, context, bones):
		if self.select_bones:
			for b in context.selected_pose_bones:
				b.bone.select = False
			for b in bones:
				b.bone.select=True

	def save_frame_state(self, context, rig, bone):
		return self.get_transform_matrix(rig, bone, with_constraints=False)

	def apply_frame_state(self, context, rig, old_matrices, bone_names):
		# Change the parent
		# TODO: Instead of relying on scene settings(auto-keying, keyingset, etc) maybe it would be better to have a custom boolean to decide whether to insert keyframes or not. Ask animators.
		value = self.get_custom_property_value(rig, self.prop_bone, self.prop_id)
		
		self.set_custom_property_value(
			rig, self.prop_bone, self.prop_id, 1-value,
			keyflags=self.keyflags_switch
		)

		context.view_layer.update()

		# Set the transforms to restore position
		for i, bone_name in enumerate(bone_names):
			old_matrix = old_matrices[i]
			self.set_transform_from_matrix(
				rig, bone_name, old_matrix, keyflags=self.keyflags,
				no_loc=self.locks[0], no_rot=self.locks[1], no_scale=self.locks[2]
			)

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

	def keyframe_transform_properties(self, rig, bone_name, keyflags, *, ignore_locks=False, no_loc=False, no_rot=False, no_scale=False):
		"Keyframe transformation properties, taking flags and mode into account, and avoiding keying locked channels."
		bone = rig.pose.bones[bone_name]

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

	def get_custom_property_value(self, rig, bone_name, prop_id):
		prop_bone = rig.pose.bones.get(self.prop_bone)
		assert prop_bone, "Bone snapping failed: Properties bone %s not found.)" %self.bone_name
		assert self.prop_id in prop_bone, "Bone snapping failed: Bone %s has no property %s" %(self.bone_name, self.bone_id)
		return prop_bone[self.prop_id]

	def set_custom_property_value(self, rig, bone_name, prop, value, *, keyflags=None):
		"Assign the value of a custom property, and optionally keyframe it."
		from rna_prop_ui import rna_idprop_ui_prop_update
		bone = rig.pose.bones[bone_name]
		bone[prop] = value
		rna_idprop_ui_prop_update(bone, prop)
		if keyflags is not None:
			bone.keyframe_insert(rna_idprop_quote_path(prop), group=bone.name, options=keyflags)

	def get_transform_matrix(self, rig, bone_name, *, space='POSE', with_constraints=True):
		"Retrieve the matrix of the bone before or after constraints in the given space."
		bone = rig.pose.bones[bone_name]
		if with_constraints:
			return rig.convert_space(pose_bone=bone, matrix=bone.matrix, from_space='POSE', to_space=space)
		else:
			return rig.convert_space(pose_bone=bone, matrix=bone.matrix_basis, from_space='LOCAL', to_space=space)

	def set_transform_from_matrix(self, rig, bone_name, matrix, *, space='POSE', ignore_locks=False, no_loc=False, no_rot=False, no_scale=False, keyflags=None):
		"Apply the matrix to the transformation of the bone, taking locked channels, mode and certain constraints into account, and optionally keyframe it."
		bone = rig.pose.bones[bone_name]

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
			matrix = rig.convert_space(pose_bone=bone, matrix=matrix, from_space=space, to_space='LOCAL')

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
				rig, bone_name, keyflags, ignore_locks=ignore_locks,
				no_loc=no_loc, no_rot=no_rot, no_scale=no_scale
			)

class POSE_OT_rigify_switch_parent(Snap_Simple):
	bl_idname = "pose.rigify_switch_parent"
	bl_label = "Switch Parent (Keep Transform)"
	bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}
	bl_description = "Switch parent, preserving the bone position and orientation"

	bones:		 StringProperty(name="Control Bone")
	prop_bone:	StringProperty(name="Property Bone")
	prop_id:	  StringProperty(name="Property")
	
	select_bones: BoolProperty(name="Select Affected Bones", default=True)

	parent_names: StringProperty(name="Parent Names")
	locks:		bpy.props.BoolVectorProperty(name="Locked", size=3, default=[False,False,False])

	parent_items = [('0','None','None')]

	selected: bpy.props.EnumProperty(
		name='Selected Parent',
		items=lambda s,c: POSE_OT_rigify_switch_parent.parent_items
	)

	def apply_frame_state(self, context, rig, old_matrices, bone_names):
		# Change the parent
		self.set_custom_property_value(
			rig, self.prop_bone, self.prop_id, int(self.selected),
			keyflags=self.keyflags_switch
		)

		context.view_layer.update()

		# Set the transforms to restore position
		for i, bone_name in enumerate(bone_names):
			old_matrix = old_matrices[i]
			self.set_transform_from_matrix(
				rig, bone_name, old_matrix, keyflags=self.keyflags,
				no_loc=self.locks[0], no_rot=self.locks[1], no_scale=self.locks[2]
			)

	def draw(self, _context):
		col = self.layout.column()
		col.prop(self, 'selected', expand=True)

	def invoke(self, context, event):
		rig = context.pose_object or context.active_object
		pose = rig.pose

		if (not pose or not self.parent_names
			#or self.bone not in pose.bones
			or self.prop_bone not in pose.bones
			or self.prop_id not in pose.bones[self.prop_bone]):
			self.report({'ERROR'}, "Invalid parameters")
			return {'CANCELLED'}

		parents = json.loads(self.parent_names)
		pitems = [(str(i), name, name) for i, name in enumerate(parents)]

		POSE_OT_rigify_switch_parent.parent_items = pitems

		self.selected = str(pose.bones[self.prop_bone][self.prop_id])

		if hasattr(self, 'draw'):
			return context.window_manager.invoke_props_popup(self, event)
		else:
			return self.execute(context)

def get_rigs():
	""" Find all cloudrig armatures in the file."""
	return [o for o in bpy.data.objects if o.type=='ARMATURE' and 'cloudrig' in o.data]

def get_rig():
	"""If the active object is a cloudrig, return it."""
	o = bpy.context.pose_object or bpy.context.object
	if o and o.type == 'ARMATURE' and 'cloudrig' in o.data and o.data['cloudrig']==script_id:
		return o

def get_char_bone(rig):
	for b in rig.pose.bones:
		if b.name.startswith("Properties_Character"):
			return b

def get_bones(rig, names):
	""" Return a list of pose bones from a string of bone names separated by ", ". """
	return list(filter(None, map(rig.pose.bones.get, json.loads(names))))

class Snap_Mapped(Snap_Simple):
	"""Toggle a custom property and snap some bones to some other bones."""
	bl_idname = "pose.snap_mapped"
	bl_label = "Snap Bones"
	bl_options = {'REGISTER', 'UNDO'}

	prop_bone:	StringProperty(name="Property Bone")
	prop_id:	  StringProperty(name="Property")

	select_bones: BoolProperty(name="Select Affected Bones", default=False)
	locks:		bpy.props.BoolVectorProperty(name="Locked", size=3, default=[False,False,False])

	# Lists of bone names separated (converted to string so they could be passed to an operator)
	map_on: StringProperty()		# Bone name dictionary to use when the property is toggled ON.
	map_off: StringProperty()		# Bone name dictionary to use when the property is toggled OFF.
	
	hide_on: StringProperty()		# List of bone names to hide when property is toggled ON.
	hide_off: StringProperty()		# List of bone names to hide when property is toggled OFF.

	def execute(self, context):
		rig = context.pose_object or context.active_object
		self.keyflags = self.get_autokey_flags(context, ignore_keyset=True)
		self.keyflags_switch = self.add_flags_if_set(self.keyflags, {'INSERTKEY_AVAILABLE'})

		value = self.get_custom_property_value(rig, self.prop_bone, self.prop_id)
		my_map = self.map_off if value==1 else self.map_on
		names_hide = self.hide_off if value==1 else self.hide_on
		names_unhide = self.hide_on if value==1 else self.hide_off

		self.set_custom_property_value(
			rig, self.prop_bone, self.prop_id, 1-value, 
			keyflags=self.keyflags
		)
		my_map = json.loads(my_map)

		names_affected = [t[0] for t in my_map]
		names_affector = [t[1] for t in my_map]

		matrices = []
		for affector_name in names_affector:
			affector_bone = rig.pose.bones.get(affector_name)
			assert affector_bone, "Error: Snapping failed, bone not found: %s" %affector_name
			matrices.append(affector_bone.matrix.copy())

		for i, affected_name in enumerate(names_affected):
			affected_bone = rig.pose.bones.get(affected_name)
			assert affected_bone, "Error: Snapping failed, bones not found: %s" %affected_name
			affected_bone.matrix = matrices[i]
			context.evaluated_depsgraph_get().update()

			# Keyframe properties
			if self.keyflags is not None:
				self.keyframe_transform_properties(
					rig, affected_bone.name, self.keyflags,
					no_loc=self.locks[0], no_rot=self.locks[1], no_scale=self.locks[2]
				)

		self.hide_unhide_bones(get_bones(rig, names_hide), get_bones(rig, names_unhide))
		self.set_selection(context, get_bones(rig, json.dumps(names_affected)))
		
		return {'FINISHED'}

	def hide_unhide_bones(self, hide_bones, unhide_bones):
		# Hide bones
		for b in hide_bones:
			b.bone.hide = True
		
		# Unhide bones
		for b in unhide_bones:
			b.bone.hide = False

		return {'FINISHED'}

class IKFK_Toggle(bpy.types.Operator):
	"Toggle between IK and FK, and snap the controls accordingly. This will NOT place any keyframes, but it will select the affected bones"
	bl_idname = "armature.ikfk_toggle"
	bl_label = "Toggle IK/FK"
	bl_options = {'REGISTER', 'UNDO'}
	
	prop_bone: StringProperty()
	prop_id: StringProperty()

	fk_chain: StringProperty()
	ik_chain: StringProperty()
	str_chain: StringProperty()

	double_first_control: BoolProperty(default=False)
	double_ik_control: BoolProperty(default=False)

	ik_pole: StringProperty()
	ik_control: StringProperty()

	@classmethod
	def poll(cls, context):
		return context.pose_object

	def execute(self, context):
		armature = context.pose_object
		
		fk_chain = get_bones(armature, self.fk_chain)
		ik_chain = get_bones(armature, self.ik_chain)
		str_chain = get_bones(armature, self.str_chain)

		ik_pole = armature.pose.bones.get(self.ik_pole)
		ik_control = armature.pose.bones.get(self.ik_control)
		assert ik_pole, "ERROR: Could not find IK Pole: " + self.ik_pole
		assert ik_control, "ERROR: Could not find IK Control: " + self.ik_control

		map_on = []
		map_off = []
		hide_on = [b.name for b in fk_chain]
		hide_off = [self.ik_control, self.ik_pole]
		if self.double_ik_control:
			hide_off.append(ik_control.parent.name)
			map_on.append( (ik_control.parent.name, fk_chain[-1].name) )
		map_on.append( (self.ik_control, fk_chain[-1].name) )
		map_on.append( (ik_chain[0].name, fk_chain[0].name) )
		if self.double_first_control:
			hide_on.append( (fk_chain[0].parent.name) )
			map_off.append( (fk_chain[0].parent.name, ik_chain[0].name) )
		map_off.append( (fk_chain[0].name, ik_chain[0].name) )
		map_off.append( (fk_chain[1].name, str_chain[1].name) )
		map_off.append( (fk_chain[2].name, ik_control.name) )

		prop_bone = armature.pose.bones.get(self.prop_bone)
		value = prop_bone[self.prop_id]
		if value==0:
			# Snap the last IK control to the last FK control.
			first_ik_bone = ik_chain[0]
			last_ik_bone = ik_chain[-1]
			first_fk_bone = fk_chain[-2].parent
			self.match_pole_target(first_ik_bone, last_ik_bone, ik_pole, first_fk_bone, 0.5)
			context.evaluated_depsgraph_get().update()

		bpy.ops.pose.snap_mapped(
			prop_bone = self.prop_bone,
			prop_id = self.prop_id,

			map_on		= json.dumps(map_on), 
			map_off		= json.dumps(map_off), 
			hide_on		= json.dumps(hide_on), 
			hide_off	= json.dumps(hide_off),

			select_bones = True,
		)

		if value==0:
			# Select pole
			ik_pole.bone.select=True

		return {'FINISHED'}

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
			par_rest = Matrix()
			if pose_bone.bone.parent:
				par_rest = pose_bone.bone.parent.matrix_local.copy()

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

			org_mode = bpy.context.object.mode
			bpy.ops.object.mode_set(mode='OBJECT')
			bpy.ops.object.mode_set(mode=org_mode)

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

class Reset_Rig_Colors(bpy.types.Operator):
	"""Reset rig color properties to their stored default."""
	bl_idname = "object.reset_rig_colors"
	bl_label = "Reset Rig Colors"
	bl_options = {'REGISTER', 'UNDO'}

	@classmethod
	def poll(cls, context):
		rig = context.pose_object or context.object
		return 'cloudrig' in rig.data

	def execute(self, context):
		rig = context.pose_object or context.object
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

class Rig_Properties(bpy.types.PropertyGroup):
	""" PropertyGroup for storing fancy custom properties in.
		Character and Outfit specific properties will still be stored in their relevant Properties bones (eg. Properties_Outfit_Rain).
	"""

	def get_rig(self):
		""" Find the armature object that is using this instance (self). """

		for rig in get_rigs():
			if(rig.rig_properties == self):
				return rig
	
	def outfits(self, context):
		""" Callback function for finding the list of available outfits for the outfit enum.
			Based on naming convention. Bones storing an outfit's properties must be named "Properties_Outfit_OutfitName".
		"""
		rig = self.get_rig()
		if not rig: return [(('identifier', 'name', 'description'))]

		outfits = []
		for b in rig.pose.bones:
			if b.name.startswith("Properties_Outfit_"):
				outfits.append(b.name.replace("Properties_Outfit_", ""))
		
		# Convert the list into what an EnumProperty expects.
		items = []
		for i, outfit in enumerate(outfits):
			items.append((outfit, outfit, outfit, i))	# Identifier, name, description, can all be the outfit name.
		
		# If no outfits were found, don't return an empty list so the console doesn't spam "'0' matches no enum" warnings.
		if(items==[]):
			return [(('identifier', 'name', 'description'))]
		
		return items
	
	def change_outfit(self, context):
		""" Update callback of outfit enum. """
		
		rig = self.get_rig()
		if not rig: return
		
		if( (self.outfit == '') ):
			self.outfit = self.outfits(context)[0][0]
		
		outfit_bone = rig.pose.bones.get("Properties_Outfit_"+self.outfit)

		if outfit_bone:
			# Reset all settings to default.
			for key in outfit_bone.keys():
				value = outfit_bone[key]
				if type(value) in [float, int]:
					pass # TODO: Can't seem to reset custom properties to their default, or even so much as read their default!?!?
			
			# For outfit properties starting with "_", update the corresponding character property.
			char_bone = get_char_bone(rig)
			for key in outfit_bone.keys():
				if key.startswith("_") and key[1:] in char_bone:
					char_bone[key[1:]] = outfit_bone[key]
		
		context.evaluated_depsgraph_get().update()

	# TODO: This could be implemented like an operator instead, just like parent switching. But maybe this way is better?
	outfit: EnumProperty(
		name	= "Outfit",
		items	= outfits,
		update	= change_outfit,
		options	= {"LIBRARY_EDITABLE"} # Make it not animatable.
	)

class RigUI(bpy.types.Panel):
	bl_space_type = 'VIEW_3D'
	bl_region_type = 'UI'
	bl_category = 'CloudRig'
	
	@classmethod
	def poll(cls, context):
		return get_rig() is not None

	def draw(self, context):
		layout = self.layout

class RigUI_Outfits(RigUI):
	bl_idname = "OBJECT_PT_rig_ui_properties_" + script_id
	bl_label = "Outfits"

	@classmethod
	def poll(cls, context):
		if(not super().poll(context)):
			return False

		# Only display this panel if there is either an outfit with options, multiple outfits, or character options.
		rig = get_rig()
		if not rig: return
		rig_props = rig.rig_properties
		multiple_outfits = len(rig_props.outfits(context)) > 1
		outfit_properties_bone = rig.pose.bones.get("Properties_Outfit_"+rig_props.outfit)
		char_bone = get_char_bone(rig)

		return multiple_outfits or outfit_properties_bone or char_bone

	def draw(self, context):
		layout = self.layout
		rig = context.pose_object or context.object

		rig_props = rig.rig_properties
		
		def add_props(prop_owner):
			def get_text(prop_id, value):
				""" If there is a property on prop_owner named $prop_id, expect it to be a list of strings and return the valueth element."""
				text = prop_id.replace("_", " ")
				if "$"+prop_id in prop_owner and type(value)==int:
					names = prop_owner["$"+prop_id]
					if value > len(names)-1:
						print("WARNING: Name list for this property is not long enough for current value: %s" %prop_id)
						return text
					return text + ": " + names[value]
				else:
					return text

			for prop_id in prop_owner.keys():
				if( prop_id.startswith("_") ): continue
				# Int Props
				if(type(prop_owner[prop_id]) in [int, float] ):
					layout.prop(prop_owner, '["'+prop_id+'"]', slider=True, 
						text = get_text(prop_id, prop_owner[prop_id])
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
	bl_idname = "OBJECT_PT_rig_ui_layers_" + script_id
	bl_label = "Layers"
	
	def draw(self, context):
		layout = self.layout
		rig = get_rig()
		if not rig: return
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
	bl_idname = "OBJECT_PT_rig_ui_settings_" + script_id
	bl_label = "Settings"
	
	def draw(self, context):
		layout = self.layout
		rig = get_rig()
		if not rig: return

		if 'render_modifiers' in rig.data:
			layout.row().prop(rig.data, 'render_modifiers', text='Enable Modifiers', toggle=True)

def draw_rig_settings(layout, rig, ui_area, label=""):
	""" Draw UI settings in the layout, if info for those settings can be found in the rig's data. 
	Parameters read from the rig data:
	
	prop_bone: Name of the pose bone that holds the custom property.
	prop_id: Name of the custom property on aforementioned bone. This is the property that gets drawn in the UI as a slider.
	
	texts: Optional list of strings to display alongside the property name on the slider, chosen based on the current value of the property.
	operator: Optional parameter to specify an operator to draw next to the slider.
	icon: Optional prameter to override the icon of the operator. Defaults to 'FILE_REFRESH'.
	
	Arbitrary arguments will be passed on to the operator.
	"""
	
	if ui_area not in rig.data: return
	
	if label!="":
		layout.label(text=label)

	settings = rig.data[ui_area].to_dict()
	for row_name in settings.keys():
		col_name = settings[row_name]
		row = layout.row()
		for entry_name in col_name.keys():
			info = col_name[entry_name]
			assert 'prop_bone' in info and 'prop_id' in info, "ERROR: Limb definition lacks properties bone or ID: %s, %s" %(row_name, info)
			prop_bone = rig.pose.bones.get(info['prop_bone'])
			prop_id = info['prop_id']
			assert prop_bone and prop_id in prop_bone, "ERROR: Properties bone or property does not exist: %s" %info

			col = row.column()
			sub_row = col.row(align=True)
			
			text = entry_name
			if 'texts' in info:
				prop_value = prop_bone[prop_id]
				cur_text = info['texts'][int(prop_value)]
				text = entry_name + ": " + cur_text

			sub_row.prop(prop_bone, '["' + prop_id + '"]', slider=True, text=text)
			
			# Draw an operator if provided.
			if 'operator' in info:
				icon = 'FILE_REFRESH'
				if 'icon' in info:
					icon = info['icon']
				
				switch = sub_row.operator(info['operator'], text="", icon=icon)
				# Fill the operator's parameters where provided.
				for param in info.keys():
					if hasattr(switch, param):
						value = info[param]
						if type(value) in [list, dict]:
							value = json.dumps(value)
						setattr(switch, param, value)

class RigUI_Settings_FKIK(RigUI):
	bl_idname = "OBJECT_PT_rig_ui_ikfk_" + script_id
	bl_label = "FK/IK Switch"
	bl_parent_id = "OBJECT_PT_rig_ui_settings_" + script_id

	@classmethod
	def poll(cls, context):
		rig = get_rig()
		return rig and "ik_switches" in rig.data

	def draw(self, context):
		layout = self.layout
		rig = get_rig()
		if not rig: return
		data = rig.data

		draw_rig_settings(layout, rig, "ik_switches")

class RigUI_Settings_IK(RigUI):
	bl_idname = "OBJECT_PT_rig_ui_ik_" + script_id
	bl_label = "IK Settings"
	bl_parent_id = "OBJECT_PT_rig_ui_settings_" + script_id

	@classmethod
	def poll(cls, context):
		rig = get_rig()
		if not rig: return False
		ik_settings = ['ik_stretches', 'ik_hinges', 'parents', 'ik_pole_follows']
		for ik_setting in ik_settings:
			if ik_setting in rig.data:
				return True
		return False

	def draw(self, context):
		layout = self.layout
		rig = get_rig()
		if not rig: return
		ikfk_props = rig.pose.bones.get('Properties_IKFK')
		data = rig.data

		draw_rig_settings(layout, rig, "ik_stretches", label="IK Stretch")
		draw_rig_settings(layout, rig, "parents", label="IK Parents")
		draw_rig_settings(layout, rig, "ik_hinges", label="IK Hinge")
		draw_rig_settings(layout, rig, "ik_pole_follows", label="IK Pole Follow")

class RigUI_Settings_FK(RigUI):
	bl_idname = "OBJECT_PT_rig_ui_fk_" + script_id
	bl_label = "FK Settings"
	bl_parent_id = "OBJECT_PT_rig_ui_settings_" + script_id

	@classmethod
	def poll(cls, context):
		rig = get_rig()
		if not rig: return False
		fk_settings = ['fk_hinges']
		for fk_setting in fk_settings:
			if fk_setting in rig.data:
				return True
		return False

	def draw(self, context):
		layout = self.layout
		rig = get_rig()
		if not rig: return
		data = rig.data

		draw_rig_settings(layout, rig, "fk_hinges", label='FK Hinge')

class RigUI_Settings_Face(RigUI):
	bl_idname = "OBJECT_PT_rig_ui_face_" + script_id
	bl_label = "Face Settings"
	bl_parent_id = "OBJECT_PT_rig_ui_settings_" + script_id

	@classmethod
	def poll(cls, context):
		rig = get_rig()
		return rig and "face_settings" in rig.data
	
	def draw(self, context):
		layout = self.layout
		rig = get_rig()
		if not rig: return
		face_props = rig.pose.bones.get('Properties_Face')

		if 'face_settings' in rig.data:
			# Eyelid settings
			layout.prop(face_props, '["sticky_eyelids"]',	text='Sticky Eyelids',  slider=True)
			layout.prop(face_props, '["sticky_eyesockets"]', text='Sticky Eyerings', slider=True)

			layout.separator()
			# Mouth settings
			layout.prop(face_props, '["teeth_follow_mouth"]', text='Teeth Follow Mouth', slider=True)

			layout.label(text="Eye Target Parent")
			row = layout.row()
			eye_parents = ['Root', 'Torso', 'Torso_Loc', 'Head']
			row.prop(face_props, '["eye_target_parents"]',  text=eye_parents[face_props["eye_target_parents"]], slider=True)

class RigUI_Settings_Misc(RigUI):
	bl_idname = "OBJECT_PT_rig_ui_misc_" + script_id
	bl_label = "Misc"
	bl_parent_id = "OBJECT_PT_rig_ui_settings_" + script_id

	@classmethod
	def poll(cls, context):
		rig = get_rig()
		return rig and "misc_settings" in rig.data

	def draw(self, context):
		layout = self.layout
		rig = get_rig()
		if not rig: return
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
	bl_idname = "OBJECT_PT_rig_ui_viewport_display_" + script_id
	bl_label = "Viewport Display"

	@classmethod
	def poll(cls, context):
		rig = get_rig()
		return rig and hasattr(rig, "rig_colorproperties") and len(rig.rig_colorproperties)>0

	def draw(self, context):
		layout = self.layout
		rig = get_rig()
		if not rig: return
		layout.operator(Reset_Rig_Colors.bl_idname, text="Reset Colors")
		layout.separator()
		for cp in rig.rig_colorproperties:
			layout.prop(cp, "color", text=cp.name)

classes = (
	POSE_OT_rigify_switch_parent,
	Snap_Mapped,
	Snap_Simple,
	Rig_ColorProperties,
	Rig_Properties,
	RigUI_Outfits,
	RigUI_Layers,
	IKFK_Toggle,
	Reset_Rig_Colors,
	RigUI_Settings,
	RigUI_Settings_FKIK,
	RigUI_Settings_IK,
	RigUI_Settings_FK,
	RigUI_Settings_Face,
	RigUI_Settings_Misc,
	RigUI_Viewport_Display,
)

from bpy.utils import register_class
for c in classes:
	register_class(c)

bpy.types.Object.rig_properties = bpy.props.PointerProperty(type=Rig_Properties)
bpy.types.Object.rig_colorproperties = bpy.props.CollectionProperty(type=Rig_ColorProperties)