# Data Container and utilities for de-coupling bone creation and setup from BPY.
# Lets us easily create bones without having to worry about edit/pose mode.
import bpy
from .id import *
from mathutils import *
from mets_tools.utils import *
import copy
from ..shared import group_defs

# Attributes that reference an actual bone ID. These should get special treatment, because we don't want to store said bone ID. 
# Ideally we would store a BoneInfo, but a string is allowed too(less safe).
bone_attribs = ['parent', 'bbone_custom_handle_start', 'bbone_custom_handle_end']

def get_defaults(contype, armature):
	"""Return my preferred defaults for each constraint type."""
	ret = {
		"target" : armature,
	 }

	if contype not in ['STRETCH_TO', 'ARMATURE', 'IK']:
		ret["target_space"] = 'LOCAL'
		ret["owner_space"] = 'LOCAL'

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

def setattr2(thing, key, value):
	try:
		setattr(thing, key, value)
	except:
		print("ERROR: Wrong type assignment: key:%s, type:%s, expected:%s"%(key, type(key), type(getattr(thing, key)) ) )

class BoneInfoContainer(ID):
	# TODO: implement __iter__ and such.
	def __init__(self, armature, defaults={}):
		self.bones = []
		self.defaults = defaults	# For overriding arbitrary properties' default values when creating bones in this container.

		# Load info about existing bones in the armature...
		org_mode = armature.mode
		bpy.ops.object.mode_set(mode='EDIT')
		for eb in armature.data.edit_bones:
			self.bone(eb.name, eb, armature)
		bpy.ops.object.mode_set(mode=org_mode)

	def find(self, name):
		"""Find a BoneInfo instance by name, return it if found."""
		for bd in self.bones:
			if(bd.name == name):
				return bd
		return None
	
	def bone(self, name="Bone", source=None, armature=None, **kwargs):
		"""Define a bone and add it to the list of bones. If a bone with the same name already existed, OVERWRITE IT."""
		bi = self.find(name)
		if bi:
			self.bones.remove(bi)
		
		bi = BoneInfo(self, name, source, armature, **kwargs)
		self.bones.append(bi)
			
		return bi

	def create_multiple_bones(self, armature, bones):
		"""This will only switch between modes twice, so it is the preferred way of creating bones."""
		assert armature.select_get() or bpy.context.view_layer.objects.active == armature, "Armature must be selected or active."
		
		org_mode = armature.mode

		bpy.ops.object.mode_set(mode='EDIT')
		# First we create all the bones.
		for bd in bones:
			edit_bone = find_or_create_bone(armature, bd.name)
		
		# Now that all the bones are created, loop over again to set the properties.
		for bd in bones:
			edit_bone = armature.data.edit_bones.get(bd.name)
			bd.write_edit_data(armature, edit_bone)

		# And finally a third time, after switching to pose mode, so we can add constraints.
		bpy.ops.object.mode_set(mode='POSE')
		for bd in bones:
			pose_bone = armature.pose.bones.get(bd.name)
			bd.write_pose_data(pose_bone)
		
		bpy.ops.object.mode_set(mode=org_mode)

	def make_real(self, armature, clear=True):
		self.create_multiple_bones(armature, self.bones)
		if clear:
			self.clear()
	
	def clear(self):
		self.bones = []

