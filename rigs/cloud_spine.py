import bpy
from bpy.props import BoolProperty, IntProperty
from mathutils import Vector

from rigify.base_rig import stage
from rigify.utils.bones import BoneDict
from rigify.utils.rig import connected_children_names

from ..definitions.driver import Driver
from ..definitions.custom_props import CustomProp
from .cloud_fk_chain import CloudChainRig

#TODO: Allow multiple spine rigs in the same rig.
# Currently there can be only one spine in the rig, or at least only one that will be displayed in the UI, since the spine rig's IK property is always simply "ik_spine".
#     head hinge also has some hardcoded name strings.
#     When registering bones as a parent, the parent identifiers are also non-unique.

class CloudSpineRig(CloudChainRig):
	"""CloudRig Spine"""

	def find_org_bones(self, bone):
		"""Populate self.bones.org."""
		return BoneDict(
			main=[bone.name] + connected_children_names(self.obj, bone.name),
		)

	def initialize(self):
		"""Gather and validate data about the rig."""
		super().initialize()

		assert len(self.bones.org.main) >= self.params.CR_spine_length, f"Spine Length parameter value({self.params.CR_spine_length}) cannot exceed length of bone chain connected to {self.base_bone} ({len(self.bones.org.main)})"
		assert len(self.bones.org.main) > 2, "Spine must consist of at least 3 connected bones."

		self.display_scale *= 3

		self.ik_prop_name = "ik_spine"
		self.ik_stretch_name = "ik_stretch_spine"

	def get_segments(self, org_i, chain):
		"""Determine how many deform segments should be in a section of the chain."""
		segments = self.params.CR_deform_segments
		bbone_segments = self.params.CR_bbone_segments
		
		if (org_i == len(chain)-1):
			return (1, 1)
		
		return (segments, bbone_segments)

	@stage.prepare_bones
	def prepare_fk_spine(self):
		# Create Troso Master control
		self.mstr_torso = self.bone_infos.bone(
			name 					= "MSTR-Torso",
			source 					= self.org_chain[0],
			head 					= self.org_chain[0].center,
			# tail 					= self.org_chain[0].center + Vector((0, 0, self.scale)),
			custom_shape 			= self.load_widget("Torso_Master"),
			bone_group 				= 'Body: Main IK Controls',
		)

		# Create master (reverse) hip control
		self.mstr_hips = self.bone_infos.bone(
				name				= "MSTR-Hips",
				source				= self.org_chain[0],
				head				= self.org_chain[0].center,
				# tail 				= self.org_chain[0].center + Vector((0, 0, -self.scale)),
				custom_shape 		= self.load_widget("Hips"),
				custom_shape_scale 	= 0.7,
				parent				= self.mstr_torso,
				bone_group 			= "Body: Main IK Controls"
		)
		self.register_parent(self.mstr_torso, "Torso")
		self.mstr_torso.flatten()
		if self.params.CR_double_controls:
			double_mstr_pelvis = self.create_parent_bone(self.mstr_torso)
			double_mstr_pelvis.bone_group = 'Body: Main IK Controls Extra Parents'

		self.org_spines = self.org_chain[:self.params.CR_spine_length]
		self.org_necks = []
		self.org_head = None
		if len(self.org_chain) > self.params.CR_spine_length:	
			self.org_necks = self.org_chain[self.params.CR_spine_length:-1]
			self.org_head = self.org_chain[-1]

		# Create FK bones
		self.fk_chain = []
		fk_name = ""
		next_parent = self.mstr_torso
		for i, org_bone in enumerate(self.org_chain):
			fk_name = org_bone.name.replace("ORG", "FK")
			org_bone.fk_bone = fk_bone = self.bone_infos.bone(
				name				= fk_name,
				source				= org_bone,
				custom_shape 		= self.load_widget("FK_Limb"),
				custom_shape_scale 	= 0.9 * org_bone.custom_shape_scale,
				parent				= next_parent,
				bone_group = "Body: Main FK Controls"
			)
			next_parent = fk_bone

			self.fk_chain.append(fk_bone)

			if org_bone in self.org_spines:	# Spine section
				# Shift FK controls up to the center of their ORG bone
				org_bone = self.org_chain[i]
				fk_bone.put(org_bone.center)
				if i < len(self.org_spines)-1:
					fk_bone.tail = self.org_chain[i+1].center
				#fk_bone.flatten()

				# Create a child corrective - Everything that would normally be parented to this FK bone should actually be parented to this child bone.
				fk_child_bone = self.bone_infos.bone(
					name = fk_bone.name.replace("FK", "FK-C"),
					source = fk_bone,
					custom_shape = fk_bone.custom_shape,
					custom_shape_scale = fk_bone.custom_shape_scale * 0.9,
					bone_group = 'Body: FK Helper Bones',
					parent = fk_bone
				)
				# TODO: Add FK-C constraints (4 Transformation Constraints).
				next_parent = fk_child_bone
				fk_bone.fk_child = fk_child_bone
		
		# Head Hinge
		if self.org_head:
			self.hinge_setup(
				bone = self.fk_chain[-1], 
				category = "Head",
				parent_bone = self.fk_chain[-2],
				hng_name = self.fk_chain[-1].name.replace("FK", "FK-HNG"),
				prop_bone = self.prop_bone,
				prop_name = "fk_hinge_head",
				limb_name = "Head",
				default_value = 1.0,	# TODO: Delet this.
				head_tail = 1
			)

	@stage.prepare_bones
	def prepare_ik_spine(self):
		if not self.params.CR_create_ik_spine: return

		# Create master chest control
		self.mstr_chest = self.bone_infos.bone(
				name				= "MSTR-Chest", 
				source 				= self.org_spines[-2],
				head				= self.org_spines[-2].center,
				tail 				= self.org_spines[-2].center + Vector((0, 0, self.scale)),
				custom_shape 		= self.load_widget("Chest_Master"),
				custom_shape_scale 	= 0.7,
				parent				= self.mstr_torso,
				bone_group 			= "Body: Main IK Controls"
			)
		self.register_parent(self.mstr_chest, "Chest")

		if self.params.CR_double_controls:
			double_mstr_chest = self.create_parent_bone(self.mstr_chest)
			double_mstr_chest.bone_group = 'Body: Main IK Controls Extra Parents'
		
		self.mstr_hips.flatten()
		self.register_parent(self.mstr_hips, "Hips")

		self.ik_ctr_chain = []
		for i, org_spine in enumerate(self.org_spines):
			fk_bone = org_spine.fk_bone
			ik_ctr_name = fk_bone.name.replace("FK", "IK-CTR")	# Equivalent of IK-CTR bones in Rain (Technically animator-facing, but rarely used)
			ik_ctr_bone = self.bone_infos.bone(
				name				= ik_ctr_name, 
				source				= fk_bone,
				custom_shape 		= self.load_widget("Oval"),
				bone_group 			= "Body: IK - Secondary IK Controls"
			)
			if i >= len(self.org_spines)-2:	
				# Last two spine controls should be parented to the chest control.
				ik_ctr_bone.parent = self.mstr_chest
			else:
				# The rest to the torso root.
				ik_ctr_bone.parent = self.mstr_torso
			self.ik_ctr_chain.append(ik_ctr_bone)
		
		# Reverse IK (IK-R) chain. Damped track to IK-CTR of one lower index.
		next_parent = self.mstr_chest
		self.ik_r_chain = []
		for i, org_bone in enumerate(reversed(self.org_spines[1:])):	# We skip the first spine.
			fk_bone = org_bone.fk_bone
			index = len(self.org_spines)-i-2
			ik_r_name = fk_bone.name.replace("FK", "IK-R")
			org_bone.ik_r_bone = ik_r_bone = self.bone_infos.bone(
				name		= ik_r_name,
				source 		= fk_bone,
				tail 		= self.fk_chain[index].head.copy(),
				parent		= next_parent,
				bone_group = 'Body: IK-MCH - IK Mechanism Bones',
				hide_select	= self.mch_disable_select
			)
			next_parent = ik_r_bone
			self.ik_r_chain.append(ik_r_bone)
			ik_r_bone.add_constraint(self.obj, 'DAMPED_TRACK',
				subtarget = self.ik_ctr_chain[index].name
			)
		
		# IK chain
		next_parent = self.mstr_hips # First IK bone is parented to MSTR-Chest.
		self.ik_chain = []
		for i, org_bone in enumerate(self.org_spines):
			fk_bone = org_bone.fk_bone
			ik_name = fk_bone.name.replace("FK", "IK")
			org_bone.ik_bone = ik_bone = self.bone_infos.bone(
				name = ik_name,
				source = fk_bone,
				head = self.fk_chain[i-1].head.copy() if i>0 else self.def_bones[0].head.copy(),
				tail = fk_bone.head,
				parent = next_parent,
				bone_group = 'Body: IK-MCH - IK Mechanism Bones',
				hide_select	= self.mch_disable_select
			)
			self.ik_chain.append(ik_bone)
			next_parent = ik_bone
			
			damped_track_target = self.ik_r_chain[0].name
			if i > 0:
				if i != len(self.org_spines)-1:
					damped_track_target = self.org_spines[i+1].ik_r_bone.name
				influence_unit = 1 / (len(self.org_spines)-1)	# Minus three because there are no IK bones for the head and neck, and no stretchy constraint on the first IK spine bone. TODO: Allow arbitrary spine length.
				influence = influence_unit * i
				# IK Stretch Copy Location
				con_name = "Copy Location (Stretchy Spine)"
				ik_bone.add_constraint(self.obj, 'COPY_LOCATION', true_defaults=True,
					name = con_name,
					target = self.obj,
					subtarget = org_bone.ik_r_bone.name,
					head_tail = 1,
				)
				drv = Driver()
				drv.expression = "var * %f" %influence
				var = drv.make_var("var")
				var.type = 'SINGLE_PROP'
				var.targets[0].id_type='OBJECT'
				var.targets[0].id = self.obj
				var.targets[0].data_path = f'pose.bones["{self.prop_bone.name}"]["{self.ik_stretch_name}"]'

				data_path = f'constraints["{con_name}"].influence'
				ik_bone.drivers[data_path] = drv

				ik_bone.add_constraint(self.obj, 'COPY_ROTATION', true_defaults=True,
					target = self.obj,
					subtarget = self.ik_ctr_chain[i-1].name
				)
				self.ik_ctr_chain[i-1].custom_shape_transform = ik_bone
			
			head_tail = 1
			if i == len(self.org_spines)-1:
				# Special treatment for last IK bone...
				damped_track_target = self.ik_ctr_chain[-1].name
				head_tail = 0
				self.mstr_chest.custom_shape_transform = ik_bone
				if self.params.CR_double_controls:
					self.mstr_chest.parent.custom_shape_transform = ik_bone

			ik_bone.add_constraint(self.obj, 'DAMPED_TRACK',
				subtarget = damped_track_target,
				head_tail = head_tail
			)

		# Attach FK to IK
		for i, ik_bone in enumerate(self.ik_chain[1:]):
			fk_bone = self.fk_chain[i]
			con_name = "Copy Transforms IK"
			fk_bone.add_constraint(self.obj, 'COPY_TRANSFORMS', true_defaults=True,
				name = con_name,
				target = self.obj,
				subtarget = ik_bone.name
			)
			drv = Driver()
			drv.expression = "var"
			var = drv.make_var("var")
			var.type = 'SINGLE_PROP'
			var.targets[0].id_type='OBJECT'
			var.targets[0].id = self.obj
			var.targets[0].data_path = 'pose.bones["%s"]["%s"]' %(self.prop_bone.name, self.ik_prop_name)

			data_path = f'constraints["{con_name}"].influence'
			fk_bone.drivers[data_path] = drv
		
		# Store info for UI
		info = {
			"prop_bone"		: self.prop_bone.name,
			"prop_id" 		: self.ik_stretch_name,
		}
		self.add_ui_data("ik_stretches", "spine", "Spine", info, default=1.0)

		info = {
			"prop_bone"		: self.prop_bone.name,
			"prop_id"		: self.ik_prop_name,
		}
		self.add_ui_data("ik_switches", "spine", "Spine", info, default=0.0)

	@stage.prepare_bones
	def prepare_def_str_spine(self):
		# Tweak some display things
		for i, str_bone in enumerate(self.str_bones):
			str_bone.use_custom_shape_bone_size = False
			str_bone.custom_shape_scale = 0.15
		
		if len(self.org_necks) > 0:
			# If there are any neck bones, set the last one's easeout to 0.
			self.org_necks[-1].def_bone.bbone_easeout = 0

		# The last DEF bone should copy the scale of the FK bone. (Or maybe each of them should? And maybe all FK chains, not just the spine? TODO)
		last_def = self.def_bones[-1]
		# Nevermind, just inherit scale for now, it works nice when the neck STR scales the head in this case.
		last_def.inherit_scale = 'FULL'

	@stage.prepare_bones
	def prepare_org_spine(self):
		# Parent ORG to FK. This is only important because STR- bones are owned by ORG- bones.
		# We want each FK bone to control the STR- bone of one higher index, eg. FK-Spine0 would control STR-Spine1.
		for i, org_bone in enumerate(self.org_chain):
			if i == 0:
				# First STR bone should by owned by the hips.
				org_bone.parent = self.mstr_hips
			elif i > len(self.org_chain)-2:
				# Last two STR bones should both be owned by the last FK bone (usually the head)
				org_bone.parent = self.fk_chain[-1]
			elif hasattr(self.fk_chain[i-1], 'fk_child'):
				# Every other STR bone should be owned by the FK bone of one lower index.
				org_bone.parent = self.fk_chain[i-1].fk_child
			else:
				print("This shouldn't happen?")	# TODO This does happen
				org_bone.parent = self.fk_chain[i-1]
		
		# Change any ORG- children of the final spine bone to be owned by the neck bone instead. This is needed because of the index shift described above.
		new_parent = self.org_head
		if len(self.org_necks) > 0:
			new_parent = self.org_necks[0]
		if new_parent:
			for b in self.bone_infos.bones:
				if b.parent==self.org_spines[-1] and b.name.startswith("ORG-"):
					b.parent = new_parent

	##############################
	# Parameters

	@classmethod
	def add_parameters(cls, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		super().add_parameters(params)

		params.CR_show_spine_settings = BoolProperty(name="Spine Rig")
		params.CR_spine_length = IntProperty(
			name		 = "Spine Length"
			,description = "Number of bones on the chain until the spine ends and the neck begins. The spine and neck can both be made up of an arbitrary number of bones. The final bone of the chain is always treated as the head."
			,default	 = 3
			,min		 = 3
			,max		 = 99
		)
		params.CR_create_ik_spine = BoolProperty(
			name		 = "Create IK Setup"
			,description = "If disabled, this spine rig will only have FK controls"
			,default	 = True
		)
		params.CR_double_controls = BoolProperty(
			name		 = "Double Controls"
			,description = "Make duplicates of the main spine controls"
			,default	 = True
		)

	@classmethod
	def parameters_ui(cls, layout, params):
		"""Create the ui for the rig parameters."""
		super().parameters_ui(layout, params)

		icon = 'TRIA_DOWN' if params.CR_show_spine_settings else 'TRIA_RIGHT'
		layout.prop(params, "CR_show_spine_settings", toggle=True, icon=icon)
		if not params.CR_show_spine_settings: return
		
		layout.prop(params, "CR_spine_length")
		layout.prop(params, "CR_create_ik_spine")
		layout.prop(params, "CR_double_controls")

class Rig(CloudSpineRig):
	pass


def create_sample(obj):
    # generated by rigify.utils.write_metarig
    bpy.ops.object.mode_set(mode='EDIT')
    arm = obj.data

    bones = {}

    bone = arm.edit_bones.new('Spine')
    bone.head = 0.0000, 0.0018, 0.8211
    bone.tail = 0.0000, -0.0442, 1.0134
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
    bone = arm.edit_bones.new('RibCage')
    bone.head = 0.0000, -0.0442, 1.0134
    bone.tail = 0.0000, -0.0458, 1.1582
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
    bone.head = 0.0000, -0.0458, 1.1582
    bone.tail = 0.0000, -0.0148, 1.2805
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
    bone.head = 0.0000, -0.0148, 1.2805
    bone.tail = 0.0000, -0.0277, 1.3921
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
    bone.head = 0.0000, -0.0277, 1.3921
    bone.tail = 0.0000, -0.0528, 1.6157
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
        pbone.rigify_parameters.CR_double_controls = False
    except AttributeError:
        pass
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