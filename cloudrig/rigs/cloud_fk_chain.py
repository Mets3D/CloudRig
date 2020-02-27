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

	@classmethod
	def parameters_ui(cls, layout, params):
		""" Create the ui for the rig parameters.
		"""
		super().parameters_ui(layout, params)

class Rig(CloudFKChainRig):
	pass