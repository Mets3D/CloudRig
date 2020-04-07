import bpy
from bpy.props import BoolProperty, StringProperty, EnumProperty
from mathutils import Vector
from math import radians as rad

from rigify.base_rig import stage

from ..definitions.driver import Driver
from ..definitions.custom_props import CustomProp
from .cloud_ik_chain import CloudIKChainRig

class Rig(CloudIKChainRig):
	"""CloudRig arms and legs."""

	description = "IK chain with extras for specific limbs, such as foot roll."

	def initialize(self):
		super().initialize()
		"""Gather and validate data about the rig."""
		# Forced parameters
		self.params.CR_sharp_sections = True
		self.meta_base_bone.rigify_parameters.CR_sharp_sections = True

		# Safety checks
		self.limb_type = self.params.CR_limb_type
		if self.limb_type=='ARM':
			assert len(self.bones.org.main) == 3, "Arm chain must be exactly 3 connected bones."
		if self.limb_type=='LEG':
			assert len(self.bones.org.main) == 4, "Leg chain must be exactly 4 connected bones."

		# UI Strings and Custom Property names
		self.category = "arms" if self.limb_type == 'ARM' else "legs"
		if self.params.CR_use_custom_category_name:
			self.category = self.params.CR_custom_category_name

		self.limb_name = self.limb_type.capitalize()
		if self.params.CR_use_custom_limb_name:
			self.limb_name = self.params.CR_custom_limb_name
		
		self.limb_ui_name = self.side_prefix + " " + self.limb_name

		# IK values
		self.ik_pole_direction = 1 if self.limb_type=='ARM' else -1				#TODO: self.limb_type doesn't exist in cloud_ik_chain...
		if self.limb_type=='LEG':
			self.ik_pole_offset = 5
			self.pole_side = -1
		
		# List of parent candidate identifiers that this rig is looking for among its registered parent candidates
		self.ik_parents = ['Root', 'Torso']
		if self.limb_type == 'LEG':
			self.ik_parents.append('Hips')
		elif self.limb_type == 'ARM':
			self.ik_parents.append('Chest')
		self.ik_parents.append(self.limb_ui_name)

	# Overrides CloudChainRig.get_segments()
	def get_segments(self, org_i, chain):
		segments = self.params.CR_deform_segments
		bbone_segments = self.params.CR_bbone_segments
		
		if self.limb_type=='LEG' and org_i > len(chain)-3:
			# Force strictly 1 segment on the foot and the toe.
			return (1, self.params.CR_bbone_segments)
		elif self.limb_type=='ARM' and org_i == len(chain)-1:
			# Force strictly 1 segment and no BBone on the wrist.
			return (1, 1)
		
		return(segments, bbone_segments)

	@stage.prepare_bones
	def prepare_fk_limb(self):
		# NOTE: This runs after super().prepare_fk_chain().

		hng_child = self.fk_chain[0]	# For keeping track of which bone will need to be parented to the Hinge helper bone.
		for i, fk_bone in enumerate(self.fk_chain):
			if i == 0 and self.params.CR_double_first_control:
				# Make a parent for the first control.
				fk_parent_bone = self.create_parent_bone(fk_bone)
				fk_parent_bone.custom_shape = self.load_widget("FK_Limb")
				if self.params.CR_center_all_fk:
					self.create_dsp_bone(fk_parent_bone, center=True)
				hng_child = fk_parent_bone
			
			if i == 1:
				fk_bone.lock_rotation[1] = self.params.CR_limb_lock_yz
				fk_bone.lock_rotation[2] = self.params.CR_limb_lock_yz
			
			if i == 3 and self.limb_type=='LEG':
				self.fk_toe = fk_bone
		
		# Create Hinge helper
		self.hinge_setup(
			bone = hng_child, 
			category = self.category,
			parent_bone = self.limb_root_bone,
			hng_name = self.base_bone.replace("ORG", "FK-HNG"),
			prop_bone = self.prop_bone,
			prop_name = self.fk_hinge_name,
			limb_name = self.limb_ui_name
		)

	@stage.prepare_bones
	def prepare_str_limb(self):
		# We want to make some changes to the STR chain to make it behave more limb-like.
		
		# Disable first Copy Rotation constraint on the upperarm
		for b in self.main_str_bones[0].sub_bones:
			str_h_bone = b.parent
			if len(str_h_bone.constraints) < 3:
				# print(str_h_bone.name)
				continue
			str_h_bone.constraints[2][1]['mute'] = True	# TODO IMPORTANT: We have no proper way to access already existing constraints (by name, or even type) which is pretty sad. Instead of storing constraints as a (type, attribs) tuple, just store them as a dict, and initialize them a 'name' and 'type' attrib in add_constraint().

	@stage.prepare_bones
	def prepare_ik_limb(self):
		# NOTE: This runs after super().prepare_ik_chain()

		def foot_dsp(bone):
			# Create foot DSP helpers
			if self.limb_type=='LEG':
				dsp_bone = self.create_dsp_bone(bone)
				direction = 1 if self.side_suffix=='L' else -1
				projected_head = Vector((bone.head[0], bone.head[1], 0))
				projected_tail = Vector((bone.tail[0], bone.tail[1], 0))
				projected_center = projected_head + (projected_tail-projected_head) / 2
				dsp_bone.head = projected_center
				dsp_bone.tail = projected_center + Vector((0, -self.scale/10, 0))
				dsp_bone.roll = rad(90) * direction

		# Configure IK Master
		wgt_name = 'Hand_IK' if self.limb_type=='ARM' else 'Foot_IK'
		self.ik_mstr.custom_shape = self.load_widget(wgt_name)
		self.ik_mstr.custom_shape_scale = 0.8 if self.limb_type=='ARM' else 2.8

		foot_dsp(self.ik_mstr)
		# Parent control
		if self.params.CR_double_ik_control:
			double_control = self.create_parent_bone(self.ik_mstr)
			double_control.bone_group = 'Body: Main IK Controls Extra Parents'
			foot_dsp(double_control)

		# IK Foot setup, including Foot Roll
		if self.limb_type == 'LEG':
			self.prepare_ik_foot(self.ik_tgt_bone, self.ik_chain[-2:], self.org_chain[-2:])

		# Counter-Rotate setup for the first section of STR bones.
		for i in range(0, self.params.CR_deform_segments):
			factor_unit = 0.9 / self.params.CR_deform_segments
			factor = 0.9 - factor_unit * i
			self.first_str_counterrotate_setup(self.str_bones[i], self.org_chain[0], factor)

	def first_str_counterrotate_setup(self, str_bone, org_bone, factor):
		str_bone.add_constraint(self.obj, 'TRANSFORM',
			name = "Transformation (Counter-Rotate)",
			subtarget = org_bone.name,
			map_from = 'ROTATION', map_to = 'ROTATION',
			use_motion_extrapolate = True,
			from_min_y_rot =   -1, 
			from_max_y_rot =	1,
			to_min_y_rot   =  factor,
			to_max_y_rot   = -factor,
			from_rotation_mode = 'SWING_TWIST_Y'
		)

	def prepare_ik_foot(self, ik_tgt, ik_chain, org_chain):
		ik_foot = ik_chain[0]
		# TODO: This should be further split up into a separate function specifically for setting up foot roll, and one for the the rest(which I guess is setting up the toe Armature constraint)

		# Create ROLL control behind the foot (Limit Rotation, lock other transforms)
		if self.params.CR_use_foot_roll:	# TODO: Don't like this big if block. Maybe toe part should be moved out of this function, and the if check put before calling of this function, and then this function can be renamed to prepare_footroll.
			rolly_stretchy = self.bone_infos.bone(
				name = self.org_chain[0].name.replace("ORG", "IK-STR-ROLL"),
				source = self.org_chain[0],
				tail = self.ik_mstr.head.copy(),
				parent = self.limb_root_bone.name,
				bone_group = 'Body: IK-MCH - IK Mechanism Bones',
				hide_select = self.mch_disable_select
			)
			rolly_stretchy.scale_width(0.4)
			rolly_stretchy.add_constraint(self.obj, 'STRETCH_TO', subtarget=self.ik_chain[-2].name)

			sliced_name = self.slice_name(ik_foot.name)
			master_name = self.make_name(["ROLL", "MSTR"], sliced_name[1], sliced_name[2])
			roll_master = self.bone_infos.bone(
				name = master_name,
				source = self.ik_mstr,
				parent = self.ik_mstr,
				bone_group = 'Body: IK-MCH - IK Mechanism Bones'
			)
			roll_master.constraints.append(self.ik_tgt_bone.constraints[0])
			self.ik_tgt_bone.clear_constraints()

			# self.stretch_target_bone.parent = roll_master
			
			roll_name = self.make_name(["ROLL"], sliced_name[1], sliced_name[2])
			roll_ctrl = self.bone_infos.bone(
				name = roll_name,
				bbone_width = 1/18,
				head = ik_foot.head + Vector((0, self.scale, self.scale/4)),
				tail = ik_foot.head + Vector((0, self.scale/2, self.scale/4)),
				roll = rad(180),
				custom_shape = self.load_widget('FootRoll'),
				bone_group = 'Body: Main IK Controls',
				parent = roll_master
			)

			roll_ctrl.add_constraint(self.obj, 'LIMIT_ROTATION', 
				use_limit_x=True,
				min_x = rad(-90),
				max_x = rad(130),
				use_limit_y=True,
				use_limit_z=True,
				min_z = rad(-90),
				max_z = rad(90),
			)

			# Create bone to use as pivot point when rolling back. This is read from the metarig and should be placed at the heel of the shoe, pointing forward.
			ankle_pivot_name = self.params.CR_ankle_pivot_bone
			if ankle_pivot_name=="":
				ankle_pivot_name = "AnklePivot." + self.side_suffix
			meta_ankle_pivot = self.generator.metarig.data.bones.get(ankle_pivot_name)
			assert meta_ankle_pivot, f"ERROR: Could not find AnklePivot bone in the metarig: {ankle_pivot_name}."	# TODO IMPORTANT: This doesn't need to be an assert, just use the transforms of the foot org bone and create a new bone there! After that, we could remove the hardcoded default name of "AnklePivot.L/R".

			# I want to be able to customize the shape size of the foot controls from the metarig, via ankle pivot bone bbone scale.
			self.ik_mstr._bbone_x = meta_ankle_pivot.bbone_x
			self.ik_mstr._bbone_z = meta_ankle_pivot.bbone_z
			if self.params.CR_double_ik_control:
				self.ik_mstr.parent._bbone_x = meta_ankle_pivot.bbone_x
				self.ik_mstr.parent._bbone_z = meta_ankle_pivot.bbone_z

			ankle_pivot = self.bone_infos.bone(
				name = "IK-RollBack." + self.side_suffix,
				bbone_width = self.org_chain[-1].bbone_width,
				head = meta_ankle_pivot.head_local,
				tail = meta_ankle_pivot.tail_local,
				roll = rad(180),
				bone_group = 'Body: IK-MCH - IK Mechanism Bones',
				parent = roll_master,
				hide_select = self.mch_disable_select
			)

			ankle_pivot.add_constraint(self.obj, 'TRANSFORM',
				subtarget = roll_ctrl.name,
				map_from = 'ROTATION',
				map_to = 'ROTATION',
				from_min_x_rot = rad(-90),
				to_min_x_rot = rad(-60),
			)
			
			# Create reverse bones
			# TODO: Does this really need to be a loop? We are just dealing with a foot and a toe, never anything more.
			rik_chain = []
			for i, b in reversed(list(enumerate(org_chain))):
				rik_bone = self.bone_infos.bone(
					name = b.name.replace("ORG", "RIK"),
					source = b,
					head = b.tail.copy(),
					tail = b.head.copy(),
					roll = 0,
					parent = ankle_pivot,
					bone_group = 'Body: IK-MCH - IK Mechanism Bones',
					hide_select = self.mch_disable_select
				)
				rik_chain.append(rik_bone)
				ik_chain[i].parent = rik_bone

				if i == 1:
					rik_bone.add_constraint(self.obj, 'TRANSFORM',
						subtarget = roll_ctrl.name,
						map_from = 'ROTATION',
						map_to = 'ROTATION',
						from_min_x_rot = rad(90),
						from_max_x_rot = rad(166),
						to_min_x_rot   = rad(0),
						to_max_x_rot   = rad(169),
						from_min_z_rot = rad(-60),
						from_max_z_rot = rad(60),
						to_min_z_rot   = rad(10),
						to_max_z_rot   = rad(-10)
					)
				
				if i == 0:
					rik_bone.add_constraint(self.obj, 'COPY_LOCATION',
						true_defaults = True,
						target = self.obj,
						subtarget = rik_chain[-2].name,
						head_tail = 1,
					)

					rik_bone.add_constraint(self.obj, 'TRANSFORM',
						name = "Transformation Roll",
						subtarget = roll_ctrl.name,
						map_from = 'ROTATION',
						map_to = 'ROTATION',
						from_min_x_rot = rad(0),
						from_max_x_rot = rad(135),
						to_min_x_rot   = rad(0),
						to_max_x_rot   = rad(118),
						from_min_z_rot = rad(-45),
						from_max_z_rot = rad(45),
						to_min_z_rot   = rad(25),
						to_max_z_rot   = rad(-25)
					)
					rik_bone.add_constraint(self.obj, 'TRANSFORM',
						name = "Transformation CounterRoll",
						subtarget = roll_ctrl.name,
						map_from = 'ROTATION',
						map_to = 'ROTATION',
						from_min_x_rot = rad(90),
						from_max_x_rot = rad(135),
						to_min_x_rot   = rad(0),
						to_max_x_rot   = rad(-31.8)
					)
				
			# Change the subtarget of the constraints on main_str_bones from the old stretchy bone to the new one, that accounts for footroll.
			for main_str_bone in self.main_str_bones:
				for c in main_str_bone.parent.constraints:
					if c[1]['name'] == 'CopyLoc_IK_Stretch':
						c[1]['subtarget'] = rolly_stretchy.name
						print(f"constraint set to {rolly_stretchy.name}")

		# FK Toe bone should be parented between FK Foot and IK Toe.
		fk_toe = self.fk_toe
		fk_toe.parent = None
		fk_toe.add_constraint(self.obj, 'ARMATURE',
			targets = [
				{
					"subtarget" : self.fk_chain[-2].name	# FK Foot
				},
				{
					"subtarget" : ik_chain[-1].name		# IK Toe
				}
			],
		)

		drv1 = Driver()
		drv1.expression = "1-ik"
		var1 = drv1.make_var("ik")
		var1.type = 'SINGLE_PROP'
		var1.targets[0].id_type='OBJECT'
		var1.targets[0].id = self.obj
		var1.targets[0].data_path = f'pose.bones["{self.prop_bone.name}"]["{self.ikfk_name}"]'

		drv2 = drv1.clone()
		drv2.expression = "ik"

		data_path1 = 'constraints["Armature"].targets[0].weight'
		data_path2 = 'constraints["Armature"].targets[1].weight'
		
		fk_toe.drivers[data_path1] = drv1
		fk_toe.drivers[data_path2] = drv2

	def prepare_parent_switch(self, ik_ctrl):
		return

	@stage.prepare_bones
	def foot_org_tweak(self):
		# Delete IK constraint and driver from toe bone. It should always use FK.
		if self.limb_type == 'LEG':
			org_toe = self.org_chain[-1]
			org_toe.constraints.pop()
			org_toe.drivers = {}

	@stage.prepare_bones
	def prepare_parent_switch_with_double_control(self):
		ik_ctrl = self.ik_mstr
		if self.params.CR_double_ik_control:
			ik_ctrl = ik_ctrl.parent

		super().prepare_parent_switch(ik_ctrl)

	##############################
	# Parameters

	@classmethod
	def add_parameters(cls, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		super().add_parameters(params)

		params.CR_show_limb_settings = BoolProperty(name="Limb Rig")

		params.CR_limb_type = EnumProperty(
			 name 		 = "Type"
			,items 		 = (
				("ARM", "Arm", "Arm (Chain of 3)"),
				("LEG", "Leg", "Leg (Chain of 5, includes foot rig)"),
			)
			,default	 = 'ARM'
		)
		params.CR_double_first_control = BoolProperty(
			 name		 = "Double First FK"
			,description = "The first FK control has a parent control. Having two controls for the same thing can help avoid interpolation issues when the common pose in animation is far from the rest pose"
			,default	 = True
		)
		params.CR_double_ik_control = BoolProperty(
			 name		 = "Double IK Master"
			,description = "The IK control has a parent control. Having two controls for the same thing can help avoid interpolation issues when the common pose in animation is far from the rest pose"
			,default	 = True
		)

		params.CR_limb_lock_yz = BoolProperty(
			 name		 = "Lock Elbow/Shin YZ"
			,description = "Lock Y and Z rotation of the elbow/shin"
			,default 	 = False
		)
		params.CR_use_foot_roll = BoolProperty(
			 name 		 = "Foot Roll"
			,description = "Create Foot roll controls"
			,default 	 = True
		)
		params.CR_ankle_pivot_bone = StringProperty(
			 name		 = "Ankle Pivot Bone"
			,description = "Bone to use as the ankle pivot. This bone should be placed at the heel of the shoe, pointing forward. If unspecified, default to a bone called AnklePivot.L/.R"
			,default	 = ""
		)

	@classmethod
	def parameters_ui(cls, layout, params):
		"""Create the ui for the rig parameters."""
		ui_rows = super().parameters_ui(layout, params)
		if 'sharp_sections' in ui_rows:
			ui_rows['sharp_sections'].enabled = False

		icon = 'TRIA_DOWN' if params.CR_show_limb_settings else 'TRIA_RIGHT'
		layout.prop(params, "CR_show_limb_settings", toggle=True, icon=icon)
		if not params.CR_show_limb_settings: return ui_rows

		layout.prop(params, "CR_limb_type")
		if params.CR_limb_type=='LEG':
			footroll_row = layout.row()
			footroll_row.prop(params, "CR_use_foot_roll")
			if params.CR_use_foot_roll:
				footroll_row.prop_search(params, "CR_ankle_pivot_bone", bpy.context.object.data, "bones", text="Ankle Pivot")

		double_row = layout.row()
		double_row.prop(params, "CR_double_ik_control")
		double_row.prop(params, "CR_double_first_control")


		word = "Elbow" if params.CR_limb_type == 'ARM' else "Shin"
		layout.prop(params, "CR_limb_lock_yz", text=f"Lock {word} Y/Z")

def create_sample(obj):
    # generated by rigify.utils.write_metarig
    bpy.ops.object.mode_set(mode='EDIT')
    arm = obj.data

    bones = {}

    bone = arm.edit_bones.new('Thigh.L')
    bone.head = 0.0816, -0.0215, 0.8559
    bone.tail = 0.0756, -0.0246, 0.4856
    bone.roll = 0.0164
    bone.use_connect = False
    bone.bbone_x = 0.0185
    bone.bbone_z = 0.0185
    bone.head_radius = 0.0279
    bone.tail_radius = 0.0239
    bone.envelope_distance = 0.0475
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bones['Thigh.L'] = bone.name
    bone = arm.edit_bones.new('UpperArm.L')
    bone.head = 0.1131, 0.0042, 1.2508
    bone.tail = 0.3176, 0.0138, 1.2407
    bone.roll = -1.5214
    bone.use_connect = False
    bone.bbone_x = 0.0121
    bone.bbone_z = 0.0121
    bone.head_radius = 0.0133
    bone.tail_radius = 0.0112
    bone.envelope_distance = 0.0448
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bones['UpperArm.L'] = bone.name
    bone = arm.edit_bones.new('Knee.L')
    bone.head = 0.0756, -0.0246, 0.4856
    bone.tail = 0.0657, -0.0042, 0.0775
    bone.roll = 0.0241
    bone.use_connect = True
    bone.bbone_x = 0.0163
    bone.bbone_z = 0.0163
    bone.head_radius = 0.0239
    bone.tail_radius = 0.0186
    bone.envelope_distance = 0.0412
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bone.parent = arm.edit_bones[bones['Thigh.L']]
    bones['Knee.L'] = bone.name
    bone = arm.edit_bones.new('Forearm.L')
    bone.head = 0.3176, 0.0138, 1.2407
    bone.tail = 0.5288, -0.0125, 1.2312
    bone.roll = -1.5260
    bone.use_connect = True
    bone.bbone_x = 0.0107
    bone.bbone_z = 0.0107
    bone.head_radius = 0.0112
    bone.tail_radius = 0.0132
    bone.envelope_distance = 0.0526
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bone.parent = arm.edit_bones[bones['UpperArm.L']]
    bones['Forearm.L'] = bone.name
    bone = arm.edit_bones.new('Foot.L')
    bone.head = 0.0657, -0.0042, 0.0775
    bone.tail = 0.0689, -0.1086, 0.0249
    bone.roll = -0.0592
    bone.use_connect = True
    bone.bbone_x = 0.0155
    bone.bbone_z = 0.0155
    bone.head_radius = 0.0186
    bone.tail_radius = 0.0162
    bone.envelope_distance = 0.0342
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bone.parent = arm.edit_bones[bones['Knee.L']]
    bones['Foot.L'] = bone.name
    bone = arm.edit_bones.new('Wrist.L')
    bone.head = 0.5288, -0.0125, 1.2312
    bone.tail = 0.5842, -0.0197, 1.2286
    bone.roll = -1.5240
    bone.use_connect = True
    bone.bbone_x = 0.0139
    bone.bbone_z = 0.0139
    bone.head_radius = 0.0132
    bone.tail_radius = 0.0056
    bone.envelope_distance = 0.0222
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bone.parent = arm.edit_bones[bones['Forearm.L']]
    bones['Wrist.L'] = bone.name
    bone = arm.edit_bones.new('Toes.L')
    bone.head = 0.0689, -0.1086, 0.0249
    bone.tail = 0.0697, -0.1838, 0.0046
    bone.roll = -0.0402
    bone.use_connect = True
    bone.bbone_x = 0.0103
    bone.bbone_z = 0.0103
    bone.head_radius = 0.0162
    bone.tail_radius = 0.0083
    bone.envelope_distance = 0.0332
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bone.parent = arm.edit_bones[bones['Foot.L']]
    bones['Toes.L'] = bone.name
    bone = arm.edit_bones.new('AnklePivot.L')
    bone.head = 0.0657, 0.0495, 0.0213
    bone.tail = 0.0672, -0.0040, 0.0213
    bone.roll = 0.0000
    bone.use_connect = False
    bone.bbone_x = 0.0108
    bone.bbone_z = 0.0108
    bone.head_radius = 0.0085
    bone.tail_radius = 0.0034
    bone.envelope_distance = 0.0085
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bone.parent = arm.edit_bones[bones['Foot.L']]
    bones['AnklePivot.L'] = bone.name

    bpy.ops.object.mode_set(mode='OBJECT')
    pbone = obj.pose.bones[bones['Thigh.L']]
    pbone.rigify_type = 'cloud_limbs'
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    try:
        pbone.rigify_parameters.rotation_axis = "automatic"
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_limb_type = "LEG"
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_center_all_fk = True
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_use_custom_limb_name = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_limb_lock_yz = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_custom_limb_name = "Leg"
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_use_custom_category_name = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_double_first_control = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_double_ik_control = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_custom_category_name = "legs"
    except AttributeError:
        pass
    pbone = obj.pose.bones[bones['UpperArm.L']]
    pbone.rigify_type = 'cloud_limbs'
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    try:
        pbone.rigify_parameters.CR_double_first_control = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_double_ik_control = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_use_custom_category_name = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_use_custom_limb_name = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_cap_control = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_center_all_fk = True
    except AttributeError:
        pass

    pbone = obj.pose.bones[bones['Knee.L']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['Forearm.L']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['Foot.L']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['Wrist.L']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['Toes.L']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['AnklePivot.L']]
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