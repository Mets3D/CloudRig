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

# <pep8 compliant>

import bpy
from bpy.props import *
from itertools import count

from rigify.utils.layers import DEF_LAYER
from rigify.utils.errors import MetarigError
from rigify.utils.rig import connected_children_names
from rigify.utils.naming import make_derived_name
from rigify.utils.widgets_basic import create_bone_widget
from rigify.utils.bones import BoneDict, BoneUtilityMixin, put_bone
from rigify.utils.misc import map_list

from rigify.base_rig import BaseRig, stage

from .cloud_utils import load_widget

# Registerable rig template classes MUST be called exactly "Rig"!!!
# (This class probably shouldn't be registered in the future)
class Rig(BaseRig):
	""" Base for CloudRig arms and legs.
	"""
	# NOTE: The rigging shouldn't rely on ORG bones unless neccessary, so that we can delete them at the end of the generation process. There's no need for the generated rig to contain the original metarig.

	# overrides BaseRig.find_org_bones.
	def find_org_bones(self, bone):
		"""Populate self.bones.org."""
		# For now we just grab all connected children of our main bone and put it in self.bones.org.main.
		return BoneDict(
			main=[bone.name] + connected_children_names(self.obj, bone.name),
		)

	def initialize(self):
		super().initialize()
		"""Gather and validate data about the rig."""
		self.type = self.params.type

	# DSP bones - Display bones at the mid-point of each bone to use as display transforms for FK.
	# TODO: This should be in a shared place like utils or something.
	def create_dsp_bone(self, parent):
		if not self.params.display_middle: return
		dsp_name = "DSP-" + parent.name
		dsp = self.copy_bone(parent.name, dsp_name, parent=True, length=0.05)
		dsp_bone = self.get_bone(dsp_name)
		dsp_bone.parent = parent
		
		loc = parent.head + (parent.tail-parent.head)/2
		put_bone(self.obj, dsp_name, loc)
		
		if 'dsp' not in self.bones.mch:
			self.bones.mch.dsp = []
		self.bones.mch.dsp.append(dsp_name)

	# FK Controls
	@stage.generate_bones
	def generate_everything(self):
		self.generate_fk_controls(self.bones.org.main)

	def generate_fk_controls(self, chain):
		for i, bn in enumerate(chain):
			fk_name = bn.replace("ORG", "FK")
			self.copy_bone(bn, fk_name)
			fk_bone = self.get_bone(fk_name)

			if 'fk' not in self.bones.ctrl:
				self.bones.ctrl.fk = []
			self.bones.ctrl.fk.append(fk_name)

			if i > 0:
				parent_bone = self.get_bone(self.bones.ctrl.fk[-2])
				fk_bone.parent = parent_bone

			if i < 2:
				self.create_dsp_bone(fk_bone)

	@stage.finalize
	def configure_everything(self):
		for i, fk_name in enumerate(self.bones.ctrl.fk):
			fk_bone = self.get_bone(fk_name)
			fk_bone.custom_shape = load_widget("FK_Limb")
			if i < 2:
				fk_bone.custom_shape_transform = self.get_bone("DSP-"+fk_name)
		
		for dsp in self.bones.mch.dsp:
			dsp_bone = self.get_bone(dsp)
			dsp_bone.bone.bbone_x = dsp_bone.bone.bbone_z = 0.05	# For some reason this can apparently only be set from finalize??
		
		self.obj.display_type = 'SOLID'
		self.obj.data.display_type = 'BBONE'

	##############################
	# Parameters

	@classmethod
	def add_parameters(self, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		print(".......add params")
		params.type = EnumProperty(name="Type",
		items = (
			("ARM", "Arm", "Arm"),
			("LEG", "Leg", "Leg"),
			),
		)
		params.double_first_control = BoolProperty(
			name="Double First Control", 
			description="The first FK control has a parent control. Having two controls for the same thing can help avoid interpolation issues when the common pose in animation is far from the rest pose",
			default=True,
		)
		params.display_middle = BoolProperty(
			name="Display Centered", 
			description="Display FK controls on the center of the bone, instead of at its root", 
			default=True,
		)

	@classmethod
	def parameters_ui(self, layout, params):
		""" Create the ui for the rig parameters.
		"""
		r = layout.row()
		r.prop(params, "type")
		r = layout.row()
		r.prop(params, "display_middle")