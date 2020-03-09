from bpy.props import *
from mathutils import *
from math import pi

from rigify.base_rig import stage

from ..definitions.driver import *
from .cloud_chain import CloudChainRig

class CloudFKChainRig(CloudChainRig):
	"""CloudRig FK chain."""

	def initialize(self):
		"""Gather and validate data about the rig."""
		super().initialize()

	@stage.prepare_bones
	def prepare_fk_chain(self):
		self.fk_chain = []
		fk_name = ""

		for i, org_bone in enumerate(self.org_chain):
			fk_name = org_bone.name.replace("ORG", "FK")
			fk_bone = self.bone_infos.bone(
				name				= fk_name, 
				source				= org_bone,
				custom_shape 		= self.load_widget("FK_Limb"),
				custom_shape_scale 	= org_bone.custom_shape_scale,# * 0.8,
				parent				= self.bones.parent,
				bone_group = "Body: Main FK Controls"
			)
			if i > 0:
				# Parent FK bone to previous FK bone.
				fk_bone.parent = self.fk_chain[-1]
			if self.params.center_all_fk:
				self.create_dsp_bone(fk_bone, center=True)
			if self.params.counter_rotate_str:
				str_bone = self.main_str_bones[i]
				str_bone.add_constraint(self.obj, 'TRANSFORM',
				subtarget = fk_bone.name,
				map_from = 'ROTATION', map_to='ROTATION',
				use_motion_extrapolate = True,
				from_max_x_rot = 1, from_max_y_rot = 1, from_max_z_rot = 1,
				to_max_x_rot = -0.5, to_max_y_rot = -0.5, to_max_z_rot = -0.5
				)
			self.fk_chain.append(fk_bone)

	@stage.prepare_bones
	def prepare_org_chain(self):
		# Find existing ORG bones
		# Add Copy Transforms constraints targetting FK.
		for i, org_bone in enumerate(self.org_chain):
			fk_bone = self.bone_infos.find(org_bone.name.replace("ORG", "FK"))

			org_bone.add_constraint(self.obj, 'COPY_TRANSFORMS', true_defaults=True, target=self.obj, subtarget=fk_bone.name, name="Copy Transforms FK")

	##############################
	# Parameters

	@classmethod
	def add_parameters(cls, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		super().add_parameters(params)

		params.counter_rotate_str = BoolProperty(
			name="Counter-Rotate STR",
			description="Main STR- bones will counter half the rotation of their parent FK bones. This is only recommended when Deform Segments is 1, and will result in easier to pose smooth curves",
			default=False
		)
		params.center_all_fk = BoolProperty(
			name="Display FK in center"
			,description="Display all FK controls' shapes in the center of the bone, rather than the beginning of the bone"
			,default=False
		)

	@classmethod
	def parameters_ui(cls, layout, params):
		""" Create the ui for the rig parameters.
		"""
		super().parameters_ui(layout, params)

		layout.prop(params, "counter_rotate_str")
		layout.prop(params, "center_all_fk")

class Rig(CloudFKChainRig):
	pass