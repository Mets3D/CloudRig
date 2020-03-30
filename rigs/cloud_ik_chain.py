import bpy
from bpy.props import BoolProperty, StringProperty, FloatProperty, IntProperty
from mathutils import Vector
from math import radians as rad

from rigify.base_rig import stage

from ..definitions.driver import Driver
from .cloud_fk_chain import CloudFKChainRig

#TODO: There's some code in limb that makes the last def- bone has bbone_easeout=0. That should be in here, under a parameter, that's greyed out when ik_tail or whatever it will be called, would be enabled. Maybe.
class CloudIKChainRig(CloudFKChainRig):
	"""CloudRig IK chain."""

	description = "IK chain with stretchy IK and IK/FK snapping. Pole control optional."

	def initialize(self):
		"""Gather and validate data about the rig."""
		super().initialize()

		assert self.params.CR_ik_length <= len(self.bones.org.main), f"IK Length parameter ({self.params.CR_ik_length}) higher than number of bones in the connected chain ({len(self.bones.org.main)}) on rig: {self.meta_base_bone.name}"

		# UI Strings and Custom Property names
		self.category = self.slice_name(self.base_bone)[1]
		if self.params.CR_use_custom_category_name:
			self.category = self.params.CR_custom_category_name

		self.limb_name = self.category						# Name used for naming bones. Should not contain a side identifier like .L/.R.
		if self.params.CR_use_custom_limb_name:
			self.limb_name = self.params.CR_custom_limb_name
		
		self.limb_ui_name = self.side_prefix + " " + self.limb_name	# Name used for UI related things. Should contain the side identifier.

		self.limb_name_props = self.limb_ui_name.replace(" ", "_").lower()
		self.ikfk_name = "ik_" + self.limb_name_props
		self.ik_stretch_name = "ik_stretch_" + self.limb_name_props
		self.fk_hinge_name = "fk_hinge_" + self.limb_name_props

		self.ik_pole_direction = 1 	# TODO: Calculate based on org chain's curvature!
		self.ik_pole_offset = 3		# Scalar on distance from the body.

	@stage.prepare_bones
	def prepare_root_bone(self):
		# Socket/Root bone to parent IK and FK to.
		root_name = self.base_bone.replace("ORG", "ROOT")
		base_bone = self.get_bone(self.base_bone)
		self.limb_root_bone = self.bone_infos.bone(
			name 				= root_name, 
			source 				= base_bone, 
			parent 				= self.bones.parent,
			custom_shape 		= self.load_widget("Cube"),
			custom_shape_scale 	= 0.5,
			bone_group			= 'Body: IK-MCH - IK Mechanism Bones'
		)
		self.register_parent(self.limb_root_bone, self.limb_ui_name)
	
	def make_pole_control(self, org_chain):
		# Create IK Pole Control
		first_bone = org_chain[0]
		elbow = first_bone.tail.copy()	# Starting point for the location of the pole target. TODO: This is no good when IK length > 2.
		offset_y = self.ik_pole_direction * self.ik_pole_offset * self.scale * self.params.CR_ik_limb_pole_offset	# Because of this code simplification, the character must face +Y axis.
		offset = Vector((0, offset_y, 0))
		pole_ctrl = self.pole_ctrl = self.bone_infos.bone(
			name = self.make_name(["IK", "POLE"], self.limb_name, [self.side_suffix]),
			bbone_width = 0.1,
			head = elbow + offset,
			tail = elbow + offset*1.1,
			roll = 0,
			custom_shape = self.load_widget('ArrowHead'),
			custom_shape_scale = 0.5,
			bone_group = 'Body: Main IK Controls',
		)
		pole_ctrl.head = pole_ctrl.head.copy()
		pole_ctrl.tail = pole_ctrl.tail.copy()

		pole_line = self.bone_infos.bone(
			name = self.make_name(["IK", "POLE", "LINE"], self.limb_name, [self.side_suffix]),
			source = pole_ctrl,
			tail = elbow,
			custom_shape = self.load_widget('Pole_Line'),
			use_custom_shape_bone_size = True,
			parent = pole_ctrl,
			bone_group = 'Body: Main IK Controls',
			hide_select = True
		)
		pole_line.add_constraint(self.obj, 'STRETCH_TO', 
			subtarget = first_bone.name, 
			head_tail = 1,
		)
		# Add a driver to the Line's hide property so it's hidden exactly when the pole target is hidden.
		drv = Driver()
		var = drv.make_var("var")
		var.type = 'SINGLE_PROP'
		var.targets[0].id_type = 'ARMATURE'
		var.targets[0].id = self.obj.data
		var.targets[0].data_path = 'bones["%s"].hide' %pole_ctrl.name

		pole_line.bone_drivers['hide'] = drv
		
		self.create_dsp_bone(pole_ctrl)
		return pole_ctrl
	
	def add_ui_data_ik_fk(self, fk_chain, ik_chain, ik_pole):
		""" Prepare the data needed to be stored on the armature object for IK/FK snapping. """
		fk_chain = fk_chain[:self.params.CR_ik_length]
		ik_chain = ik_chain[:self.params.CR_ik_length]

		info = {	# These parameter names must be kept in sync with Snap_IK2FK in cloudrig.py
			"operator"				: "armature.ikfk_toggle",
			"prop_bone"				: self.prop_bone.name,
			"prop_id"				: self.ikfk_name,
			"fk_chain"				: [b.name for b in fk_chain],
			"ik_chain"				: [b.name for b in ik_chain],
			"str_chain"				: [b.name for b in self.main_str_bones],
			"double_first_control"	: self.params.CR_double_first_control,
			"double_ik_control"		: self.params.CR_double_ik_control,
			"ik_pole"				: self.pole_ctrl.name if self.pole_ctrl else "",
			"ik_control"			: self.ik_mstr.name
		}
		default = 1.0
		if hasattr(self, "limb_type") and self.limb_type=='ARM':
			default = 0.0	# TODO: delet this.
		self.add_ui_data("ik_switches", self.category, self.limb_ui_name, info, default=default)

	def make_ik_chain(self, org_chain, ik_mstr, pole_target, ik_pole_direction=0):
		""" Based on a chain of ORG bones, create an IK chain, optionally with a pole target."""
		ik_chain = []
		for i, org_bone in enumerate(org_chain):
			# org_bone = self.get_bone(bn)
			ik_name = org_bone.name.replace("ORG", "IK")
			ik_bone = self.bone_infos.bone(ik_name, org_bone,
				bone_group = 'Body: IK-MCH - IK Mechanism Bones',
				hide_select = self.mch_disable_select
			)
			ik_chain.append(ik_bone)
			
			if i == 0:
				# Parent first bone to the limb root
				ik_bone.parent = self.limb_root_bone.name
				if not self.params.CR_use_pole_target:
					ik_bone.custom_shape = self.load_widget("IK_Base")
					ik_bone.use_custom_shape_bone_size = True
					ik_bone.custom_shape_scale = 0.8
					ik_bone.bone_group = 'Body: Main IK Controls'

			else:
				ik_bone.parent = ik_chain[-2]
			
			if i == self.params.CR_ik_length-1:
				# Add the IK constraint to the previous bone, targetting this one.
				pole_target_name = pole_target.name if pole_target else ""
				ik_chain[self.params.CR_ik_length-2].add_constraint(self.obj, 'IK', 
					pole_target		= self.obj if pole_target_name!="" else None,
					pole_subtarget	= pole_target_name,
					pole_angle		= ik_pole_direction * rad(90),
					subtarget		= ik_bone.name,
					chain_count		= self.params.CR_ik_length-1
				)
				# Parent this one to the IK master.
				ik_bone.parent = ik_mstr
		
		# Add IK/FK Snapping to the UI.
		self.add_ui_data_ik_fk(self.fk_chain, ik_chain, pole_target)
		return ik_chain

	def setup_ik_stretch(self):
		ik_org_bone = self.org_chain[self.params.CR_ik_length-1]
		str_name = ik_org_bone.name.replace("ORG", "IK-STR")
		stretch_bone = self.bone_infos.bone(
			name = str_name, 
			source = self.org_chain[0],
			tail = self.ik_mstr.head.copy(),
			parent = self.limb_root_bone.name,
			bone_group = 'Body: IK-MCH - IK Mechanism Bones',
			hide_select = self.mch_disable_select
		)
		stretch_bone.scale_width(0.4)
		
		# Bone responsible for giving stretch_bone the target position to stretch to.
		self.stretch_target_bone = self.bone_infos.bone(
			name = ik_org_bone.name.replace("ORG", "IK-STR-TGT"), 
			source = ik_org_bone, 
			parent = self.ik_mstr,
			bone_group = 'Body: IK-MCH - IK Mechanism Bones',
			hide_select = self.mch_disable_select
		)
		
		chain_length = 0
		for ikb in self.ik_chain[:-1]:	# TODO: Support IK at tail of chain.
			chain_length += ikb.length

		length_factor = chain_length / stretch_bone.length
		stretch_bone.add_constraint(self.obj, 'STRETCH_TO', subtarget=self.stretch_target_bone.name)
		stretch_bone.add_constraint(self.obj, 'LIMIT_SCALE', 
			use_max_y = True,
			max_y = length_factor,
			influence = 0
		)

		str_drv = Driver()
		str_drv.expression = "1-stretch"
		var = str_drv.make_var("stretch")
		var.type = 'SINGLE_PROP'
		var.targets[0].id_type = 'OBJECT'
		var.targets[0].id = self.obj
		var.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (self.prop_bone.name, self.ik_stretch_name)

		data_path = 'constraints["Limit Scale"].influence'
		
		stretch_bone.drivers[data_path] = str_drv

		# Store info for UI
		info = {
			"prop_bone"			: self.prop_bone.name,
			"prop_id" 			: self.ik_stretch_name,
		}
		self.add_ui_data("ik_stretches", self.category, self.limb_ui_name, info, default=1.0)

		# Bone responsible for keeping track of where the IK master IS (ie, IK master is parented to this bone). Foot Roll could be parented to this, and then the IK bone gets parented to the foot roll.
		self.ik_tgt_bone = self.bone_infos.bone(
			name = ik_org_bone.name.replace("ORG", "IK-TGT"),
			source = ik_org_bone,
			bone_group = 'Body: IK-MCH - IK Mechanism Bones',
			parent = self.ik_mstr,
			hide_select = self.mch_disable_select
		)
		self.ik_tgt_bone.add_constraint(self.obj, 'COPY_LOCATION',
			true_defaults = True,
			target = self.obj,
			subtarget = stretch_bone.name,
			head_tail = 1
		)
		
		ik_bone = self.ik_chain[self.params.CR_ik_length-1]
		ik_bone.parent = self.ik_tgt_bone

		# Create Helpers for main STR bones so they will stick to the stretchy bone.
		self.main_str_transform_setup(stretch_bone, chain_length)

	def main_str_transform_setup(self, stretch_bone, chain_length):
		""" Set up transformation constraint to mid-limb STR bone that ensures that it stays in between the root of the limb and the IK master control during IK stretching. """
		# TODO IMPORTANT: This should be reworked, such that main_str_bones also have an STR-H bone that they are parented to. The STR-H bone has a Copy Transforms constraint to the stretch mechanism helper(the long bone going across the entire chain) which fully activates instantly using a driver, as soon as stretching begins(same check as current, but two checks rolled into one now: whether stretching is enabled and whether the distance to the arm is longer than max)
		# This would allow arbitrary number of bones in a limb, and not have funny results when local Y axis isn't perfectly ideal(which is what we're relying on atm)
		# But this does rely on finding the head_tail value for the copy transforms constraint appropriately - but that shouldn't be too hard.

		cum_length = self.org_chain[0].length
		for i, main_str_bone in enumerate(self.main_str_bones):
			if i == 0: continue
			if i == len(self.main_str_bones)-1: continue
			main_str_helper = self.bone_infos.bone(
				name = main_str_bone.name.replace("STR-", "STR-S-"),
				source = main_str_bone,
				bbone_width = 1/10,
				bone_group = 'Body: STR-H - Stretch Helpers',
				parent = main_str_bone.parent,
				hide_select = self.mch_disable_select
			)
			main_str_bone.parent = main_str_helper

			con_name = 'CopyLoc_IK_Stretch'
			main_str_helper.add_constraint(self.obj, 'COPY_LOCATION',
				true_defaults	= True,
				target			= self.obj,
				subtarget		= stretch_bone.name,
				name			= con_name,
				head_tail		= cum_length/chain_length	# How far this bone is along the total chain length
			)
			cum_length += self.org_chain[i].length

			stretchy_drv = Driver()		# Influence driver
			stretchy_drv.expression = f"ik * stretch * (distance > {chain_length} * scale)"
			var_stretch = stretchy_drv.make_var("stretch")
			var_stretch.type = 'SINGLE_PROP'
			var_stretch.targets[0].id_type = 'OBJECT'
			var_stretch.targets[0].id = self.obj
			var_stretch.targets[0].data_path = f'pose.bones["{self.prop_bone.name}"]["{self.ik_stretch_name}"]'

			var_ik = stretchy_drv.make_var("ik")
			var_ik.type = 'SINGLE_PROP'
			var_ik.targets[0].id_type = 'OBJECT'
			var_ik.targets[0].id = self.obj
			var_ik.targets[0].data_path = f'pose.bones["{self.prop_bone.name}"]["{self.ikfk_name}"]'

			var_dist = stretchy_drv.make_var("distance")
			var_dist.type = 'LOC_DIFF'
			var_dist.targets[0].id = self.obj
			var_dist.targets[0].bone_target = self.ik_tgt_bone.name
			var_dist.targets[0].transform_space = 'WORLD_SPACE'
			var_dist.targets[1].id = self.obj
			var_dist.targets[1].bone_target = self.ik_chain[0].name
			var_dist.targets[1].transform_space = 'WORLD_SPACE'

			var_scale = stretchy_drv.make_var("scale")
			var_scale.type = 'TRANSFORMS'
			var_scale.targets[0].id = self.obj
			var_scale.targets[0].transform_type = 'SCALE_Y'
			var_scale.targets[0].transform_space = 'WORLD_SPACE'
			var_scale.targets[0].bone_target = self.ik_chain[0].name

			data_path = f'constraints["{con_name}"].influence'

			main_str_helper.drivers[data_path] = stretchy_drv

	@stage.prepare_bones
	def prepare_ik_chain(self):
		# Create IK Master control
		ik_org_bone = self.org_chain[self.params.CR_ik_length-1]
		mstr_name = ik_org_bone.name.replace("ORG", "IK-MSTR")
		self.ik_mstr = self.bone_infos.bone(
			name = mstr_name,
			source = self.org_chain[self.params.CR_ik_length-1],
			custom_shape = self.load_widget("Sphere"),
			parent = None,
			bone_group = 'Body: Main IK Controls'
		)

		# Create Pole control
		self.pole_ctrl = None
		if self.params.CR_use_pole_target:
			self.pole_ctrl = self.make_pole_control(self.org_chain)
			# Add aim constraint to pole display bone
			self.pole_ctrl.dsp_bone.add_constraint(self.obj, 'DAMPED_TRACK', 
				subtarget = self.main_str_bones[1].name, # TODO: This should be something else, maybe... But hard to make it any more accurate without causing a dependency cycle.
				head_tail=1, 
				track_axis='TRACK_NEGATIVE_Y'
			)

		# Create IK Chain
		self.ik_chain = self.make_ik_chain(self.org_chain, self.ik_mstr, self.pole_ctrl, self.ik_pole_direction)

		if self.params.CR_world_aligned_controls:
			self.ik_mstr.flatten()

		# Set up IK Stretch
		self.setup_ik_stretch()
	
	@stage.prepare_bones
	def prepare_org_limb(self):
		# Note: Runs after prepare_org_chain().
		
		# Add Copy Transforms constraints to the ORG bones to copy the IK bones.
		# Put driver on the influence to be able to disable IK.

		for i, org_bone in enumerate(self.org_chain):
			ik_bone = self.bone_infos.find(org_bone.name.replace("ORG", "IK"))
			ik_ct_name = "Copy Transforms IK"
			ik_con = org_bone.add_constraint(self.obj, 'COPY_TRANSFORMS', 
				true_defaults = True,
				target		  = self.obj,
				subtarget	  = ik_bone.name,
				name		  = ik_ct_name
			)

			drv = Driver()
			var = drv.make_var()
			var.targets[0].id = self.obj
			var.targets[0].data_path = 'pose.bones["%s"]["%s"]' %(self.prop_bone.name, self.ikfk_name)

			data_path = 'constraints["%s"].influence' %(ik_ct_name)
			org_bone.drivers[data_path] = drv

	##############################
	# Parameters
	
	@classmethod
	def add_parameters(cls, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		super().add_parameters(params)

		params.CR_show_ik_settings = BoolProperty(name="IK Rig")
		# TODO: Parameter to let the IK control be at the tip of the last bone instead of at the last bone itself. Would be useful for fingers.
		params.CR_use_custom_limb_name = BoolProperty(
			 name		 = "Custom Limb Name"
			,description = 'Specify a name for this limb - There can be exactly two limbs with the same name, a Left and a Right one. This name should NOT include a side indicator such as "Left" or "Right". Limbs with the same name will be displayed on the same row'
			,default 	 = False
		)
		params.CR_custom_limb_name = StringProperty(default="Arm")
		params.CR_use_custom_category_name = BoolProperty(
			 name		 = "Custom Category Name"
			,description = "Specify a category for this limb. Limbs in the same category will have their settings displayed in the same column"
			,default	 = False,
		)
		params.CR_custom_category_name = StringProperty(default="arms")

		params.CR_ik_limb_pole_offset = FloatProperty(	# TODO: Rename to ik_pole_offset - Also, maybe this is redundant.
			 name	 	 = "Pole Vector Offset"
			,description = "Push the pole target closer to or further away from the chain"
			,default 	 = 1.0
		)
		params.CR_world_aligned_controls = BoolProperty(
			 name		 = "World Aligned Control"
			,description = "Ankle/Wrist IK/FK controls are aligned with world axes"
			,default	 = True
		)
		params.CR_ik_length = IntProperty(
			name	 	 = "IK Length"
			,description = "Length of the IK chain. Cannot be higher than the number of bones in the chain"
			,default	 = 3
			,min		 = 1
			,max		 = 255
		)
		params.CR_use_pole_target = BoolProperty(
			name 		 = "Use Pole Target"
			,description = "If disabled, you can control the rotation of the IK chain by simply rotating its first bone, rather than with an IK pole control"
			,default	 = True
		)
		#TODO: Implement this.
		params.CR_custom_pole_bone = StringProperty(
			name 		 = "Custom Pole Position"
			,description = "When chosen, use this bone's position for the IK pole target, instead of determining it automatically"
			,default	 = ""
		)

	@classmethod
	def parameters_ui(cls, layout, params):
		""" Create the ui for the rig parameters.
		"""
		ui_rows = super().parameters_ui(layout, params)

		icon = 'TRIA_DOWN' if params.CR_show_ik_settings else 'TRIA_RIGHT'
		layout.prop(params, "CR_show_ik_settings", toggle=True, icon=icon)
		if not params.CR_show_ik_settings: return ui_rows

		name_row = layout.row()
		limb_column = name_row.column()
		limb_column.prop(params, "CR_use_custom_limb_name")
		if params.CR_use_custom_limb_name:
			limb_column.prop(params, "CR_custom_limb_name", text="")
		category_column = name_row.column()
		category_column.prop(params, "CR_use_custom_category_name")
		if params.CR_use_custom_category_name:
			category_column.prop(params, "CR_custom_category_name", text="")

		pole_row = layout.row()
		pole_row.prop(params, "CR_use_pole_target")
		if params.CR_use_pole_target:
			pole_row.prop_search(params, "CR_custom_pole_bone", bpy.context.object.data, "bones", text="Position")
		layout.prop(params, "CR_ik_length")
		layout.prop(params, "CR_world_aligned_controls")
		# layout.prop(params, "CR_ik_limb_pole_offset")

		return ui_rows

class Rig(CloudIKChainRig):
	pass