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

# <pep8 compliant> (TODO: make it so)

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
from .cloud_base import CloudBaseRig

# Registerable rig template classes MUST be called exactly "Rig"!!!
# (This class probably shouldn't be registered in the future)
class Rig(CloudBaseRig):
	"""CloudRig foot."""
	# Create a usual setup for STR/DEF bones, but with strictly 1 segment.

	# Create ROLL control behind the foot, parented to IK-Foot from the parent rigify_rig. (Limit Rotation, lock other transforms)

	# Create RollBack bone from the heel bone's head to the toe bone's head. Parented to IK. (Transformation Constraint)
	# Create RIK bones for Foot and Toe. (flipped orientation). 
	# 	Foot is parented to RollBack. (Copy Location of Toe tail, Roll, CounterRoll constraints)
	#	Toe is parented to RollBack. (Roll constraint)
	
	# ORG-Foot bone is parented between RIK and FK Foot with armature constraint.
	# FK-Toe bone 	is parented between RIK and FK Foot with armature constraint.

	def find_org_bones(self, bone):
		self.toe = connected_children_names(self.obj, bone.name)[0]
	
	def initialize(self):
		super().initialize()
		return
		"""Gather and validate data about the rig."""
		# Properties bone and Custom Properties 
		side = "left" if self.base_bone.endswith("L") else "right"
		ikfk_name = "ik_%s_%s" %(limb, side)
		fk_hinge_name = "fk_hinge_%s_%s" %(limb, side)
		self.ikfk_prop = self.prop_bone.custom_props[ikfk_name] = CustomProp(ikfk_name, default=0.0)
		self.fk_hinge_prop = self.prop_bone.custom_props[fk_hinge_name] = CustomProp(fk_hinge_name, default=0.0)

	@stage.prepare_bones
	def prepare_org(self):
		# What we need:
		# Find FK-Foot bone created by the parent rig... Is this even possible?
		# Add some constraints and drivers...
		# Create an FK-Toe bone
		# Toe is parented with Armature constraint with drivers.
		return
		for i, bn in enumerate(self.bones.org.main):
			ik_bone = self.bone_infos.find(bn.replace("ORG", "IK"))
			fk_bone = self.bone_infos.find(bn.replace("ORG", "FK"))
			org_bone = self.bone_infos.find(bn)

			org_bone.add_constraint(self.obj, 'COPY_TRANSFORMS', true_defaults=True, target=self.obj, subtarget=fk_bone.name, name="Copy Transforms FK")
			ik_ct_name = "Copy Transforms IK"
			ik_con = org_bone.add_constraint(self.obj, 'COPY_TRANSFORMS', true_defaults=True, target=self.obj, subtarget=ik_bone.name, name=ik_ct_name)

			drv = Driver()
			var = drv.make_var()
			var.targets[0].id = self.obj
			var.targets[0].data_path = 'pose.bones["%s"]["%s"]' %(self.prop_bone.name, self.ikfk_prop.name)

			data_path = 'constraints["%s"].influence' %(ik_ct_name)
			org_bone.drivers[data_path] = drv

	##############################
	# Parameters

	@classmethod
	def add_parameters(self, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""

		params.deform_segments = IntProperty(
			name="Deform Segments",
			description="Number of deform bones per limb piece",
			default=2,
			min=1,
			max=9
		)
		params.bbone_segments = IntProperty(
			name="BBone Segments",
			description="BBone segments of deform bones",
			default=10,
			min=1,
			max=32
		)

	@classmethod
	def parameters_ui(self, layout, params):
		""" Create the ui for the rig parameters.
		"""

		layout.prop(params, "deform_segments")
		layout.prop(params, "bbone_segments")