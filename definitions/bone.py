# Data Container and utilities for de-coupling bone creation and setup from BPY.
# Lets us easily create bones without having to worry about edit/pose mode.
import bpy
from .id import ID
from mathutils import Vector
import copy
from ..rigs import cloud_utils

# Attributes that reference an actual bone ID. These should get special treatment, because we don't want to store said bone ID. 
# Ideally we would store a BoneInfo, but a string is allowed too.
bone_attribs = ['parent', 'bbone_custom_handle_start', 'bbone_custom_handle_end']

def get_defaults(contype, armature):
	"""Return my preferred defaults for each constraint type."""
	ret = {
		"target" : armature,
	 }

	# Constraints that support local space should default to local space.
	local_space = ['COPY_LOCATION', 'COPY_SCALE', 'COPY_ROTATION', 'COPY_TRANSFORMS',
						'LIMIT_LOCATION', 'LIMIT_SCALE', 'LIMIT_ROTATION',
						'ACTION', 'TRANSFORM', ]
	if contype in local_space:
		ret["owner_space"] = 'LOCAL'
		if contype not in ['LIMIT_SCALE']:
			ret["target_space"] = 'LOCAL'

	if contype == 'STRETCH_TO':
		ret["use_bulge_min"] = True
		ret["use_bulge_max"] = True
	elif contype in ['COPY_LOCATION', 'COPY_SCALE']:
		ret["use_offset"] = True
	elif contype == 'COPY_ROTATION':
		ret["use_offset"] = True
		ret["mix_mode"] = 'BEFORE'
	elif contype in ['COPY_TRANSFORMS', 'ACTION']:
		ret["mix_mode"] = 'BEFORE'
	elif contype == 'LIMIT_SCALE':
		ret["min_x"] = 1
		ret["max_x"] = 1
		ret["min_y"] = 1
		ret["max_y"] = 1
		ret["min_z"] = 1
		ret["max_z"] = 1
		ret["use_transform_limit"] = True
	elif contype in ['LIMIT_LOCATION', 'LIMIT_ROTATION']:
		ret["use_transform_limit"] = True
	elif contype == 'IK':
		ret["chain_count"] = 2
		ret["pole_target"] = armature
	elif contype == 'ARMATURE':
		# Create two targets in armature constraints.
		ret["targets"] = [{"target" : armature}, {"target" : armature}]
	
	return ret

def setattr_safe(thing, key, value):
	try:
		setattr(thing, key, value)
	except:
		print(f"ERROR: Wrong type assignment: key:{key}, type:{type(key)}, expected:{type(getattr(thing, key))}")
		print(thing)

class BoneInfoContainer(ID):
	# TODO: implement __iter__ and such.
	def __init__(self, cloudrig):
		self.bones = []
		self.armature = cloudrig.obj
		self.defaults = cloudrig.defaults	# For overriding arbitrary properties' default values when creating bones in this container.
		self.scale = cloudrig.scale

	def find(self, name):
		"""Find a BoneInfo instance by name, return it if found."""
		for bd in self.bones:
			if(bd.name == name):
				return bd
		return None

	def bone(self, name="Bone", source=None, overwrite=True, bone_group=None, **kwargs):
		"""Define a bone and add it to the list of bones. If it already exists, return or re-define it depending on overwrite param."""

		bi = self.find(name)
		if bi and not overwrite: 
			return bi
		elif bi:
			self.bones.remove(bi)

		bi = BoneInfo(self, name, source, bone_group, **kwargs)
		self.bones.append(bi)
		return bi
	
	def clear(self):
		self.bones = []

