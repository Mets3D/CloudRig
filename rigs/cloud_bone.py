import bpy
from bpy.props import BoolProperty, StringProperty, EnumProperty
from rigify.base_rig import BaseRig, stage
from rigify.utils.bones import BoneDict
from ..definitions.bone import BoneInfoContainer, BoneInfo
from ..definitions.driver import Driver
from ..definitions import custom_props

# TODO: When Transforms param is unchecked, move the metabone to the generated bone's transforms during generation?

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
		
		# TODO: If the bone already exists, delete it.
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
		
		# Constraint re-linking is done similarly to Rigify, but without the prefix-only shorthand.
		# Constraint names can contain an @ character which separates the constraint name from the desired target to set when all bones have been generated.
		# Eg. "Transformation@FK-Spine" on meta_bone will result in a constraint on mod_bone called "Transformation" with "FK-Spine" as its subtarget.
		# Armature constraints can have multiple @ targets.
		for org_c in org_bone.constraints:
			# Create a copy of this constraint on mod_bone
			new_con = self.copy_constraint(org_c, mod_bone)
			new_con.target = self.obj
			split_name = new_con.name.split("@")
			subtargets = split_name[1:]
			if new_con.type=='ARMATURE':
				for i, t in enumerate(new_con.targets):
					t.target = self.obj
					t.subtarget = subtargets[i]	# IndexError is possible and allowed here.
				continue
			if len(subtargets) > 0:
				new_con.subtarget = subtargets[0]
				new_con.name = split_name[0]
			else:
				# This is allowed to happen with targetless constraints like Limit Location.
				pass
		
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
			,description="Add the constraints of this bone to the generated bone's constraints. When disabled, we replace the constraints instead"
			,default=True
		)

		params.CR_copy_type = EnumProperty(
			name="Copy Type"
			,items=(
				("Create", "Create", "Create a new bone"),
				("Tweak", "Tweak", "Tweak an existing bone")
			)
			,description="Create: Create a standalone control (If one exists, overwrite it completely). Tweak: Find a control with the name of this bone, and overwrite it only partially"
			,default="Create"
		)

		# Parameters for tweaking existing bone
		params.CR_custom_bone_parent = StringProperty(
			 name="Parent"
			,description="When this is not an empty string, set the parent to the bone with this name"
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


		# Parameters for copying the bone
		params.CR_create_deform_bone = BoolProperty(
			 name="Create Deform Bone"
			,description="Create a copy of the ORG bone with use_deform enabled, and with the bbone settings of this bone"
			,default=True
		)

	@classmethod
	def parameters_ui(cls, layout, params):
		"""Create the ui for the rig parameters."""
		layout.use_property_split = True
		
		layout.prop(params, "CR_custom_bone_parent")
		layout.row().prop(params, "CR_copy_type", expand=True, text="Copy Type")
		row = layout.row()
		col1 = row.column()
		col2 = row.column()	# Empty column for indent
		if params.CR_copy_type=='Tweak':
			col1.prop(params, "CR_constraints_additive")
			col1.prop(params, "CR_bone_transforms")
			col1.prop(params, "CR_transform_locks")
			col1.prop(params, "CR_bone_rot_mode")
			col1.prop(params, "CR_bone_shape")
			col1.prop(params, "CR_bone_group")
			col1.prop(params, "CR_layers")
			col1.prop(params, "CR_custom_props")
			col1.prop(params, "CR_ik_settings")
		else:
			col1.prop(params, "CR_create_deform_bone")

class Rig(CloudBoneRig):
	pass

def create_sample(obj):
    # generated by rigify.utils.write_metarig
    bpy.ops.object.mode_set(mode='EDIT')
    arm = obj.data

    bones = {}

    bone = arm.edit_bones.new('Spine')
    bone.head = 0.0000, 0.0027, 0.8214
    bone.tail = 0.0000, -0.0433, 1.0137
    bone.roll = 0.0000
    bone.use_connect = False
    bone.bbone_x = 0.0135
    bone.bbone_z = 0.0135
    bone.head_radius = 0.0114
    bone.tail_radius = 0.0122
    bone.envelope_distance = 0.1306
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bones['Spine'] = bone.name
    bone = arm.edit_bones.new('MSTR-P-Torso')
    bone.head = 0.0000, -0.0758, 1.3939
    bone.tail = 0.0000, -0.0758, 1.6091
    bone.roll = 1.5708
    bone.use_connect = False
    bone.bbone_x = 0.0135
    bone.bbone_z = 0.0135
    bone.head_radius = 0.0124
    bone.tail_radius = 0.0133
    bone.envelope_distance = 0.1422
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bones['MSTR-P-Torso'] = bone.name
    bone = arm.edit_bones.new('RibCage')
    bone.head = 0.0000, -0.0433, 1.0137
    bone.tail = 0.0000, -0.0449, 1.1585
    bone.roll = 0.0000
    bone.use_connect = True
    bone.bbone_x = 0.0124
    bone.bbone_z = 0.0124
    bone.head_radius = 0.0122
    bone.tail_radius = 0.0121
    bone.envelope_distance = 0.1231
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bone.parent = arm.edit_bones[bones['Spine']]
    bones['RibCage'] = bone.name
    bone = arm.edit_bones.new('Chest')
    bone.head = 0.0000, -0.0449, 1.1585
    bone.tail = 0.0000, -0.0139, 1.2808
    bone.roll = 0.0000
    bone.use_connect = True
    bone.bbone_x = 0.0108
    bone.bbone_z = 0.0108
    bone.head_radius = 0.0121
    bone.tail_radius = 0.0118
    bone.envelope_distance = 0.1000
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bone.parent = arm.edit_bones[bones['RibCage']]
    bones['Chest'] = bone.name
    bone = arm.edit_bones.new('Neck')
    bone.head = 0.0000, -0.0139, 1.2808
    bone.tail = 0.0000, -0.0268, 1.3924
    bone.roll = 0.0000
    bone.use_connect = True
    bone.bbone_x = 0.0056
    bone.bbone_z = 0.0056
    bone.head_radius = 0.0118
    bone.tail_radius = 0.0138
    bone.envelope_distance = 0.0739
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bone.parent = arm.edit_bones[bones['Chest']]
    bones['Neck'] = bone.name
    bone = arm.edit_bones.new('Head')
    bone.head = 0.0000, -0.0268, 1.3924
    bone.tail = 0.0000, -0.0519, 1.6160
    bone.roll = 0.0000
    bone.use_connect = True
    bone.bbone_x = 0.0113
    bone.bbone_z = 0.0113
    bone.head_radius = 0.0138
    bone.tail_radius = 0.0583
    bone.envelope_distance = 0.0799
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bone.parent = arm.edit_bones[bones['Neck']]
    bones['Head'] = bone.name

    bpy.ops.object.mode_set(mode='OBJECT')
    pbone = obj.pose.bones[bones['Spine']]
    pbone.rigify_type = 'cloud_spine'
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'
    try:
        pbone.rigify_parameters.CR_sharp_sections = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_deform_segments = 1
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_bbone_segments = 6
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_show_display_settings = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_show_spine_settings = True
    except AttributeError:
        pass
    pbone = obj.pose.bones[bones['MSTR-P-Torso']]
    pbone.rigify_type = 'cloud_bone'
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'XYZ'
    try:
        pbone.rigify_parameters.CR_sharp_sections = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_deform_segments = 1
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_bbone_segments = 6
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_copy_type = "Tweak"
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_bone_transforms = True
    except AttributeError:
        pass
    pbone = obj.pose.bones[bones['RibCage']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['Chest']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['Neck']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['Head']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'

    bpy.ops.object.mode_set(mode='EDIT')
    for bone in arm.edit_bones:
        bone.select = False
        bone.select_head = False
        bone.select_tail = False
    for b in bones:
        bone = arm.edit_bones[bones[b]]
        bone.select = True
        bone.select_head = True
        bone.select_tail = True
        arm.edit_bones.active = bone

    return bones