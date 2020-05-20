# This file is executed and loaded into a self-registering text datablock when a CloudRig is generated.
# It's currently responsible for drawing rig UI

# The only change made by the generator is replacing SCRIPT_ID with the name of the blend file.
# This is used to allow multiple characters generated with different versions of CloudRig
# to co-exist in the same scene.
# So each rig uses the script that belongs to it, and not another, potentially newer or older version.

import bpy, traceback, json
from bpy.props import StringProperty, BoolProperty, BoolVectorProperty, EnumProperty, FloatVectorProperty, PointerProperty, CollectionProperty
from mathutils import Vector, Matrix
from math import radians, acos
from rna_prop_ui import rna_idprop_quote_path

script_id = "SCRIPT_ID"

def get_rigs():
	""" Find all cloudrig armatures in the file. """
	return [o for o in bpy.data.objects if o.type=='ARMATURE' and 'cloudrig' in o.data]

def active_cloudrig():
	""" If the active object is a cloudrig, return it. """
	o = bpy.context.pose_object or bpy.context.object
	if o and o.type == 'ARMATURE' and 'cloudrig' in o.data and o.data['cloudrig']==script_id:
		return o

def get_char_bone(rig):
	for b in rig.pose.bones:
		if b.name.startswith("Properties_Character"):
			return b

def get_bones(rig, names):
	""" Return a list of pose bones from a string of bone names in json format. """
	return list(filter(None, map(rig.pose.bones.get, json.loads(names))))

def draw_rig_settings(layout, rig, dict_name, label=""):
	""" 
	dict_name is the name of the custom property dictionary that we expect to find in the rig.
	Everything stored in a single dictionary is drawn in one call of this function.
	These dictionaries are created during rig generation.

	For an example dictionary, select an existing CloudRig, and put this in the PyConsole:
	>>> import json
	>>> print(json.dumps(C.object.data['ik_stretches'].to_dict(), indent=4))

	Parameters expected to be found in the dictionary:
		prop_bone: Name of the pose bone that holds the custom property.
		prop_id: Name of the custom property on aforementioned bone. This is the property that gets drawn in the UI as a slider.

	Further optional parameters:
		texts: List of strings to display alongside an integer property slider.
		operator: Specify an operator to draw next to the slider.
		icon: Override the icon of the operator. If not specified, default to 'FILE_REFRESH'.
		Any other arbitrary parameters will be passed on to the operator as kwargs.
	"""

	if dict_name not in rig.data: return

	if label != "":
		layout.label(text=label)

	main_dict = rig.data[dict_name].to_dict()
	# Each top-level dictionary within the main dictionary defines a row.
	for row_name in main_dict.keys():
		row = layout.row()
		# Each second-level dictionary within that defines a slider (and operator, if given).
		# If there is more than one, they will be drawn next to each other, since they're in the same row.
		row_entries = main_dict[row_name]
		for entry_name in row_entries.keys():
			info = row_entries[entry_name]		# This is the lowest level dictionary that contains the parameters for the slider and its operator, if given.
			assert 'prop_bone' in info and 'prop_id' in info, f"ERROR: Limb definition lacks properties bone or ID: {row_name}, {info}"
			prop_bone = rig.pose.bones.get(info['prop_bone'])
			prop_id = info['prop_id']
			assert prop_bone and prop_id in prop_bone, f"ERROR: Properties bone or property does not exist: {info}"

			col = row.column()
			sub_row = col.row(align=True)

			slider_text = entry_name
			if 'texts' in info:
				prop_value = prop_bone[prop_id]
				cur_text = info['texts'][int(prop_value)]
				slider_text = entry_name + ": " + cur_text

			sub_row.prop(prop_bone, '["' + prop_id + '"]', slider=True, text=slider_text)

			# Draw an operator if provided.
			if 'operator' in info:
				icon = 'FILE_REFRESH'
				if 'icon' in info:
					icon = info['icon']

				operator = sub_row.operator(info['operator'], text="", icon=icon)
				# Pass on any paramteres to the operator that it will accept.
				for param in info.keys():
					if hasattr(operator, param):
						value = info[param]
						# Lists and Dicts cannot be passed to blender operators, so we must convert them to a string.
						if type(value) in [list, dict]:
							value = json.dumps(value)
						setattr(operator, param, value)