class BoneInfo(ID):
	"""Container of all info relating to a Bone."""
	def __init__(self, container, name="Bone", source=None, bone_group=None, **kwargs):
		""" 
		container: Need a reference to what BoneInfoContainer this BoneInfo belongs to.
		source:	Bone to take transforms from (head, tail, roll, bbone_x, bbone_z).
			NOTE: Ideally a source should always be specified, or bbone_x/z specified, otherwise blender will use the default 0.1, which can result in giant or tiny bones.
		kwargs: Allow setting arbitrary bone properties at initialization.
		"""

		self.container = container

		### The following dictionaries store pure information, never references to the real thing. ###
		# PoseBone custom properties.
		self.custom_props = {}
		# EditBone custom properties.
		self.custom_props_edit = {}
		# data_path:Driver dictionary, where data_path is from the bone. Only for drivers that are directly on a bone property! Not a sub-ID like constraints.
		self.drivers = {}
		self.bone_drivers = {}

		# List of (Type, attribs{}) tuples where attribs{} is a dictionary with the attributes of the constraint.
		# "drivers" is a valid attribute which expects the same content as self.drivers, and it holds the constraints for constraint properties.
		# TODO: I'm too lazy to implement a container for every constraint type, or even a universal one, but maybe I should.
		self.constraints = []

		### Edit Bone properties
		# Note that for these bbone properties, we are referring only to edit bone versions of the values.
		self.head = Vector((0,0,0))
		self.tail = Vector((0,1,0))
		self.roll = 0
		self.bbone_curveinx = 0
		self.bbone_curveiny = 0
		self.bbone_curveoutx = 0
		self.bbone_curveouty = 0
		self.bbone_easein = 1
		self.bbone_easeout = 1
		self.bbone_scaleinx = 1
		self.bbone_scaleiny = 1
		self.bbone_scaleoutx = 1
		self.bbone_scaleouty = 1

		### Bone properties
		self.name = name
		self.layers = [l==0 for l in range(32)]	# 32 bools where only the first one is True.
		self.rotation_mode = 'QUATERNION'
		self.hide_select = False
		self.hide = False

		self.parent = None	# Blender expects bpy.types.Bone, but we store definitions.bone.BoneInfo.
		self.use_connect = False
		self.use_deform = False
		self.show_wire = False
		self.use_endroll_as_inroll = False

		self.bbone_width = 0.1	# Property that wraps bbone_x and bbone_z.
		self._bbone_x = 0.1
		self._bbone_z = 0.1
		self.bbone_segments = 1
		self.bbone_handle_type_start = "AUTO"
		self.bbone_handle_type_end = "AUTO"
		self.bbone_custom_handle_start = ""	# Blender expects bpy.types.Bone, but we store str.	TODO: We should store BoneInfo here as well!!
		self.bbone_custom_handle_end = ""	# Blender expects bpy.types.Bone, but we store str.

		self.envelope_distance = 0.25
		self.envelope_weight = 1.0
		self.use_envelope_multiply = False
		self.head_radius = 0.1
		self.tail_radius = 0.1

		self.use_inherit_rotation = True
		self.inherit_scale = "FULL"
		self.use_local_location = True
		self.use_relative_parent = False

		### Pose Mode Only
		self._bone_group = None		# Blender expects bpy.types.BoneGroup, we store definitions.bone_group.BoneGroup.
		self.custom_shape = None	# Blender expects bpy.types.Object, we store bpy.types.Object.
		self.custom_shape_transform = None	# Blender expects bpy.types.PoseBone, we store definitions.bone.BoneInfo.
		self.custom_shape_scale = 1.0
		self.use_custom_shape_bone_size = False

		self.lock_location = [False, False, False]
		self.lock_rotation = [False, False, False]
		self.lock_rotation_w = False
		self.lock_scale = [False, False, False]

		# Apply property values from container's defaults
		for key, value in self.container.defaults.items():
			setattr_safe(self, key, value)

		if source:
			self.head = source.head.copy()
			self.tail = source.tail.copy()
			self.roll = source.roll
			self.envelope_distance = source.envelope_distance
			self.envelope_weight = source.envelope_weight
			self.use_envelope_multiply = source.use_envelope_multiply
			self.head_radius = source.head_radius
			self.tail_radius = source.tail_radius
			if type(source)==BoneInfo:
				self._bone_group = source._bone_group
				self.bbone_width = source.bbone_width
			else:
				self._bbone_x = source.bbone_x
				self._bbone_z = source.bbone_z
			if source.parent:
				if type(source)==bpy.types.EditBone:
					self.parent = source.parent.name
				else:
					self.parent = source.parent 

		if type(bone_group) != str:
			self.bone_group = bone_group

		# Apply property values from arbitrary keyword arguments if any were passed.
		for key, value in kwargs.items():
			setattr_safe(self, key, value)

	def __str__(self):
		return self.name

	@property
	def bbone_width(self):
		return self._bbone_x / self.container.scale

	@bbone_width.setter
	def bbone_width(self, value):
		"""Set BBone width relative to the rig's scale."""
		self._bbone_x = value * self.container.scale
		self._bbone_z = value * self.container.scale
		self.envelope_distance = value * self.container.scale
		self.head_radius = value * self.container.scale
		self.tail_radius = value * self.container.scale

	@property
	def bone_group(self):
		return self._bone_group

	@bone_group.setter
	def bone_group(self, value):
		# value is expected to be a cloudrig.definitions.bone_group.Bone_Group object.
		# Let the bone group know that this bone has been assigned to it.
		if value:
			value.assign_bone(self)
		elif self._bone_group:
			self._bone_group.remove_bone(self)

	@property
	def vec(self):
		"""Vector pointing from head to tail."""
		return self.tail-self.head

	@vec.setter
	def vec(self, value):
		self.tail = self.head + value

	def scale_width(self, value):
		"""Set bbone width relative to current."""
		self.bbone_width *= value

	def scale_length(self, value):
		"""Set bone length relative to its current length."""
		self.tail = self.head + self.vec * value

	@property
	def length(self):
		return (self.tail-self.head).length

	@length.setter
	def length(self, value):
		assert value > 0, "Length cannot be 0!"
		self.tail = self.head + self.vec.normalized() * value

	@property
	def center(self):
		return self.head + self.vec/2

	def set_layers(self, layerlist, additive=False):
		cloud_utils.set_layers(self, layerlist, additive)

	def put(self, loc, length=None, width=None, scale_length=None, scale_width=None):
		offset = loc-self.head
		self.head = loc
		self.tail = loc+offset

		if length:
			self.length=length
		if width:
			self.bbone_width = width
		if scale_length:
			self.scale_length(scale_length)
		if scale_width:
			self.scale_width(scale_width)

	def flatten(self):
		self.vec = cloud_utils.flat(self.vec)
		from math import pi
		deg = self.roll*180/pi
		# Round to nearest 90 degrees.
		rounded = round(deg/90)*90
		self.roll = pi/180*rounded

	def copy_info(self, bone_info):
		"""Called from __init__ to initialize using existing BoneInfo."""
		my_dict = self.__dict__
		skip = ["name"]
		for attr in my_dict.keys():
			if attr in skip: continue
			attr_copy = attr
			try:
				attr_copy = copy.deepcopy(attr)
			except:
				print(f"Warning: Failed to deepcopy {attr} while trying to initialize BoneInfo.")

			setattr_safe( self, attr, getattr(bone_info, attr_copy) )

	def copy_bone(self, armature, edit_bone):
		"""Called from __init__ to initialize using existing bone."""
		my_dict = self.__dict__
		skip = ['name', 'constraints', 'bl_rna', 'type', 'rna_type', 'error_location', 'error_rotation', 'is_proxy_local', 'is_valid', 'children']
		
		for key, value in my_dict.items():
			if key in skip: continue
			if(hasattr(edit_bone, key)):
				target_bone = getattr(edit_bone, key)
				if key in bone_attribs and target_bone:
					value = target_bone.name
				else:
					if key in ['layers']:
						value = list(getattr(edit_bone, key)[:])
					else:
						# NOTE: EDIT BONE PROPERTIES MUST BE DEEPCOPIED SO THEY AREN'T DESTROYED WHEN LEAVEING EDIT MODE!
						value = copy.deepcopy(getattr(edit_bone, key))
				setattr_safe(self, key, value)
				skip.append(key)

		# Read Pose Bone data (only if armature was passed)
		if not armature: return
		pose_bone = armature.pose.bones.get(edit_bone.name)
		if not pose_bone: return

		for attr in my_dict.keys():
			if attr in skip: continue

			if hasattr(pose_bone, attr):
				setattr_safe( self, attr, getattr(pose_bone, attr) )

		# Read Constraint data
		for c in pose_bone.constraints:
			constraint_data = (c.type, {})
			# TODO: Why are we using dir() here instead of __dict__?
			for attr in dir(c):
				if "__" in attr: continue
				if attr in skip: continue
				constraint_data[1][attr] = getattr(c, attr)

			self.constraints.append(constraint_data)

	def disown(self, new_parent):
		""" Parent all children of this bone to a new parent. """
		for b in self.container.bones:
			if b.parent==self or b.parent==self.name:
				b.parent = new_parent

	def add_constraint(self, armature, contype, true_defaults=False, prepend=False, **kwargs):
		"""Add a constraint to this bone.
		contype: Type of constraint, eg. 'STRETCH_TO'.
		props: Dictionary of properties and values.
		true_defaults: When False, we use a set of arbitrary default values that I consider better than Blender's defaults.
		"""
		props = kwargs
		# Override defaults with better ones.
		if not true_defaults:
			new_props = get_defaults(contype, armature)
			for key, value in kwargs.items():
				new_props[key] = value
			props = new_props
		
		if prepend:
			self.constraints.insert(0, (contype, props))
		else:
			self.constraints.append((contype, props))
		return props

	def clear_constraints(self):
		self.constraints = []

	def write_edit_data(self, armature, edit_bone):
		"""Write relevant data into an EditBone."""
		assert armature.mode == 'EDIT', "Error: Armature must be in Edit Mode when writing edit bone data."

		# Check for 0-length bones.
		if (self.head - self.tail).length == 0:
			# Warn and force length.
			print("WARNING: Had to force 0-length bone to have some length: " + self.name)
			self.tail = self.head+Vector((0, 0.1, 0))

		# Edit Bone Properties.

		for key, value in self.__dict__.items():
			if(hasattr(edit_bone, key)):
				if key == 'use_connect': continue	# TODO why does this break everything?
				if key in bone_attribs:
					real_bone = None
					if(type(value) == str):
						real_bone = armature.data.edit_bones.get(value)
					elif(type(value) == BoneInfo):
						real_bone = value.get_real(armature)
						if not real_bone:
							print(f"WARNING: {key}: {self.parent.name} not found for bone: {self.name}")
					elif value != None:
						# TODO: Maybe this should be raised when assigning the parent in the first place(via @property setter/getter)
						assert False, "ERROR: Unsupported parent type: " + str(type(value))
					
					setattr_safe(edit_bone, key, real_bone)
				else:
					# We don't want Blender to destroy my object references(particularly vectors) when leaving edit mode, so pass in a deepcopy instead.
					setattr_safe(edit_bone, key, copy.deepcopy(value))
		
		edit_bone.bbone_x = self._bbone_x
		edit_bone.bbone_z = self._bbone_z
					
		# Custom Properties.
		for key, prop in self.custom_props_edit.items():
			prop.make_real(edit_bone)
		
		# Without this, ORG- bones' Copy Transforms constraints can't work properly.
		edit_bone.use_connect = False

	def write_pose_data(self, pose_bone):
		"""Write relevant data into a PoseBone."""
		armature = pose_bone.id_data

		assert armature.mode != 'EDIT', "Armature cannot be in Edit Mode when writing pose data"

		my_dict = self.__dict__
		
		# Pose bone data
		pb = pose_bone
		pb.custom_shape = self.custom_shape
		pb.custom_shape_scale = self.custom_shape_scale
		if self.custom_shape_transform:
			pb.custom_shape_transform = armature.pose.bones.get(self.custom_shape_transform.name)
		pb.use_custom_shape_bone_size = self.use_custom_shape_bone_size

		pb.lock_location = self.lock_location
		pb.lock_rotation = self.lock_rotation
		pb.lock_rotation_w = self.lock_rotation_w
		pb.lock_scale = self.lock_scale

		# Bone data
		b = pb.bone
		b.layers = self.layers[:]
		b.use_deform = self.use_deform
		b.bbone_x = self._bbone_x
		b.bbone_z = self._bbone_z
		b.bbone_segments = self.bbone_segments
		b.bbone_handle_type_start = self.bbone_handle_type_start
		b.bbone_handle_type_end = self.bbone_handle_type_end
		b.bbone_custom_handle_start = armature.data.bones.get(self.bbone_custom_handle_start or "")
		b.bbone_custom_handle_end = armature.data.bones.get(self.bbone_custom_handle_end or "")
		b.show_wire = self.show_wire
		b.use_endroll_as_inroll = self.use_endroll_as_inroll

		b.use_inherit_rotation = self.use_inherit_rotation
		b.inherit_scale = self.inherit_scale
		b.use_local_location = self.use_local_location
		b.use_relative_parent = self.use_relative_parent

		b.envelope_distance = self.envelope_distance
		b.envelope_weight = self.envelope_weight
		b.use_envelope_multiply = self.use_envelope_multiply
		b.head_radius = self.head_radius
		b.tail_radius = self.tail_radius
		
		# Constraints.
		for cd in self.constraints:
			con_type = cd[0]
			cinfo = cd[1]
			c = pose_bone.constraints.new(con_type)
			if 'name' in cinfo:
				c.name = cinfo['name'] 
			#c = find_or_create_constraint(pose_bone, con_type, name)
			for key, value in cinfo.items():
				if con_type == 'ARMATURE' and key=='targets':
					# Armature constraint targets need special treatment. D'oh!
					# We assume the value of "targets" is a list of dictionaries describing a target.
					for tinfo in value:	# For each of those dictionaries
						target = c.targets.new()	# Create a target
						# Set armature as the target by default so we don't have to always specify it.
						target.target = armature
						# Copy just these three values.
						copy = ['weight', 'target', 'subtarget']
						for prop in copy:
							if prop in tinfo:
								setattr_safe(target, prop, tinfo[prop])
				elif(hasattr(c, key)):
					setattr_safe(c, key, value)

				# Fix stretch constraints
				if c.type == 'STRETCH_TO':
					c.rest_length = 0
		
		# Custom Properties.
		for key, prop in self.custom_props.items():
			prop.make_real(pose_bone)
		
		# Pose Bone Property Drivers.
		for path, d in self.drivers.items():
			data_path = f'pose.bones["{pose_bone.name}"].{path}'
			d.make_real(pose_bone.id_data, data_path)
	
		# Data Bone Property Drivers.
		for path, d in self.bone_drivers.items():
			#HACK: If we want to add drivers to bone properties that are shared between pose and edit mode, they aren't stored under armature.pose.bones[0].property but instead armature.bones[0].property... The entire way we handle drivers should be scrapped tbh. :P
			# But scrapping that requires scrapping the way we handle bones, so... just keep making it work.
			data_path = f'bones["{pose_bone.name}"].{path}'
			d.make_real(pose_bone.id_data.data, data_path)
	
	def get_real(self, armature):
		"""If a bone with the name in this BoneInfo exists in the passed armature, return it."""
		if armature.mode == 'EDIT':
			return armature.data.edit_bones.get(self.name)
		else:
			return armature.pose.bones.get(self.name)