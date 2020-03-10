from bpy.props import *
from rigify.base_rig import BaseRig, stage
from rigify.utils.bones import BoneDict
from ..definitions.bone import BoneInfoContainer, BoneInfo
from ..definitions.driver import Driver

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
		self.orgless_name = self.bones.org.replace("ORG-", "")

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

	@stage.generate_bones
	def create_copy(self):
		# Make a copy of the ORG- bone without the ORG- prefix.
		if not self.params.op_type == "Create": return
		mod_bone = self.copy_bone(self.bones.org, self.orgless_name, parent=True)
		
		# And then we hack our parameters, so future stages just modify this newly created bone :)
		# Afaik, we only need to worry about pose bone properties, edit_bone stuff is taken care of by self.copy_bone().
		self.params.op_type='Tweak'
		self.params.transform_locks = True
		self.params.rot_mode = True
		self.params.bone_shape = True
		self.params.layers = True

	@stage.apply_bones
	def modify_edit_bone(self):
		if not self.params.op_type=='Tweak': return
		bone_name = self.base_bone.replace("ORG-", "")
		mod_bone = self.get_bone(bone_name)
		org_bone = self.get_bone(self.base_bone)
		meta_bone = self.generator.metarig.data.bones.get(bone_name)

		if self.params.transforms:
			mod_bone.head = meta_bone.head_local.copy()
			mod_bone.tail = meta_bone.tail_local.copy()
			mod_bone.roll = org_bone.roll
			mod_bone.bbone_x = meta_bone.bbone_x
			mod_bone.bbone_z = meta_bone.bbone_z
		
		parent = self.obj.data.edit_bones.get(self.params.parent)
		
		# WHY DOESN'T THIS WORK??? (When does the parent get overwritten after this, to be None?!)
		if parent:
			print(mod_bone)
			print("Trying to set parent for " + mod_bone.name)
			print("to " + parent.name)
			print(parent)
			mod_bone.parent = parent
			print("did it work? ")
			print(mod_bone.parent)
		else:
			print("Did not find parent for " + mod_bone.name)
			print("called " + self.params.parent)

	@stage.configure_bones
	def modify_bone_group(self):
		if not self.params.op_type=='Tweak': return
		mod_bone = self.get_bone(self.orgless_name)
		meta_bone = self.generator.metarig.pose.bones.get(self.orgless_name)

		meta_bg = meta_bone.bone_group
		if self.params.bone_group:
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

	@stage.finalize
	def modify_pose_bone(self):
		if not self.params.op_type=='Tweak': return
		bone_name = self.base_bone.replace("ORG-", "")
		mod_bone = self.get_bone(bone_name)
		meta_bone = self.generator.metarig.pose.bones.get(bone_name)
		org_bone = self.get_bone(self.base_bone)
		
		if self.params.transform_locks:
			mod_bone.lock_location = meta_bone.lock_location[:]
			mod_bone.lock_rotation = meta_bone.lock_rotation[:]
			mod_bone.lock_rotation_w = meta_bone.lock_rotation_w
			mod_bone.lock_scale = meta_bone.lock_scale[:]
		
		if self.params.rot_mode:
			mod_bone.rotation_mode = meta_bone.rotation_mode
		
		if self.params.bone_shape:
			mod_bone.custom_shape = meta_bone.custom_shape
			mod_bone.custom_shape_scale = meta_bone.custom_shape_scale
			mod_bone.custom_shape_transform = meta_bone.custom_shape_transform
			mod_bone.use_custom_shape_bone_size = meta_bone.use_custom_shape_bone_size
			mod_bone.bone.show_wire = meta_bone.bone.show_wire
		
		if self.params.layers:
			mod_bone.bone.layers = meta_bone.bone.layers[:]
		
		if not self.params.constraints_additive:
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
		
		self.copy_and_retarget_drivers(mod_bone)

	def copy_and_retarget_driver(self, BPY_driver, obj, data_path, index=-1):
		"""Copy a driver to some other data path."""
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

		params.constraints_additive = BoolProperty(
			name="Additive Constraints",
			description="Add the constraints of this bone to the generated bone's constraints. When disabled, we replace the constraints instead (even when there aren't any)",
			default=True
		)

		# TODO: Behaviour for when this is False. Also more parameters for that, if needed. Also, turn it into an enum.
		# TODO: Do these two things even need to be in the same rig? Maybe we should just have separate copy and tweak rigs?
		
		# I like the way this works for tweaking existing bones, but how should things work when creating a new bone?
		# Some use cases:
		# Shoulder rig; This needs a control bone with a shape and group, but also a deform bone, and the ORG- bone really doesn't hurt.
		# Extra hip bone: This would be just a deform bone with a constraint, and importantly, an arbitrary parent that only exists in the generated rig(which is the first STR bone of the spine). An ORG- bone is really quite useless here. But I guess the idea or being able to extract the metarig by taking ORG- bones and removing the ORG- prefix is a good idea.


		params.op_type = EnumProperty(
			name="Copy Type",
			items=(
				("Create", "Create", "Create a new bone"),
				("Tweak", "Tweak", "Tweak an existing bone")
			),
			description="Whether this bone should be copied to the generated rig as a new control on its own, or tweak a pre-existing bone that should exist after bone generation phase",
			default="Create"
		)

		# These parameters are valid when op_type==True
		# TODO: We should do a search for P- bones, and have an option to affect those as well
		#	Better yet, when we create a P- bone for a bone, that bone should store the name of that P- bone in a custom property, so we don't need to do slow searches like this.
		#	Another idea is to be able to input a list of names that this bone should affect. But I'm not sure if there's a use case good enough for any of these things to bother implementing.
		params.parent = StringProperty(
			name="Parent",
			description="When this is not an empty string, set the parent to the bone with this name.",
			default=""
		)
		params.transforms = BoolProperty(
			name="Transforms",
			description="Replace the matching generated bone's transforms with this bone's transforms", # TODO: An idea: when this is False, let the generation script affect the metarig - and move this bone, to where it is in the generated rig.
			default=False
		)
		params.transform_locks = BoolProperty(
			name="Locks",
			description="Replace the matching generated bone's transform locks with this bone's transform locks",
			default=False
		)
		params.rot_mode = BoolProperty(
			name="Rotation Mode",
			description="Set the matching generated bone's rotation mode to this bone's rotation mode",
			default=False
		)
		params.bone_shape = BoolProperty(
			name="Bone Shape",
			description = "Replace the matching generated bone's shape with this bone's shape",
			default=False
		)
		params.bone_group = BoolProperty(
			name="Bone Group",
			description="Replace the matching generated bone's group with this bone's group",
			default=False
		)
		params.layers = BoolProperty(
			name="Layers",
			description="Set the generated bone's layers to this bone's layers",
			default=False
		)
		#TODO: implement this.
		params.custom_props = BoolProperty(
			name="Custom Properties",
			description="Copy custom properties from this bone to the the generated bone",
			default=False
		)

		# These parameters are valid when op_type==False
		# TODO.
		params.control = BoolProperty(
			name="Create Control Bone",
			description="Create a copy of the ORG bone with use_deform disabled, with the name, bone group, layers, bone shape and constraints of this bone",
			default=True
		)
		params.unlocker = BoolProperty(	# Is this overkill? Maybe if we want something this complex, we should be expected to have to add two bones to the metarig.
			name="Create Unlocker Bone",
			description="In addition to the control bone, create an extra parent to hold the constraints, so the control bone itself can be freely animated",
			default=False
		)
		params.deform = BoolProperty(
			name="Create Deform Bone",
			description="Create a copy of the ORG bone with use_deform enabled, and with the bbone settings of this bone.",
			default=True
		)

	@classmethod
	def parameters_ui(cls, layout, params):
		"""Create the ui for the rig parameters."""
		super().parameters_ui(layout, params)
		layout.use_property_split = True
		
		col = layout.column()
		layout.prop(params, "constraints_additive")
		layout.row().prop(params, "op_type", expand=True, text="Copy Type")
		row = layout.row()
		col1 = row.column()	# Empty column for indent
		col2 = row.column()
		if params.op_type=='Tweak':
			col2.prop(params, "parent")
			col2.prop(params, "transforms")
			col2.prop(params, "transform_locks")
			col2.prop(params, "rot_mode")
			col2.prop(params, "bone_shape")
			col2.prop(params, "bone_group")
			col2.prop(params, "layers")
			col2.prop(params, "custom_props")
		else:
			col2.prop(params, "deform")

class Rig(CloudBoneRig):
	pass