#====================== BEGIN GPL LICENSE BLOCK ======================
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software Foundation,
# Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
#======================= END GPL LICENSE BLOCK ========================

import bpy
from bpy.props import *
from mathutils import *
from math import pi

from rigify.utils.errors import MetarigError
from rigify.base_rig import stage
from rigify.utils.bones import BoneDict
from rigify.utils.rig import connected_children_names
from rigify.utils.misc import map_list

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
				**self.defaults,
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
	def add_parameters(self, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		super().add_parameters(params)

	@classmethod
	def parameters_ui(self, layout, params):
		""" Create the ui for the rig parameters.
		"""
		super().parameters_ui(layout, params)

class Rig(CloudFKChainRig):
	pass