class BoneInfo(ID):
	"""Container of all info relating to a Bone."""
	def __init__(self, container, name="Bone", source=None, armature=None, only_transform=False, **kwargs):
		# Need a reference to what BoneInfoContainer this BoneInfo belongs to.
		self.container = container

		### All of the following store abstractions, not the real thing. ###
		# PoseBone custom properties.
		self.custom_props = {}
		# EditBone custom properties.
		self.custom_props_edit = {}
		# data_path:Driver dictionary, where data_path is from the bone. Only for drivers that are directly on a bone property! Not a sub-ID like constraints.
		self.drivers = {}
		# List of (Type, attribs{}) tuples where attribs{} is a dictionary with the attributes of the constraint.
		# "drivers" is a valid attribute which expects the same content as self.drivers, and it holds the constraints for constraint properties.
		# I'm too lazy to implement a container for every constraint type, or even a universal one, but maybe I should.
		self.constraints = []
		
		self.name = name
		self.head = Vector((0,0,0))
		self.tail = Vector((0,1,0))
		self.roll = 0
		self.layers = [False]*32
		self.rotation_mode = 'QUATERNION'
		self.bbone_curveinx = 0
		self.bbone_curveiny = 0
		self.bbone_curveoutx = 0
		self.bbone_curveouty = 0
		self.bbone_handle_type_start = "AUTO"
		self.bbone_handle_type_end = "AUTO"
		self.bbone_easein = 0
		self.bbone_easeout = 0
		self.bbone_scaleinx = 0
		self.bbone_scaleiny = 0
		self.bbone_scaleoutx = 0
		self.bbone_scaleouty = 0
		self.segments = 1
		self.bbone_x = 0.1
		self.bbone_z = 0.1
		self.bone_group = ""
		self.custom_shape = None   # Object ID?
		self.custom_shape_scale = 1.0
		self.use_custom_shape_bone_size = False
		self.use_endroll_as_inroll = False
		self.use_connect = False
		self.use_deform = False
		self.use_inherit_rotation = True
		self.use_inherit_scale = True
		self.use_local_location = True
		self.use_envelope_multiply = False
		self.use_relative_parent = False

		# We don't want to store a real Bone ID because we want to be able to set the parent before the parent was really created. So this is either a String or a BoneInfo instance.
		# TODO: These should be handled uniformally.
		# TODO: Maybe they should be forced to be BoneInfo instance, and don't allow str. Seems pointless and unneccessarily non-foolproof.
		self.custom_shape_transform = None # Bone name
		self.parent = None
		self.bbone_custom_handle_start = None
		self.bbone_custom_handle_end = None
		
		if only_transform:
			assert source, "If only_transform==True, source cannot be None!"
			self.head=copy.copy(source.head)
			self.tail=copy.copy(source.tail)
			self.roll=source.roll
			self.bbone_x=source.bbone_x
			self.bbone_z=source.bbone_z
		else:
			if(source and type(source)==BoneInfo):
				self.copy_info(source)
			elif(source and type(source)==bpy.types.EditBone):
				self.copy_bone(armature, source)
		
		# Apply property values from container's defaults
		for key, value in self.container.defaults.items():
			setattr2(self, key, value)

		# Apply property values from arbitrary keyword arguments if any were passed.
		for key, value in kwargs.items():
			setattr2(self, key, value)

	@property
	def bbone_width(self):
		return self.bbone_x

	@bbone_width.setter
	def bbone_width(self, value):
		self.bbone_x = value
		self.bbone_z = value

	@property
	def vec(self):
		"""Vector pointing from head to tail."""
		return self.tail-self.head

	@property
	def length(self):
		return (self.tail-self.head).size

	@length.setter
	def length(self, value):
		assert value > 0, "Length cannot be 0!"
		self.tail = self.head + self.vec.normalized() * value

	@property
	def center(self):
		return self.head + self.vec/2

	def set_layers(self, layerlist, wipe=True):
		if wipe:
			self.layers = [False]*32
		
		for i, e in enumerate(layerlist):
			if type(e)==bool:
				assert len(layerlist)==32, "ERROR: Layer assignment expected a list of 32 booleans, got %d."%len(layerlist)
				self.layers[i] = e
			elif type(e)==int:
				self.layers[e] = True

	def put(self, loc, length=None, width=None):
		offset = loc-self.head
		self.head = loc
		self.tail = loc+offset
		
		if length:
			self.length=length
		
		if width:
			self.bbone_width = width
	
	def copy_info(self, bone_info):
		"""Called from __init__ to initialize using existing BoneInfo."""
		my_dict = self.__dict__
		skip = ["name"]
		for attr in my_dict.keys():
			if attr in skip: continue
			setattr2( self, attr, getattr(bone_info, copy.deepcopy(attr)) )

	def copy_bone(self, armature, edit_bone):
		"""Called from __init__ to initialize using existing bone."""
		my_dict = self.__dict__
		skip = ['name', 'constraints', 'bl_rna', 'type', 'rna_type', 'error_location', 'error_rotation', 'is_proxy_local', 'is_valid']
		
		for key, value in my_dict.items():
			if key in skip: continue
			if(hasattr(edit_bone, key)):
				target_bone = getattr(edit_bone, key)
				if key in bone_attribs and target_bone:
					# TODO: Instead of just saving the name as a string, we should check if our BoneInfoContainer has a bone with this name, and if not, even go as far as to create it.
					# Look for the BoneInfo object corresponding to this bone in our BoneInfoContainer.
					bone_info = self.container.bone(name=target_bone.name, armature=armature, source=target_bone)
					value = bone_info
				else:
					# EDIT BONE PROPERTIES MUST BE DEEPCOPIED SO THEY AREN'T DESTROYED WHEN LEAVEING EDIT MODE. OTHERWISE IT FAILS SILENTLY!
					if key in ['layers']:
						value = list(getattr(edit_bone, key)[:])
					else:
						value = copy.deepcopy(getattr(edit_bone, key))
				setattr2(self, key, value)
				skip.append(key)

		# Read Pose Bone data (only if armature was passed)
		if not armature: return
		pose_bone = armature.pose.bones.get(edit_bone.name)
		if not pose_bone: return

		for attr in my_dict.keys():
			if attr in skip: continue

			if hasattr(pose_bone, attr):
				setattr2( self, attr, getattr(pose_bone, attr) )

		# Read Constraint data
		for c in pose_bone.constraints:
			constraint_data = (c.type, {})
			# TODO: Why are we using dir() here instead of __dict__?
			for attr in dir(c):
				if "__" in attr: continue
				if attr in skip: continue
				constraint_data[1][attr] = getattr(c, attr)

			self.constraints.append(constraint_data)

	def add_constraint(self, armature, contype, true_defaults=False, **kwargs):
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
		
		self.constraints.append((contype, props))
		return props

	def clear_constraints(self):
		self.constraints = []

	def write_edit_data(self, armature, edit_bone):
		"""Write relevant data into an EditBone."""
		assert armature.mode == 'EDIT', "Armature must be in Edit Mode when writing bone data"

		# Check for 0-length bones. Warn and skip if so.
		if (self.head - self.tail).length == 0:
			print("WARNING: Skpping 0-length bone: " + self.name)
			return
		
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
							print("WARNING: Parent %s not found for bone: %s" % (self.parent.name, self.name))
					elif value != None:
						# TODO: Maybe this should be raised when assigning the parent to the variable in the first place(via @property setter/getter)
						assert False, "ERROR: Unsupported parent type: " + str(type(value))
					
					setattr2(edit_bone, key, real_bone)
				else:
					# We don't want Blender to destroy my object references(particularly vectors) when leaving edit mode, so pass in a deepcopy instead.
					setattr2(edit_bone, key, copy.deepcopy(value))
					
		# Custom Properties.
		for key, prop in self.custom_props_edit.items():
			prop.make_real(edit_bone)

	def write_pose_data(self, pose_bone):
		"""Write relevant data into a PoseBone and its (Data)Bone."""
		armature = pose_bone.id_data

		assert armature.mode != 'EDIT', "Armature cannot be in Edit Mode when writing pose data"

		data_bone = armature.data.bones.get(pose_bone.name)

		my_dict = self.__dict__

		# Pose bone data.
		skip = ['constraints', 'head', 'tail', 'parent', 'length', 'use_connect', 'bone_group']
		for attr in my_dict.keys():
			value = my_dict[attr]
			if(hasattr(pose_bone, attr)):
				if attr in skip: continue
				if 'bbone' in attr: continue
				if(attr in ['custom_shape_transform'] and value):
					value = armature.pose.bones.get(value.name)
				setattr2(pose_bone, attr, value)

		# Data bone data.
		"""
		for attr in my_dict.keys():
			if(hasattr(data_bone, attr)):
				value = my_dict[attr]
				if attr in skip: continue
				# TODO: It should be more explicitly defined what properties we want to be setting here exactly, because I don't even know. Same for Pose and Edit data tbh.
				if attr in ['bbone_custom_handle_start', 'bbone_custom_handle_end']:
					if(type(value)==str):
						value = armature.data.bones.get(value)
				setattr2(data_bone, attr, value)
		"""
		
		# Bone group
		if self.bone_group:
			bone_group = armature.pose.bone_groups.get(self.bone_group)
			group_def = {}

			# If the bone group doesn't already exist, create it.
			if not bone_group:
				bone_group = armature.pose.bone_groups.new(name=self.bone_group)
			# If we have a definition for this group, set its attributes accordingly.
			if self.bone_group in group_defs:
				group_def = group_defs[self.bone_group]
				if self.bone_group in group_defs:
					for prop in ['normal', 'select', 'active']:
						if prop in group_def:
							bone_group.color_set='CUSTOM'
							setattr(bone_group.colors, prop, group_def[prop])
			
			pose_bone.bone_group = bone_group

			# Set layers if specified in the group definition.
			if 'layers' in group_def:
				self.set_layers(group_def['layers'])
		
		pose_bone.bone.layers = self.layers[:]
		
		# Constraints.
		for cd in self.constraints:
			con_type = cd[0]
			cinfo = cd[1]
			name = cinfo['name'] if 'name' in cinfo else None
			c = find_or_create_constraint(pose_bone, con_type, name)
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
								setattr2(target, prop, tinfo[prop])
				elif(hasattr(c, key)):
					setattr2(c, key, value)
		
		# Custom Properties.
		for key, prop in self.custom_props.items():
			prop.make_real(pose_bone)
		
		# Bone Property Drivers.
		for path, d in self.drivers.items():
			driv = d.make_real(pose_bone.id_data, path)
	
	def make_real(self, armature):
		# Create a single bone and its constraints. Needs to switch between object modes.
		# It is preferred to create bones in bulk via BoneDataContainer.create_all_bones().
		armature.select_set(True)
		bpy.context.view_layer.objects.active = armature
		org_mode = armature.mode

		bpy.ops.object.mode_set(mode='EDIT')
		edit_bone = find_or_create_bone(armature, self.name)
		self.write_edit_data(edit_bone)

		bpy.ops.object.mode_set(mode='POSE')
		pose_bone = armature.pose.bones.get(self.name)
		self.write_pose_data(pose_bone)

		bpy.ops.object.mode_set(mode=org_mode)
	
	def get_real(self, armature):
		if armature.mode == 'EDIT':
			return armature.data.edit_bones.get(self.name)
		else:
			return armature.pose.bones.get(self.name)