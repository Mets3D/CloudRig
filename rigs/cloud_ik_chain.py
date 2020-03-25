import bpy
from bpy.props import BoolProperty, StringProperty, FloatProperty
from mathutils import Vector

from rigify.base_rig import stage

from ..definitions.driver import Driver
from .cloud_fk_chain import CloudFKChainRig

class CloudIKChainRig(CloudFKChainRig):
	"""CloudRig IK chain."""

	def initialize(self):
		"""Gather and validate data about the rig."""
		super().initialize()

		# UI Strings and Custom Property names
		self.category = self.slice_name(self.base_bone)[1]
		if self.params.CR_use_custom_category_name:
			self.category = self.params.CR_custom_category_name

		self.limb_name = self.side_prefix + " " + self.category
		if self.params.CR_use_custom_limb_name:
			self.limb_name = self.params.CR_custom_limb_name

		self.limb_name_props = self.limb_name.replace(" ", "_").lower()
		self.ikfk_name = "ik_" + self.limb_name_props
		self.ik_stretch_name = "ik_stretch_" + self.limb_name_props
		self.fk_hinge_name = "fk_hinge_" + self.limb_name_props

	##############################
	# Parameters
	
	@classmethod
	def add_parameters(cls, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		super().add_parameters(params)

		params.CR_show_ik_settings = BoolProperty(name="IK Rig")

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

		params.CR_ik_limb_pole_offset = FloatProperty(	# TODO: Rename to ik_pole_offset
			 name	 	 = "Pole Vector Offset"
			,default 	 = 1.0
		)
		params.CR_double_first_control = BoolProperty(
			 name		 = "Double FK Control"
			,description = "The first FK control has a parent control. Having two controls for the same thing can help avoid interpolation issues when the common pose in animation is far from the rest pose"
			,default	 = True
		)
		params.CR_double_ik_control = BoolProperty(
			 name		 = "Double IK Control"
			,description = "The IK control has a parent control. Having two controls for the same thing can help avoid interpolation issues when the common pose in animation is far from the rest pose"
			,default	 = True
		)
		params.CR_world_aligned_controls = BoolProperty(
			 name		 = "World Aligned Control"
			,description = "Ankle/Wrist IK/FK controls are aligned with world axes"
			,default	 = True
		)

	@classmethod
	def parameters_ui(cls, layout, params):
		""" Create the ui for the rig parameters.
		"""
		super().parameters_ui(layout, params)

		icon = 'TRIA_DOWN' if params.CR_show_ik_settings else 'TRIA_RIGHT'
		layout.prop(params, "CR_show_ik_settings", toggle=True, icon=icon)
		if not params.CR_show_ik_settings: return

		name_row = layout.row()
		limb_column = name_row.column()
		limb_column.prop(params, "CR_use_custom_limb_name")
		if params.CR_use_custom_limb_name:
			limb_column.prop(params, "CR_custom_limb_name", text="")
		category_column = name_row.column()
		category_column.prop(params, "CR_use_custom_category_name")
		if params.CR_use_custom_category_name:
			category_column.prop(params, "CR_custom_category_name", text="")

		double_row = layout.row()
		double_row.prop(params, "CR_double_first_control")
		double_row.prop(params, "CR_double_ik_control")
		layout.prop(params, "CR_world_aligned_controls")
		layout.prop(params, "CR_ik_limb_pole_offset")

class Rig(CloudFKChainRig):
	pass