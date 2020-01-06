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
from .cloud_fk_chain import CloudChainRig

class Rig(CloudChainRig):
	"""CloudRig arms and legs."""
	
	"""
	What we need in a Spine rig:
	FK controls should be placed in the center of ORG bones. This does mean that ORG bones can't copy transforms of the FK controls directly.
	The transforms of the ORG controls don't really matter anyways, only the transforms of the STR controls that they usually own.
	We could use Armature constraints on the ORG bones instead, but that would destroy their local rotation matrix, which we need to stay clean, or readable from someplace at least.
	Alternatively we can differentiate between the FK control layer and another FK mechanism layer. The control layer would have no prefix, while the mechanism layer would have the FK prefix.
	The mechanism layer would not be offset to the halfway point, and it would be parented to the control layer.
	Then the ORG bones can copy transforms from those guys.

	Okay, cool. What about IK?
	On Rain's rig, the IK secondary controls are placed in the same place as the FK's - DEF bones halfway point.
	This works well, but I know we did it out of necessity, not because it works well. So, I wonder if doing it differently could work better.
	In Rain's rig, the IK and FK controls had to work together, which is not as true for this rig since the control branches off upward of the ORG bones.
	However, if we ever want to add an IK/FK snap for the spine, we'll need to be able to snap the IK controls to the FK controls and get precisely the same pose.
	
	Okay, we'll do it the same way as on Rain - The IK controls are in the same place as the FK controls. 
	The intermediate layer between IK/FK and ORG will switch between IK/FK via Armature constraint.
	ORG could just be parented to the intermediate layer, but then we don't get useful local transforms, so we stick with Copy Transforms for that.
	I guess we can call the intermediate layer IKFK.
	
	Alternatively, we can make FK bones Copy Transforms of the IK bones when IK is enabled, just like on Rain. No need for an intermediate layer. Kindof. ORG then just has to be parented to FK.

	So ORG is parented to FK
	FK follows IK
	FK and IK are in mid-points of DEF

	ORG owns STR
	STR drives DEF

	so IK->FK->ORG->STR->DEF

	We could even cut ORG out of the equation. We can now always rely on FK to find local rotation of any spine segment.

	We could technically define IK after FK. We'd just add the IK constraint to the FK in the IK setup function, which actually kindof makes sense.
	We need ORG to parent the thighs to the hips in a nice way. This is because the thighs are parented to the ORG bone (automatically, based on metarig), so the ORG bone should move along with it the hip... Not too sure how though...
	It would be nice to have a reverse hip bone in the metarig, but then I'm not sure how to make that part of the spine rig element.
	What if we consider ORG-Spine to be a reverse bone? This would require that RibCage isn't hard parented to it anymore.
	"""

	def initialize(self):
		"""Gather and validate data about the rig."""
		super().initialize()

	@stage.prepare_bones
	def prepare_fk_spine(self):
		# Create Troso Master control
		# TODO/NOTE: The pelvis can be placed arbitrarily, but there's no good way currently to do this from the metarig.
		# To be fair, the more customizability we add to the metarig, the less it becomes a metarig...
		self.mstr_torso = self.bone_infos.bone(
			name = "MSTR-Torso",
			head = self.org_chain[0].center,
			tail = self.org_chain[0].center + Vector((0, 0, 0.1)),
			custom_shape = self.load_widget("Torso_Master"),
			bone_group = 'Body: Main IK Controls',
		)
		#self.mstr_torso.flatten()
		if self.params.double_controls:
			double_mstr_pelvis = shared.create_parent_bone(self, self.mstr_torso)
			double_mstr_pelvis.bone_group = 'Body: Main IK Controls Extra Parents'

		# Create FK bones
		# This should work with an arbitrary spine length. We assume that the chain ends in a neck and head.
		self.fk_chain = []
		fk_name = ""
		next_parent = self.mstr_torso
		for i, org_bone in enumerate(self.org_chain):
			fk_name = org_bone.name.replace("ORG", "FK")
			fk_bone = self.bone_infos.bone(
				name				= fk_name, 
				source				= org_bone,
				**self.defaults,
				custom_shape 		= self.load_widget("FK_Limb"),
				custom_shape_scale 	= 0.9 * org_bone.custom_shape_scale,
				parent				= next_parent,
				bone_group = "Body: Main FK Controls"
			)
			next_parent = fk_bone

			self.fk_chain.append(fk_bone)

			if i < len(self.org_chain)-2:	# Spine but not head and neck
				# Shift FK controls up to the center of their ORG bone
				org_bone = self.org_chain[i]
				fk_bone.put(org_bone.center)
				fk_bone.flatten()

				# Create a child corrective - Everything that would normally be parented to this FK bone should actually be parented to this child bone.
				fk_child_bone = self.bone_infos.bone(
					name = fk_bone.name.replace("FK", "FK-C"),
					source = fk_bone,
					only_transform = True,
					custom_shape = fk_bone.custom_shape,
					custom_shape_scale = fk_bone.custom_shape_scale * 0.9,
					bone_group = 'Body: FK Helper Bones',
					parent = fk_bone
				)
				# Ideally, we would populate these bones' constraints from the metarig, because I think it will need tweaks for each character. But maybe I'm wrong.
				# TODO: Add FK-C constraints (4 Transformation Constraints).
				# I'm not sure if that should be done through the rig or customizable from the meta-rig. Maybe have defaults in here, but let the metarig overwrite?
				# But then we could just have defaults in the metarig as well...
				# But then reproportioning the rig becomes complicated, unless we store the constraint on the original bone, and somehow tell that constraint to go on the FK-C bone and target the FK bone...
				# It would be doable though... let's say a constraint is named FK-C:Transf_Fwd@FK - It would go on the FK-C-BoneName bone and its target would be FK-BoneName.
				# Could run into issues with armature constraint since it has multiple targets.
				next_parent = fk_child_bone
				fk_bone.fk_child = fk_child_bone

				# TODO: Copy Transforms constraint and driver for IK.

	@stage.prepare_bones
	def prepare_ik_spine(self):
		# Create master chest control
		# TODO: Once again, the position of this can be arbitrary.
		self.mstr_chest = self.bone_infos.bone(
				name				= "MSTR-Chest", 
				head				= self.org_chain[-3].head,
				tail 				= self.org_chain[-3].head + Vector((0, 0, 0.1)),
				**self.defaults,
				custom_shape 		= self.load_widget("Chest_Master"),
				custom_shape_scale 	= 0.7,
				parent				= self.mstr_torso,
				bone_group = "Body: Main IK Controls"
			)
		if self.params.double_controls:
			double_mstr_chest = shared.create_parent_bone(self, self.mstr_chest)
			double_mstr_chest.bone_group = 'Body: Main IK Controls Extra Parents'
		
		# Create master (reverse) hip control
		self.mstr_hips = self.bone_infos.bone(
				name				= "MSTR-Hips", 
				head				= self.org_chain[0].center,
				tail 				= self.org_chain[0].center + Vector((0, 0, -0.1)),
				**self.defaults,
				custom_shape 		= self.load_widget("Hips"),
				custom_shape_scale 	= 0.7,
				parent				= self.mstr_torso,
				bone_group = "Body: Main IK Controls"
		)

		self.ik_ctr_chain = []
		for i, org_bone in enumerate(self.org_chain):
			ik_name = org_bone.name.replace("ORG", "IK")	# Equivalent of IK-CTR bones in Rain (Technically animator-facing, but rarely used)
			ik_bone = self.bone_infos.bone(
				name				= ik_name, 
				source				= org_bone,
				**self.defaults,
				custom_shape 		= self.load_widget("Oval"),
				# custom_shape_scale 	= 0.9 * org_bone.custom_shape_scale,
				#parent				= next_parent,
				bone_group = "Body: IK - Secondary IK Controls"
			)
			self.ik_ctr_chain.append(ik_bone)

	@stage.prepare_bones
	def prepare_def_str_spine(self):
		# Tweak some display things
		for i, str_bone in enumerate(self.str_bones):
			str_bone.use_custom_shape_bone_size = True
			str_bone.custom_shape_scale = 1.5
			# if i >= len(self.str_bones)-4:
			# 	str_bone.custom_shape_scale *= 0.3
		for def_bone in self.def_bones:
			def_bone.bbone_x *= 0.3
			def_bone.bbone_z *= 0.3
		for org_bone in self.org_chain:
			org_bone.bbone_x *= 0.3
			org_bone.bbone_z *= 0.3
		
		for i, def_bone in enumerate(self.def_bones):
			if i == len(self.def_bones)-2:
				# Neck DEF bone
				def_bone.bbone_easeout = 0	# TODO: this doesn't work?

		# STR bones should be parented to their corresponding FK bone.
		for i, str_bone in enumerate(self.str_bones):
			parent = None
			if i == 0:
				str_bone.parent = self.mstr_hips
			elif i > len(self.fk_chain)-2:
				# Last two STR bones should both be parented to last FK bone(the head)
				str_bone.parent = self.fk_chain[-1]
			elif hasattr(self.fk_chain[i-1], 'fk_child'):
				str_bone.parent = self.fk_chain[i-1].fk_child
			else:
				str_bone.parent = self.fk_chain[i-1]

	@stage.prepare_bones
	def prepare_org_spine(self):
		org_spine = self.org_chain[0]
		org_spine.parent = self.mstr_torso.name
		self.org_chain[0].parent = self.mstr_torso.name

	##############################
	# Parameters

	@classmethod
	def add_parameters(self, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		super().add_parameters(params)

		params.double_controls = BoolProperty(
			name="Double Pelvis and Chest Controls", 
			description="Make duplicates of the main spine controls",
			default=True,
		)

	@classmethod
	def parameters_ui(self, layout, params):
		"""Create the ui for the rig parameters."""
		super().parameters_ui(layout, params)

		layout.prop(params, "double_first_control")