class CLOUDRIG_OT_snap_simple(bpy.types.Operator):
	bl_description = "Toggle a custom property while ensuring that some bones stay in place"
	bl_idname = "pose.snap_simple"
	bl_label = "Snap Simple"
	bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

	bones:		  StringProperty(name="Control Bone")
	prop_bone:	  StringProperty(name="Property Bone")
	prop_id:	  StringProperty(name="Property")
	select_bones: BoolProperty(name="Select Affected Bones", default=True)
	locks:		  BoolVectorProperty(name="Locked", size=3, default=[False,False,False])

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
		assert prop_bone, f"Bone snapping failed: Properties bone {self.bone_name} not found.)"
		assert self.prop_id in prop_bone, f"Bone snapping failed: Bone {self.bone_name} has no property {self.bone_id}"
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

class CLOUDRIG_OT_snap_mapped(CLOUDRIG_OT_snap_simple):
	bl_description = "Toggle a custom property and snap some bones to some other bones"
	bl_idname = "pose.snap_mapped"
	bl_label = "Snap Bones"
	bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

	prop_bone:	  StringProperty(name="Property Bone")
	prop_id:	  StringProperty(name="Property")

	select_bones: BoolProperty(name="Select Affected Bones", default=False)
	locks:		  BoolVectorProperty(name="Locked", size=3, default=[False,False,False])

	# Lists of bone names separated (converted to string so they could be passed to an operator)
	map_on:		  StringProperty()		# Bone name dictionary to use when the property is toggled ON.
	map_off:	  StringProperty()		# Bone name dictionary to use when the property is toggled OFF.

	hide_on:	  StringProperty()		# List of bone names to hide when property is toggled ON.
	hide_off:	  StringProperty()		# List of bone names to hide when property is toggled OFF.

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
			assert affector_bone, f"Error: Snapping failed, bone not found: {affector_name}"
			matrices.append(affector_bone.matrix.copy())

		for i, affected_name in enumerate(names_affected):
			affected_bone = rig.pose.bones.get(affected_name)
			assert affected_bone, f"Error: Snapping failed, bones not found: {affected_name}"
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

