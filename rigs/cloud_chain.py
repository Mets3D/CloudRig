import bpy
from bpy.props import BoolProperty, IntProperty
from mathutils import Vector

from rigify.base_rig import stage

from ..definitions.driver import Driver
from .cloud_utils import make_name, slice_name
from .cloud_base import CloudBaseRig

class CloudChainRig(CloudBaseRig):
	"""CloudRig stretchy BBone chain."""

	description = "Stretchy chain for pure squash and stretch."

	def ensure_bone_groups(self):
		""" Ensure bone groups that this rig needs. """
		super().ensure_bone_groups()
		# print("cloud_chain ensure_bone_groups().")	# TODO: This seems to run more times than it should?
		STRETCH = 2
		BODY_MECH = 8
		self.group_str = self.generator.bone_groups.ensure(
			name = "Stretch Chain Controls"
			,layers = [STRETCH]
			,preset = 8
		)
		self.group_str_helper = self.generator.bone_groups.ensure(
			name = "Stretch Chain Helpers"
			,layers = [BODY_MECH]
		)
		if self.params.CR_shape_key_helpers:
			self.group_sk_helper = self.generator.bone_groups.ensure(
				name = "Stretch Chain Shape Key Helpers"
				,layers = [BODY_MECH]
			)


	def initialize(self):
		super().initialize()
		"""Gather and validate data about the rig."""

	def get_segments(self, org_i, chain):
		"""Determine how many deform and bbone segments should be in a section of the chain."""
		segments = self.params.CR_deform_segments
		bbone_segments = self.params.CR_bbone_segments
		
		if (org_i == len(chain)-1) and not self.params.CR_cap_control:
			return (1, 1)
		
		return (segments, bbone_segments)

	def create_shape_key_helpers(self, def_bone_1, def_bone_2):
		"""Create two bones between two deform bones. 
		Let's call the first SKP for Shape Key Helper Parent. 
			This copies the transforms of the end of the first def bone's bbone spline. What this bone is parented to doesn't really matter.
		Let's call the second SKH for Shape Key Helper.
			This is parented to SKP, but copies the transforms of the start of second deform bone's bbone spline.
		The goal is that when we read the local rotation of the SKH bone, we get an accurate representation of how much rotation is happening in this joint - Even when using the toon controls to deform the character in crazy ways.
		"""

		skp_bone = self.bone_infos.bone(
			name = def_bone_2.name.replace("DEF", "SKP"),
			head = def_bone_1.tail.copy(),
			tail = def_bone_1.tail + def_bone_1.vec,
			bone_group = self.group_sk_helper,
			parent = def_bone_1,
			bbone_width = 0.05,
			hide_select = self.mch_disable_select
		)
		skp_bone.scale_length(0.3)
		skp_bone.add_constraint(self.obj, 'COPY_TRANSFORMS', true_defaults=True, target=self.obj, subtarget=def_bone_1.name, use_bbone_shape=True, head_tail=1)

		skh_bone = self.bone_infos.bone(
			name = def_bone_2.name.replace("DEF", "SKH"),
			head = def_bone_2.head.copy(),
			tail = def_bone_2.tail.copy(),
			bone_group = self.group_sk_helper,
			parent = skp_bone,
			bbone_width = 0.03,
			hide_select = self.mch_disable_select
		)
		skh_bone.scale_length(0.4)
		skh_bone.add_constraint(self.obj, 'COPY_TRANSFORMS', true_defaults=True, target=self.obj, subtarget=def_bone_2.name, use_bbone_shape=True, head_tail=0)

	def make_str_bone(self, def_bone, org_bone, name=None):
		if not name:
			name = def_bone.name.replace("DEF", "STR")
		str_bone = self.bone_infos.bone(
			name = name,
			source = def_bone,
			bone_group = self.group_str,
			head = def_bone.head,
			tail = def_bone.tail,
			roll = def_bone.roll,
			custom_shape = self.load_widget("Sphere"),
			#use_custom_shape_bone_size = True,
			custom_shape_scale = 0.3,
			parent = org_bone,
		)
		str_bone.scale_length(0.3)
		self.str_bones.append(str_bone)
		return str_bone

	def make_str_chain(self, def_sections):
		### Create Stretch controls
		str_sections = []
		for sec_i, section in enumerate(def_sections):
			str_section = []
			for i, def_bone in enumerate(section):
				str_bone = self.make_str_bone(def_bone, self.org_chain[sec_i])
				if i==0:
					# Make first control bigger, to indicate that it behaves differently than the others.
					str_bone.custom_shape_scale *= 1.3
					self.main_str_bones.append(str_bone)
				str_section.append(str_bone)
			str_sections.append(str_section)
		
		if self.params.CR_cap_control:
			# Add final STR control.
			last_def = def_sections[-1][-1]
			sliced = slice_name(last_def.name)
			str_name = make_name(["STR", "TIP"], sliced[1], sliced[2])

			str_bone = self.make_str_bone(last_def, self.org_chain[-1], str_name)
			str_bone.head = last_def.tail
			str_bone.tail = last_def.tail + last_def.vec
			str_bone.custom_shape_scale *= 1.3
			str_section = []
			str_section.append(str_bone)
			str_sections.append(str_section)

		return str_sections

	def connect_parent_chain_rig(self):
		# If the parent rig is a chain rig with cap_control=False, make the last DEF bone of that rig stretch to this rig's first STR.
		parent_rig = self.rigify_parent
		if isinstance(parent_rig, CloudChainRig):
			if not parent_rig.params.CR_cap_control:
				meta_org_bone = self.generator.metarig.data.bones.get(self.org_chain[0].name.replace("ORG-", ""))
				if meta_org_bone.use_connect:
					def_bone = parent_rig.def_bones[-1]
					str_bone = self.str_bones[0]
					def_bone.bbone_custom_handle_end = str_bone.name
					def_bone.add_constraint(self.obj, 'STRETCH_TO', subtarget = str_bone.name)
					self.make_bbone_scale_drivers(def_bone)
					if self.params.CR_shape_key_helpers:
						self.create_shape_key_helpers(def_bone, self.def_bones[0])

	def rig_str_helper(self, str_h_bone, first_str, last_str, influence):
		str_h_bone.add_constraint(self.obj, 'COPY_LOCATION', true_defaults=True, target=self.obj, subtarget=first_str)
		str_h_bone.add_constraint(self.obj, 'COPY_LOCATION', true_defaults=True, target=self.obj, subtarget=last_str, influence=influence)

		str_h_bone.add_constraint(self.obj, 'COPY_ROTATION', true_defaults=True, target=self.obj, subtarget=first_str)
		str_h_bone.add_constraint(self.obj, 'COPY_ROTATION', true_defaults=True, target=self.obj, subtarget=last_str, influence=influence)
		str_h_bone.add_constraint(self.obj, 'DAMPED_TRACK', subtarget=last_str)

	def make_str_helpers(self, str_sections):
		main_str_bone = None
		### Create Stretch Helpers and parent STR to them
		for sec_i, section in enumerate(str_sections):
			for i, str_bone in enumerate(section):
				# If this STR bone is not the first in its section
				# Create an STR-H parent helper for it, which will hold some constraints 
				# that keep this bone between the first and last STR bone of the section.
				if i==0: 
					main_str_bone = str_bone
					main_str_bone.sub_bones = []
					continue
				main_str_bone.sub_bones.append(str_bone)

				str_h_bone = self.bone_infos.bone(
					name 		 = self.add_prefix_to_name(str_bone.name, "H")
					,source 	 = str_bone
					,bbone_width = 1/10
					,bone_group  = self.group_str_helper
					,parent		 = str_bone.parent
					,hide_select = self.mch_disable_select
				)
				str_bone.parent = str_h_bone

				first_str = section[0].name
				last_str = str_sections[sec_i+1][0].name
				influence_unit = 1 / len(section)
				influence = i * influence_unit
				self.rig_str_helper(str_h_bone, first_str, last_str, influence)

	def prepare_def_str_chains(self):
		# We refer to a full limb as a limb. (eg. Arm)
		# Each part of that limb is a section. (eg. Forearm)
		# And that section contains the bones. (eg. DEF-Forearm1)
		# The deform_segments parameter defines how many bones there are in each section.

		# Each DEF bbone is surrounded by an STR control on each end.
		
		### Create deform bones.
		# Each STR section's first and last bones act as a control for the bones inbetween them. These are the main_str_bones.
		self.main_str_bones = []
		self.str_bones = []
		self.def_bones = []

		def_sections = []
		for org_i, org_bone in enumerate(self.org_chain):
			org_name = org_bone.name
			org_bone.def_bones = []
			def_section = []

			# Last bone shouldn't get segmented.
			segments, bbone_segments = self.get_segments(org_i, self.org_chain)
			
			for i in range(0, segments):
				## Create Deform bones
				def_name = org_name.replace("ORG", "DEF")
				sliced = slice_name(def_name)
				number = str(i+1) if segments > 1 else ""
				def_name = make_name(sliced[0], sliced[1] + number, sliced[2])

				unit = org_bone.vec / segments

				def_bone = self.bone_infos.bone(
					name = def_name,
					source = org_bone,
					head = org_bone.head + (unit * i),
					tail = org_bone.head + (unit * (i+1)),
					roll = org_bone.roll,
					bbone_handle_type_start = 'TANGENT',
					bbone_handle_type_end = 'TANGENT',
					bbone_segments = bbone_segments,
					hide_select = self.mch_disable_select
				)
				if bbone_segments > 1:
					def_bone.inherit_scale = 'NONE'
				org_bone.def_bones.append(def_bone)
				self.def_bones.append(def_bone)
			
				if self.params.CR_sharp_sections:
					# First bone of the segment, but not the first bone of the chain.
					if i==0 and org_i != 0:
						def_bone.bbone_easein = 0
					# Last bone of the segment, but not the last bone of the chain.
					if i==segments-1 and org_i != len(self.org_chain)-1:
						def_bone.bbone_easeout = 0

				def_section.append(def_bone)
			def_sections.append(def_section)

		str_sections = self.make_str_chain(def_sections)
		self.make_str_helpers(str_sections)

		### Configure Deform (parent to STR or previous DEF, set BBone handle)
		for sec_i, section in enumerate(def_sections):
			for i, def_bone in enumerate(section):
				if i==0:
					# If this is the first bone in the section, parent it to the STR bone of the same indices.
					def_bone.parent = str_sections[sec_i][i].name
					# Create shape key helpers
					if self.params.CR_shape_key_helpers and sec_i>0:
						self.create_shape_key_helpers(def_sections[sec_i-1][-1], def_bone)
					if (i==len(section)-1) and (sec_i==len(def_sections)-1) and (not self.params.CR_cap_control): 
						# If this is also the last bone of the last section(eg. Wrist bone), don't do anything else, unless the Final Control option is enabled.
						break
				else:
					# Otherwise parent to previous deform bone.
					def_bone.parent = section[i-1].name
				
				# Set BBone start handle to the same index STR bone.
				def_bone.bbone_custom_handle_start = str_sections[sec_i][i].name
				
				next_str = ""
				if i < len(section)-1:
					# Set BBone end handle to the next index STR bone.
					next_str = str_sections[sec_i][i+1].name
					def_bone.bbone_custom_handle_end = next_str
				else:
					# If this is the last bone in the section, use the first STR of the next section instead.
					next_str = str_sections[sec_i+1][0].name
					def_bone.bbone_custom_handle_end = next_str
				
				# Stretch To constraint
				def_bone.add_constraint(self.obj, 'STRETCH_TO', subtarget=next_str)

				# BBone scale drivers
				if def_bone.bbone_segments > 1:
					self.make_bbone_scale_drivers(def_bone)

		self.connect_parent_chain_rig()

	def prepare_bones(self):
		super().prepare_bones()
		self.prepare_def_str_chains()

	##############################
	# Parameters

	@classmethod
	def add_parameters(cls, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		super().add_parameters(params)

		params.CR_show_chain_settings = BoolProperty(name="Chain Rig")
		params.CR_deform_segments = IntProperty(
			 name		 = "Deform Segments"
			,description = "Number of deform bones per section"
			,default	 = 2
			,min		 = 1
			,max		 = 9
		)
		params.CR_bbone_segments = IntProperty(
			 name="BBone Segments"
			,description="Number of BBone segments on deform bones"
			,default=6
			,min=1
			,max=32
		)
		params.CR_shape_key_helpers = BoolProperty(
			 name="Shape Key Helpers"
			,description="Create SKH- bones that reliably read the rotation between two deform bones, and can therefore be used to drive shape keys"
		)
		params.CR_sharp_sections = BoolProperty(
			 name="Sharp Sections"
			,description="BBone EaseIn/Out is set to 0 for bones connectiong two sections"
			,default=False
		)
		params.CR_cap_control = BoolProperty(
			 name		 = "Final Control"
			,description = "Add the final control at the end of the chain (Turn off if you connect another chain to this one)"
			,default	 = True
		)

	@classmethod
	def parameters_ui(cls, layout, params):
		""" Create the ui for the rig parameters.
		"""
		ui_rows = super().parameters_ui(layout, params)

		icon = 'TRIA_DOWN' if params.CR_show_chain_settings else 'TRIA_RIGHT'
		layout.prop(params, "CR_show_chain_settings", toggle=True, icon=icon)
		if not params.CR_show_chain_settings: return ui_rows

		layout.prop(params, "CR_deform_segments")
		layout.prop(params, "CR_bbone_segments")
		layout.prop(params, "CR_shape_key_helpers")
		sharp_sections = layout.row()
		sharp_sections.prop(params, "CR_sharp_sections")
		ui_rows['sharp_sections'] = sharp_sections
		layout.prop(params, "CR_cap_control")
		
		return ui_rows

class Rig(CloudChainRig):
	pass

def create_sample(obj):
    # generated by rigify.utils.write_metarig
    bpy.ops.object.mode_set(mode='EDIT')
    arm = obj.data

    bones = {}

    bone = arm.edit_bones.new('Chain_1')
    bone.head = 0.0000, 0.0000, 0.0000
    bone.tail = 0.0000, -0.5649, 0.0000
    bone.roll = -3.1416
    bone.use_connect = False
    bone.bbone_x = 0.0399
    bone.bbone_z = 0.0399
    bone.head_radius = 0.0565
    bone.tail_radius = 0.0282
    bone.envelope_distance = 0.1412
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bones['Chain_1'] = bone.name
    bone = arm.edit_bones.new('Chain_2')
    bone.head = 0.0000, -0.5649, 0.0000
    bone.tail = 0.0000, -1.1299, 0.0000
    bone.roll = -3.1416
    bone.use_connect = True
    bone.bbone_x = 0.0399
    bone.bbone_z = 0.0399
    bone.head_radius = 0.0282
    bone.tail_radius = 0.0565
    bone.envelope_distance = 0.1412
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bone.parent = arm.edit_bones[bones['Chain_1']]
    bones['Chain_2'] = bone.name
    bone = arm.edit_bones.new('Chain_3')
    bone.head = 0.0000, -1.1299, 0.0000
    bone.tail = 0.0000, -1.6948, -0.0000
    bone.roll = -3.1416
    bone.use_connect = True
    bone.bbone_x = 0.0399
    bone.bbone_z = 0.0399
    bone.head_radius = 0.0565
    bone.tail_radius = 0.0565
    bone.envelope_distance = 0.1412
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bone.parent = arm.edit_bones[bones['Chain_2']]
    bones['Chain_3'] = bone.name
    bone = arm.edit_bones.new('Chain_4')
    bone.head = 0.0000, -1.6948, -0.0000
    bone.tail = 0.0000, -2.2598, 0.0000
    bone.roll = -3.1416
    bone.use_connect = True
    bone.bbone_x = 0.0399
    bone.bbone_z = 0.0399
    bone.head_radius = 0.0565
    bone.tail_radius = 0.0565
    bone.envelope_distance = 0.1412
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bone.parent = arm.edit_bones[bones['Chain_3']]
    bones['Chain_4'] = bone.name

    bpy.ops.object.mode_set(mode='OBJECT')
    pbone = obj.pose.bones[bones['Chain_1']]
    pbone.rigify_type = 'cloud_chain'
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    try:
        pbone.rigify_parameters.CR_subdivide_deform = 10
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_controls_for_handles = True
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_show_spline_ik_settings = True
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_show_display_settings = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_curve_handle_ratio = 2.5
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_rotatable_handles = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_hook_name = "Cable"
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_show_chain_settings = True
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_sharp_sections = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_bbone_segments = 6
    except AttributeError:
        pass
    pbone = obj.pose.bones[bones['Chain_2']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['Chain_3']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['Chain_4']]
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