from bpy.props import *
from rigify.base_rig import BaseRig, stage
from rigify.utils.bones import BoneDict
from ..definitions.bone import BoneInfoContainer, BoneInfo
from ..definitions.driver import Driver
from ..definitions import custom_props

# TODO: Implement more parameters.
# TODO: Implement constraint re-targetting(take code and conventions from Rigify where ideal)
# TODO: When Transforms param is unchecked, move the metabone to the generated bone's transforms during generation.
# It would be ideal to be able to delete the ORG bone, but life will be a lot easier if we just don't do that.

class CloudBoneRig(BaseRig):
	""" A rig type to add or modify a single bone in the generated rig. 
	For modifying other generated bones, you want to make sure this rig gets executed last. This may require that you don't parent this bone to anything.
	"""
	def find_org_bones(self, pose_bone):
		return pose_bone.name

	def initialize(self):
		super().initialize()
		self.defaults={}
		self.scale=1
		self.bone_name = self.base_bone.replace("ORG-", "")

	def copy_constraint(self, from_con, to_bone):
		new_con = to_bone.constraints.new(from_con.type)
		new_con.name = from_con.name

		skip = ['active', 'bl_rna', 'error_location', 'error_rotation']
		for key in dir(from_con):
			if "__" in key: continue
			if(key in skip): continue

			if key=='targets' and new_con.type=='ARMATURE':
				for t in from_con.targets:
					new_t = new_con.targets.new()
					new_t.target = from_con.target
					new_t.subtarget = from_con.subtarget
				continue

			value = getattr(from_con, key)
			try:
				setattr(new_con, key, value)
			except AttributeError:	# Read-Only properties throw AttributeError. These should all be added to the skip list.
				print("Warning: Can't copy read-only attribute %s to %s type constraint" %(key, new_con.type) )
				continue
		
		return new_con

	def copy_pose_bone(self, from_bone, to_bone):
		pass

	def generate_bones(self):
		if self.params.CR_copy_type != "Create": return
		
		# Make a copy of the ORG- bone without the ORG- prefix. This is our control bone.
		mod_bone_name = self.copy_bone(self.bones.org, self.bone_name, parent=True)
		self.bone_name = mod_bone_name
		
		# Make a copy with DEF- prefix, as our deform bone.
		if self.params.CR_create_deform_bone: 
			def_bone_name = self.copy_bone(self.bones.org, self.bone_name)
			def_bone = self.get_bone(def_bone_name)
			def_bone.name = "DEF-" + self.bone_name
			def_bone.parent = self.get_bone(self.bone_name)

		# And then we hack our parameters, so future stages just modify this newly created bone :)
		# Afaik, we only need to worry about pose bone properties, edit_bone stuff is taken care of by self.copy_bone().
		self.params.CR_copy_type = 'Tweak'
		self.params.CR_transform_locks = True
		self.params.CR_bone_rot_mode = True
		self.params.CR_bone_shape = True
		self.params.CR_layers = True
		self.params.CR_custom_props = True
		self.params.CR_ik_settings = True

	@stage.configure_bones
	def modify_bone_group(self):
		if self.params.CR_copy_type != 'Tweak': return
		mod_bone = self.get_bone(self.bone_name)
		meta_bone = self.generator.metarig.pose.bones.get(self.bone_name)

		meta_bg = meta_bone.bone_group
		if self.params.CR_bone_group:
			if meta_bg:
				bg_name = meta_bg.name
				bg = self.obj.pose.bone_groups.get(bg_name)
				if not bg:
					bg = self.obj.pose.bone_groups.new(bg_name)
					bg.color_set = meta_bg.color_set
					bg.colors.normal = meta_bg.colors.normal[:]
					bg.colors.active = meta_bg.colors.active[:]
					bg.colors.select = meta_bg.colors.select[:]
				mod_bone.bone_group = bg
			else:
				mod_bone.bone_group = None

	@stage.apply_bones
	def modify_edit_bone(self):
		if self.params.CR_copy_type != 'Tweak': return
		bone_name = self.base_bone.replace("ORG-", "")
		mod_bone = self.get_bone(bone_name)
		org_bone = self.get_bone(self.base_bone)
		meta_bone = self.generator.metarig.data.bones.get(bone_name)

		if self.params.CR_bone_transforms:
			mod_bone.head = meta_bone.head_local.copy()
			mod_bone.tail = meta_bone.tail_local.copy()
			mod_bone.roll = org_bone.roll
			mod_bone.bbone_x = meta_bone.bbone_x
			mod_bone.bbone_z = meta_bone.bbone_z
		
		parent = self.obj.data.edit_bones.get(self.params.CR_custom_bone_parent)
		
		if parent:
			mod_bone.parent = parent

	@stage.finalize
	def modify_pose_bone(self):
		if self.params.CR_copy_type != 'Tweak': return
		mod_bone = self.get_bone(self.bone_name)
		meta_bone = self.generator.metarig.pose.bones.get(self.bone_name)
		org_bone = self.get_bone(self.base_bone)
		
		if self.params.CR_transform_locks:
			mod_bone.lock_location = meta_bone.lock_location[:]
			mod_bone.lock_rotation = meta_bone.lock_rotation[:]
			mod_bone.lock_rotation_w = meta_bone.lock_rotation_w
			mod_bone.lock_scale = meta_bone.lock_scale[:]
		
		if self.params.CR_bone_rot_mode:
			mod_bone.rotation_mode = meta_bone.rotation_mode
		
		if self.params.CR_bone_shape:
			mod_bone.custom_shape = meta_bone.custom_shape
			mod_bone.custom_shape_scale = meta_bone.custom_shape_scale
			mod_bone.custom_shape_transform = meta_bone.custom_shape_transform
			mod_bone.use_custom_shape_bone_size = meta_bone.use_custom_shape_bone_size
			mod_bone.bone.show_wire = meta_bone.bone.show_wire
		
		if self.params.CR_layers:
			mod_bone.bone.layers = meta_bone.bone.layers[:]
		
		if self.params.CR_ik_settings:
			mod_bone.ik_stretch = meta_bone.ik_stretch
			mod_bone.lock_ik_x = meta_bone.lock_ik_x
			mod_bone.lock_ik_y = meta_bone.lock_ik_y
			mod_bone.lock_ik_z = meta_bone.lock_ik_z
			mod_bone.ik_stiffness_x = meta_bone.ik_stiffness_x
			mod_bone.ik_stiffness_y = meta_bone.ik_stiffness_y
			mod_bone.ik_stiffness_z = meta_bone.ik_stiffness_z
			mod_bone.use_ik_limit_x = meta_bone.use_ik_limit_x
			mod_bone.use_ik_limit_y = meta_bone.use_ik_limit_y
			mod_bone.use_ik_limit_z = meta_bone.use_ik_limit_z
			mod_bone.ik_min_x = meta_bone.ik_min_x
			mod_bone.ik_max_x = meta_bone.ik_max_x
			mod_bone.ik_min_y = meta_bone.ik_min_y
			mod_bone.ik_max_y = meta_bone.ik_max_y
			mod_bone.ik_min_z = meta_bone.ik_min_z
			mod_bone.ik_max_z = meta_bone.ik_max_z

		if not self.params.CR_constraints_additive:
			mod_bone.constraints.clear()
		
		# Constraint re-linking is done similarly to Rigify, but without the functionality for hard-coded prefix shorthand.
		# Constraint names can contain an @ character which separates the constraint name from the desired target to set when all bones have been generated.
		# Eg. "Transformation@FK-Spine" on meta_bone will create a constraint called "Transformation" with "FK-Spine" as its subtarget.
		# Armature constraints can have multiple @ targets. (Running into the constraint name character limit is a concern here though)
		for org_c in org_bone.constraints:
			# Create a copy of this constraint on mod_bone
			new_con = self.copy_constraint(org_c, mod_bone)
			split_name = new_con.name.split("@")
			subtargets = split_name[1:]
			if new_con.type=='ARMATURE':
				for i, t in enumerate(new_con.targets):
					t.target = self.obj
					t.subtarget = subtargets[i]	# IndexError is possible and allowed here.
				continue
			new_con.target = self.obj
			new_con.subtarget = subtargets[0]
			new_con.name = split_name[0]
		
		# Copy custom properties
		if self.params.CR_custom_props and '_RNA_UI' in meta_bone.keys():
			keys = [k for k in meta_bone.keys() if k not in ['_RNA_UI', 'rigify_parameters', 'rigify_type']]
			custom_props.copy_custom_properties(meta_bone, keys, mod_bone)

		# Copy and retarget drivers
		self.copy_and_retarget_drivers(mod_bone)

	@stage.finalize
	def rig_org_bone(self):
		# Constrain the ORG- bone to the control bone.
		org_bone = self.get_bone(self.base_bone)
		self.make_constraint(self.base_bone, 'COPY_TRANSFORMS', self.bone_name)
	
	def copy_and_retarget_driver(self, BPY_driver, obj, data_path, index=-1):
		"""Copy a driver to some other data path, while accounting for any constraint retargetting."""
		driver = Driver(BPY_driver)
		data_path = BPY_driver.data_path
		if 'constraints' in data_path:
			org_con_name = data_path.split('constraints["')[-1].split('"]')[0]	# Oh, it's magnificent.
			new_con_name = org_con_name.split("@")[0]
			data_path = data_path.replace(org_con_name, new_con_name)
		for var in driver.variables:
			for t in var.targets:
				if t.id == self.generator.metarig:
					t.id = self.obj
		driver.make_real(obj, data_path, index)

	def copy_and_retarget_drivers(self, bone):
		"""Copy and retarget drivers from both the metarig Object and the metarig Data."""
		metarig = self.generator.metarig
		rig = self.obj
		if not metarig.animation_data: return

		for d in metarig.animation_data.drivers:
			if bone.name in d.data_path:
				self.copy_and_retarget_driver(d, rig, d.data_path, d.array_index)
		
		if not metarig.data.animation_data: return
		for d in metarig.data.animation_data.drivers:
			if bone.name in d.data_path:
				self.copy_and_retarget_driver(d, rig.data, d.data_path, d.array_index)

	##############################
	# Parameters

	@classmethod
	def add_parameters(cls, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		super().add_parameters(params)

		params.CR_constraints_additive = BoolProperty(
			name="Additive Constraints"
			,description="Add the constraints of this bone to the generated bone's constraints. When disabled, we replace the constraints instead (even when there aren't any)"
			,default=True
		)

		params.CR_copy_type = EnumProperty(
			name="Copy Type"
			,items=(
				("Create", "Create", "Create a new bone"),
				("Tweak", "Tweak", "Tweak an existing bone")
			)
			,description="Whether this bone should be copied to the generated rig as a new control on its own, or tweak a pre-existing bone that should exist after bone generation phase"
			,default="Create"
		)

		# These parameters are valid when CR_copy_type==True
		# TODO: We should do a search for P- bones, and have an option to affect those as well
		#	Better yet, when we create a P- bone for a bone, that bone should store the name of that P- bone in a custom property, so we don't need to do slow searches like this.
		#	Another idea is to be able to input a list of names that this bone should affect. But I'm not sure if there's a use case good enough for any of these things to bother implementing.
		params.CR_custom_bone_parent = StringProperty(
			 name="Parent"
			,description="When this is not an empty string, set the parent to the bone with this name."
			,default=""
		)
		params.CR_bone_transforms = BoolProperty(
			 name="Transforms"
			,description="Replace the matching generated bone's transforms with this bone's transforms" # An idea: when this is False, let the generation script affect the metarig - and move this bone, to where it is in the generated rig.
			,default=False
		)
		params.CR_transform_locks = BoolProperty(
			 name="Locks"
			,description="Replace the matching generated bone's transform locks with this bone's transform locks"
			,default=False
		)
		params.CR_bone_rot_mode = BoolProperty(
			 name="Rotation Mode"
			,description="Set the matching generated bone's rotation mode to this bone's rotation mode"
			,default=False
		)
		params.CR_bone_shape = BoolProperty(
			 name="Bone Shape"
			,description = "Replace the matching generated bone's shape with this bone's shape"
			,default=False
		)
		params.CR_bone_group = BoolProperty(
			 name="Bone Group"
			,description="Replace the matching generated bone's group with this bone's group"
			,default=False
		)
		params.CR_layers = BoolProperty(
			 name="Layers"
			,description="Set the generated bone's layers to this bone's layers"
			,default=False
		)
		params.CR_custom_props = BoolProperty(
			 name="Custom Properties"
			,description="Copy custom properties from this bone to the generated bone"
			,default=False
		)
		params.CR_ik_settings = BoolProperty(
			 name="IK Settings"
			,description="Copy IK settings from this bone to the generated bone"
			,default=False
		)

		# These parameters are valid when CR_copy_type==False
		# TODO: Implement control and unlocker. Or maybe just unlocker.
		params.CR_create_control_bone = BoolProperty(
			 name="Create Control Bone"
			,description="Create a copy of the ORG bone with use_deform disabled, with the name, bone group, layers, bone shape and constraints of this bone"
			,default=True
		)
		params.CR_create_unlocker_bone = BoolProperty(	# Is this overkill? Maybe if we want something this complex, we should be expected to have to add two bones to the metarig.
			 name="Create Unlocker Bone"
			,description="In addition to the control bone, create an extra parent to hold the constraints, so the control bone itself can be freely animated"
			,default=False
		)
		params.CR_create_deform_bone = BoolProperty(
			 name="Create Deform Bone"
			,description="Create a copy of the ORG bone with use_deform enabled, and with the bbone settings of this bone."
			,default=True
		)

	@classmethod
	def parameters_ui(cls, layout, params):
		"""Create the ui for the rig parameters."""
		super().parameters_ui(layout, params)
		layout.use_property_split = True
		
		col = layout.column()
		layout.prop(params, "CR_constraints_additive")
		layout.prop(params, "CR_custom_bone_parent")
		layout.row().prop(params, "CR_copy_type", expand=True, text="Copy Type")
		row = layout.row()
		col1 = row.column()	# Empty column for indent
		col2 = row.column()
		if params.CR_copy_type=='Tweak':
			col2.prop(params, "CR_bone_transforms")
			col2.prop(params, "CR_transform_locks")
			col2.prop(params, "CR_bone_rot_mode")
			col2.prop(params, "CR_bone_shape")
			col2.prop(params, "CR_bone_group")
			col2.prop(params, "CR_layers")
			col2.prop(params, "CR_custom_props")
			col2.prop(params, "CR_ik_settings")
		else:
			col2.prop(params, "CR_create_deform_bone")

class Rig(CloudBoneRig):
	pass