#====================== BEGIN GPL LICENSE BLOCK ======================
#
#  This program is free software; you can redistribute it and/or
#  modify it under the terms of the GNU General Public License
#  as published by the Free Software Foundation; either version 2
#  of the License, or (at your option) any later version.
#
#  This program is distributed in the hope that it will be useful,
#  but WITHOUT ANY WARRANTY; without even the implied warranty of
#  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#  GNU General Public License for more details.
#
#  You should have received a copy of the GNU General Public License
#  along with this program; if not, write to the Free Software Foundation,
#  Inc., 51 Franklin Street, Fifth Floor, Boston, MA 02110-1301, USA.
#
#======================= END GPL LICENSE BLOCK ========================

import bpy, os
from bpy.props import *
from mathutils import *

from rigify.base_rig import BaseRig, stage
from rigify.utils.bones import BoneDict
from rigify.utils.rig import connected_children_names

from ..definitions.driver import *
from .cloud_fk_chain import CloudFKChainRig

class Rig(CloudFKChainRig):
	"""Cloud shoulder rig. (Currently very simple)"""

	def find_org_bones(self, bone):
		"""Populate self.bones.org."""
		# We just want the base bone.
		return BoneDict(
			main=[bone.name],
		)

	def initialize(self):
		super().initialize()
		"""Gather and validate data about the rig."""

	@stage.prepare_bones
	def prepare_fk_shoulder(self):
		self.fk_chain[0].custom_shape = self.load_widget("Clavicle")
		self.fk_chain[0].bone_group = 'Body: Main IK Controls'
		self.register_parent(self.fk_chain[0], self.side_prefix.capitalize() + " Shoulder")

		self.fk_chain[0].parent = self.get_bone(self.base_bone).parent.name

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