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

from .. import shared
from ..definitions.driver import *
from ..definitions.custom_props import CustomProp
from ..definitions.bone import BoneInfoContainer, BoneInfo
from .cloud_utils import make_name, slice_name
from .cloud_chain import CloudChainRig

class CloudFKChainRig(CloudChainRig):
	"""CloudRig FK chain."""

	def initialize(self):
		super().initialize()
		"""Gather and validate data about the rig."""

	@stage.prepare_bones
	def prepare_root(self):
		# Socket/Root bone to parent everything to.
		root_name = self.base_bone.replace("ORG", "ROOT-")
		base_bone = self.get_bone(self.base_bone)
		self.root_bone = self.bone_infos.bone(
			name 				= root_name, 
			source 				= base_bone, 
			only_transform 		= True, 
			parent 				= self.bones.parent,
			custom_shape 		= self.load_widget("Cube"),
			custom_shape_scale 	= 0.5,
			bone_group			= 'Body: IK - IK Mechanism Bones'
		)

	@stage.prepare_bones
	def prepare_fk(self):
		fk_chain = []
		fk_name = ""
		for i, bn in enumerate(self.bones.org.main):
			edit_bone = self.get_bone(bn)
			fk_name = bn.replace("ORG", "FK")
			fk_bone = self.bone_infos.bone(
				name				= fk_name, 
				source				= edit_bone,
				**self.defaults,
				custom_shape 		= self.load_widget("FK_Limb"),
				custom_shape_scale 	= 1,
				parent				= self.root_bone.name
			)
			if i > 0:
				# Parent FK bone to previous FK bone.
				fk_bone.parent = fk_chain[-1]
			fk_chain.append(fk_bone)
			
		for fkb in fk_chain:
			fkb.bone_group = "Body: Main FK Controls"
		
		self.fk_chain = fk_chain

	@stage.prepare_bones
	def prepare_ik(self):
		pass

	@stage.prepare_bones
	def prepare_org(self):
		# Find existing ORG bones
		# Add Copy Transforms constraints targetting both FK.
		
		for i, bn in enumerate(self.bones.org.main):
			fk_bone = self.bone_infos.find(bn.replace("ORG", "FK"))
			org_bone = self.bone_infos.find(bn)

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