class CLOUDRIG_OT_switch_parent(CLOUDRIG_OT_snap_simple):
	bl_description = "Switch parent, preserving the bone position and orientation"
	bl_idname = "pose.rigify_switch_parent"
	bl_label = "Switch Parent (Keep Transform)"
	bl_options = {'REGISTER', 'UNDO', 'INTERNAL'}

	bones:		  StringProperty(name="Control Bone")
	prop_bone:	  StringProperty(name="Property Bone")
	prop_id:	  StringProperty(name="Property")

	select_bones: BoolProperty(name="Select Affected Bones", default=True)

	parent_names: StringProperty(name="Parent Names")
	locks:		  BoolVectorProperty(name="Locked", size=3, default=[False,False,False])

	parent_items = [('0','None','None')]

	selected:	  EnumProperty(
		name='Selected Parent',
		items=lambda s,c: CLOUDRIG_OT_switch_parent.parent_items
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

		if (
			not pose or not self.parent_names
			#or self.bone not in pose.bones
			or self.prop_bone not in pose.bones
			or self.prop_id not in pose.bones[self.prop_bone]
			):
				self.report({'ERROR'}, "Invalid parameters")
				return {'CANCELLED'}

		parents = json.loads(self.parent_names)
		pitems = [(str(i), name, name) for i, name in enumerate(parents)]

		CLOUDRIG_OT_switch_parent.parent_items = pitems

		self.selected = str(pose.bones[self.prop_bone][self.prop_id])

		if hasattr(self, 'draw'):
			return context.window_manager.invoke_props_popup(self, event)
		else:
			return self.execute(context)

class CLOUDRIG_OT_ikfk_toggle(bpy.types.Operator):
	bl_description = "Toggle between IK and FK, and snap the controls accordingly. This will NOT place any keyframes, but it will select the affected bones"
	bl_idname = "armature.ikfk_toggle"
	bl_label = "Toggle IK/FK"
	bl_options = {'REGISTER', 'UNDO'}

	prop_bone:	StringProperty()
	prop_id:	StringProperty()

	fk_chain:	StringProperty()
	ik_chain:	StringProperty()
	str_chain:	StringProperty()

	ik_control: StringProperty()
	ik_pole:	StringProperty()

	double_first_control: BoolProperty(default=False)
	double_ik_control:	  BoolProperty(default=False)

	@classmethod
	def poll(cls, context):
		return context.pose_object

	def execute(self, context):
		armature = context.pose_object

		fk_chain = get_bones(armature, self.fk_chain)
		ik_chain = get_bones(armature, self.ik_chain)
		str_chain = get_bones(armature, self.str_chain)

		ik_pole = armature.pose.bones.get(self.ik_pole)	# Can be None.
		ik_control = armature.pose.bones.get(self.ik_control)
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
			if ik_pole:
				self.match_pole_target(first_ik_bone, last_ik_bone, ik_pole, first_fk_bone, 0.5)
			else:
				if first_ik_bone.rotation_mode == first_fk_bone.rotation_mode:
					first_ik_bone.location = first_fk_bone.location.copy()
					first_ik_bone.rotation_euler = first_fk_bone.rotation_euler.copy()
				else:
					first_ik_bone.matrix = first_fk_bone.matrix.copy()
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

		if value==0 and ik_pole:
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
		if angle > radians(90):
			angle = -angle + radians(180)
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
		tail_dist1 = (ik_first.tail - match_bone.tail).length

		pv2 = Matrix.Rotation(-angle, 4, ikv) @ pv
		set_pole(pv2)
		tail_dist2 = (ik_first.tail - match_bone.tail).length

		# Do the one with the smaller angle
		if tail_dist1 < tail_dist2:
			set_pole(pv1)

class CLOUDRIG_OT_reset_colors(bpy.types.Operator):
	bl_description = "Reset rig color properties to their stored default"
	bl_idname = "object.reset_rig_colors"
	bl_label = "Reset Rig Colors"
	bl_options = {'REGISTER', 'UNDO'}

	@classmethod
	def poll(cls, context):
		rig = context.pose_object or context.object
		return 'cloudrig' in rig.data

	def execute(self, context):
		rig = context.pose_object or context.object
		for cp in rig.cloud_colors:
			cp.current = cp.default
		return {'FINISHED'}

class CloudRig_ColorProperties(bpy.types.PropertyGroup):
	""" Store a color property that can be used to drive colors on the rig, and then be controlled even when the rig is linked. """
	# Currently, a generated rig won't create any customproperties for itself.
	# You would have to create these for yourself with a separate python script.
	# C.object.data.cloud_colors.new()

	# The reset colors operator will reset all color properties to this default. 
	# Nothing's stopping you from changing this default, but it's not exposed in the UI, so it shouldn't be easy to accidently mess up.
	default: FloatVectorProperty(
		name='Default',
		description='',
		subtype='COLOR',
		min=0,
		max=1,
		options={'LIBRARY_EDITABLE'}	# Make it not animatable.
	)
	current: FloatVectorProperty(
		name='Color',
		description='',
		subtype='COLOR',
		min=0,
		max=1,
		options={'LIBRARY_EDITABLE'}	# Make it not animatable.
	)

class CloudRig_Properties(bpy.types.PropertyGroup):
	""" PropertyGroup for storing fancy custom properties in. """

	def get_rig(self):
		""" Find the armature object that is using this instance (self). """

		for rig in get_rigs():
			if rig.cloud_rig == self:
				return rig

	def items_outfit(self, context):
		""" Items callback for outfits EnumProperty.
			Build and return a list of outfit names based on a bone naming convention.
			Bones storing an outfit's properties must be named "Properties_Outfit_OutfitName".
		"""
		rig = self.get_rig()
		if not rig: return [(('0', 'Default', 'Default'))]

		outfits = []
		for b in rig.pose.bones:
			if b.name.startswith("Properties_Outfit_"):
				outfits.append(b.name.replace("Properties_Outfit_", ""))

		# Convert the list into what an EnumProperty expects.
		items = []
		for i, outfit in enumerate(outfits):
			items.append((outfit, outfit, outfit, i))	# Identifier, name, description, can all be the outfit name.

		# If no outfits were found, don't return an empty list so the console doesn't spam "'0' matches no enum" warnings.
		if items==[]:
			return [(('0', 'Default', 'Default'))]

		return items

	def change_outfit(self, context):
		""" Update callback of outfits EnumProperty. """

		rig = self.get_rig()
		if not rig: return

		if self.outfit == '':
			self.outfit = self.items_outfit(context)[0][0]

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

	# TODO: This should be implemented as an operator instead, just like parent switching.
	outfit: EnumProperty(
		name	= "Outfit",
		items	= items_outfit,
		update	= change_outfit,
		options	= {"LIBRARY_EDITABLE"} # Make it not animatable.
	)

class CLOUDRIG_PT_main(bpy.types.Panel):
	bl_space_type = 'VIEW_3D'
	bl_region_type = 'UI'
	bl_category = 'CloudRig'

	@classmethod
	def poll(cls, context):
		return active_cloudrig() is not None

	def draw(self, context):
		layout = self.layout

class CLOUDRIG_PT_character(CLOUDRIG_PT_main):
	bl_idname = "CLOUDRIG_PT_character_" + script_id
	bl_label = "Character"

	@classmethod
	def poll(cls, context):
		if not super().poll(context):
			return False

		# Only display this panel if there is either an outfit with options, multiple outfits, or character options.
		rig = active_cloudrig()
		if not rig: return
		rig_props = rig.cloud_rig
		multiple_outfits = len(rig_props.items_outfit(context)) > 1
		outfit_properties_bone = rig.pose.bones.get("Properties_Outfit_"+rig_props.outfit)
		char_bone = get_char_bone(rig)

		return multiple_outfits or outfit_properties_bone or char_bone

	def draw(self, context):
		layout = self.layout
		rig = context.pose_object or context.object

		rig_props = rig.cloud_rig

		def add_props(prop_owner):
			def get_text(prop_id, value):
				""" If there is a property on prop_owner named $prop_id, expect it to be a list of strings and return the valueth element."""
				text = prop_id.replace("_", " ")
				if "$"+prop_id in prop_owner and type(value)==int:
					names = prop_owner["$"+prop_id]
					if value > len(names)-1:
						print(f"WARNING: Name list for this property is not long enough for current value: {prop_id}")
						return text
					return text + ": " + names[value]
				else:
					return text

			for prop_id in prop_owner.keys():
				if prop_id.startswith("_"): continue
				
				if type(prop_owner[prop_id]) in [int, float]:
					layout.prop(prop_owner, '["'+prop_id+'"]', slider=True, 
						text = get_text(prop_id, prop_owner[prop_id])
					)
				elif str(type(prop_owner[prop_id])) == "<class 'IDPropertyArray'>":
					# Vectors
					layout.prop(prop_owner, '["'+prop_id+'"]', text=prop_id.replace("_", " "))

		# Add character properties to the UI, if any.
		char_bone = get_char_bone(rig)
		if char_bone:
			add_props(char_bone)
			layout.separator()

		# Add outfit properties to the UI, if any.
		outfit_properties_bone = rig.pose.bones.get("Properties_Outfit_"+rig_props.outfit)
		if outfit_properties_bone:
			layout.prop(rig_props, 'outfit')
			add_props(outfit_properties_bone)

class CLOUDRIG_PT_layers(CLOUDRIG_PT_main):
	bl_idname = "CLOUDRIG_PT_layers_" + script_id
	bl_label = "Layers"

	def draw(self, context):
		""" Draw rig layer toggles based on data stored in rig.data.rigify_layers. """
		rig = active_cloudrig()
		if not rig: return
		data = rig.data
		# This should work even if the Rigify addon is not enabled.
		rigify_layers = data['rigify_layers']

		layout = self.layout
		for i, l in enumerate(rigify_layers):
			# When the Rigify addon is not enabled, finding the original index after sorting is impossible, so just store it.
			l['index'] = i

		sorted_layers = sorted(rigify_layers, key=lambda l: l['row'])
		sorted_layers = [l for l in sorted_layers if l.name!=" "]
		current_row_index = 0
		for rigify_layer in sorted_layers:
			if rigify_layer['name'] in ["", " "]: continue
			if rigify_layer['name'].startswith("$"): continue

			if rigify_layer['row'] > current_row_index:
				current_row_index = rigify_layer['row']
				row = layout.row()
			row.prop(data, 'layers', index=rigify_layer['index'], toggle=True, text=rigify_layer['name'])

class CLOUDRIG_PT_settings(CLOUDRIG_PT_main):
	bl_idname = "CLOUDRIG_PT_settings_" + script_id
	bl_label = "Settings"

class CLOUDRIG_PT_fkik(CLOUDRIG_PT_main):
	bl_idname = "CLOUDRIG_PT_fkik_" + script_id
	bl_label = "FK/IK Switch"
	bl_parent_id = "CLOUDRIG_PT_settings_" + script_id

	@classmethod
	def poll(cls, context):
		rig = active_cloudrig()
		return rig and "ik_switches" in rig.data

	def draw(self, context):
		layout = self.layout
		rig = active_cloudrig()
		if not rig: return

		draw_rig_settings(layout, rig, "ik_switches")

class CLOUDRIG_PT_ik(CLOUDRIG_PT_main):
	bl_idname = "CLOUDRIG_PT_ik_" + script_id
	bl_label = "IK Settings"
	bl_parent_id = "CLOUDRIG_PT_settings_" + script_id

	@classmethod
	def poll(cls, context):
		rig = active_cloudrig()
		if not rig: return False
		ik_settings = ['ik_stretches', 'ik_hinges', 'parents', 'ik_pole_follows']
		for ik_setting in ik_settings:
			if ik_setting in rig.data:
				return True
		return False

	def draw(self, context):
		layout = self.layout
		rig = active_cloudrig()
		if not rig: return

		draw_rig_settings(layout, rig, "ik_stretches", label="IK Stretch")
		draw_rig_settings(layout, rig, "parents", label="IK Parents")
		draw_rig_settings(layout, rig, "ik_hinges", label="IK Hinge")
		draw_rig_settings(layout, rig, "ik_pole_follows", label="IK Pole Follow")

class CLOUDRIG_PT_fk(CLOUDRIG_PT_main):
	bl_idname = "CLOUDRIG_PT_fk_" + script_id
	bl_label = "FK Settings"
	bl_parent_id = "CLOUDRIG_PT_settings_" + script_id

	@classmethod
	def poll(cls, context):
		rig = active_cloudrig()
		if not rig: return False
		fk_settings = ['fk_hinges']
		for fk_setting in fk_settings:
			if fk_setting in rig.data:
				return True
		return False

	def draw(self, context):
		layout = self.layout
		rig = active_cloudrig()
		if not rig: return

		draw_rig_settings(layout, rig, "fk_hinges", label='FK Hinge')

class CLOUDRIG_PT_face(CLOUDRIG_PT_main):
	bl_idname = "CLOUDRIG_PT_face_" + script_id
	bl_label = "Face Settings"
	bl_parent_id = "CLOUDRIG_PT_settings_" + script_id

	@classmethod
	def poll(cls, context):
		rig = active_cloudrig()
		return rig and "face_settings" in rig.data

	def draw(self, context):
		layout = self.layout
		rig = active_cloudrig()
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

class CLOUDRIG_PT_misc(CLOUDRIG_PT_main):
	bl_idname = "CLOUDRIG_PT_misc_" + script_id
	bl_label = "Misc"
	bl_parent_id = "CLOUDRIG_PT_settings_" + script_id

	@classmethod
	def poll(cls, context):
		rig = active_cloudrig()
		return rig and "misc_settings" in rig.data

	def draw(self, context):
		layout = self.layout
		rig = active_cloudrig()
		if not rig: return
		ikfk_props = rig.pose.bones.get('Properties_IKFK')

		if 'misc_settings' in rig:
			layout.label(text="Grab Parents")
			row = layout.row()
			grab_parents = ['Root', 'Hand']
			row.prop(ikfk_props, '["grab_parent_left"]',  text="Left Hand [" + grab_parents[ikfk_props["grab_parent_left"]] + "]", slider=True)
			row.prop(ikfk_props, '["grab_parent_right"]',  text="Right Hand [" + grab_parents[ikfk_props["grab_parent_right"]] + "]", slider=True)

class CLOUDRIG_PT_viewport(CLOUDRIG_PT_main):
	bl_idname = "CLOUDRIG_PT_viewport_" + script_id
	bl_label = "Viewport Display"

	@classmethod
	def poll(cls, context):
		rig = active_cloudrig()
		return rig and hasattr(rig, "cloud_colors") and len(rig.cloud_colors)>0

	def draw(self, context):
		layout = self.layout
		rig = active_cloudrig()
		if not rig: return
		layout.operator(CLOUDRIG_OT_reset_colors.bl_idname, text="Reset Colors")
		layout.separator()
		for cp in rig.cloud_colors:
			layout.prop(cp, "current", text=cp.name)

classes = (
	CLOUDRIG_OT_switch_parent,
	CLOUDRIG_OT_snap_mapped,	# NOTE: For some reason, if the operators inheriting from snap_simple aren't registered before it, blender complains.
	CLOUDRIG_OT_snap_simple,
	CLOUDRIG_OT_ikfk_toggle,
	CLOUDRIG_OT_reset_colors,

	CloudRig_ColorProperties,
	CloudRig_Properties,

	CLOUDRIG_PT_character,
	CLOUDRIG_PT_layers,
	CLOUDRIG_PT_settings,
	CLOUDRIG_PT_fkik,
	CLOUDRIG_PT_ik,
	CLOUDRIG_PT_fk,
	CLOUDRIG_PT_face,
	CLOUDRIG_PT_misc,
	CLOUDRIG_PT_viewport,
)

def register():
	from bpy.utils import register_class
	for c in classes:
		register_class(c)

	# We store everything in Object rather than Armature because Armature data cannot be accessed on proxy armatures.
	bpy.types.Object.cloud_rig = PointerProperty(type=CloudRig_Properties)
	# TODO: move this inside cloud_rig.colors?
	bpy.types.Object.cloud_colors = CollectionProperty(type=CloudRig_ColorProperties)

def unregister():
	from bpy.utils import unregister_class
	for c in classes:
		unregister_class(c)

	del bpy.types.Object.cloud_rig
	del bpy.types.Object.cloud_colors

register()