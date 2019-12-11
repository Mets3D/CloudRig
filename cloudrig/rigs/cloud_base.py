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

import bpy
from bpy.props import *
from mathutils import *

from rigify.base_rig import BaseRig, stage
from rigify.utils.bones import BoneDict
from rigify.utils.rig import connected_children_names

from ..definitions.driver import *
from ..definitions.custom_props import CustomProp
from ..definitions.bone import BoneInfoContainer, BoneInfo
from .cloud_utils import load_widget, make_name, slice_name

# Ideas:
# Should probably turn constraints into a class. At least it would let us more easily add drivers to them.
# I should implement a CollectionProperty-like class, for ID collections, similar to BoneInfoContainer.
# BoneInfo and other ID classes could perhaps live without all their values pre-assigned in __init__. The only ones that need to be pre-assigned are the ones that other things rely on, like how the length property relies on head and tail existing.
# I really need to make sure I can justify abstracting the entire set of blender rigging related datastructures... it feels really silly.

class CloudBaseRig(BaseRig):
	""" Base for CloudRig arms and legs.
	"""

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
		self.prepare_bone_groups()

		self.scale = self.obj.dimensions[2]/10

		self.defaults = {
			"bbone_x" : 0.05,
			"bbone_z" : 0.05,
			"rotation_mode" : "XYZ",
			"use_custom_shape_bone_size" : True
		}
		# Bone Info container used for storing new bone info created by the script.
		self.bone_infos = BoneInfoContainer(self.obj, self.defaults)
		
		self.bones.parent = self.get_bone(self.base_bone).parent.name

		# Properties bone and Custom Properties
		self.prop_bone = self.bone_infos.bone(
			name = "Properties_IKFK", 
			bone_group = 'Properties',
			custom_shape = load_widget("Cogwheel"),
			head = Vector((0, self.scale*1, 0)),
			tail = Vector((0, self.scale*2, 0))
		)

	def prepare_bone_groups(self):
		# Wipe any existing bone groups.
		# TODO this might work poorly when there's more than one type of CloudRig element in a rig.
		for bone_group in self.obj.pose.bone_groups:
			self.obj.pose.bone_groups.remove(bone_group)

	def generate_bones(self):
		# Apply scaling
		for bd in self.bone_infos.bones:
			if not bd.use_custom_shape_bone_size:
				bd.custom_shape_scale *= self.scale
			bd.bbone_x *= self.scale
			bd.bbone_z *= self.scale
		
		for bd in self.bone_infos.bones:
			if bd.name not in self.obj.data.edit_bones and bd.name not in self.bones.flatten() and bd.name!='root':
				bone_name = self.new_bone(bd.name)
	
	def parent_bones(self):
		for bd in self.bone_infos.bones:
			edit_bone = self.get_bone(bd.name)
			bd.write_edit_data(self.obj, edit_bone)
	
	def configure_bones(self):
		for bd in self.bone_infos.bones:
			pose_bone = self.get_bone(bd.name)
			bd.write_pose_data(pose_bone)

	def apply_bones(self):
		# In a previous stage, Rigify automatically parents bones that have no parent to the root bone.
		# We want to undo this when the bone has an Armature constraint, since such bones should never have a parent.
		for eb in self.obj.data.edit_bones:
			pb = self.obj.pose.bones.get(eb.name)
			for c in pb.constraints:
				if c.type=='ARMATURE':
					eb.parent = None
					break

	@stage.finalize
	def configure_display(self):
		# Armature display settings
		self.obj.display_type = 'SOLID'
		self.obj.data.display_type = 'BBONE'
	
	@stage.finalize
	def transform_locks(self):
		# Rigify automatically locks transforms of bones whose names match this regex: "[A-Z][A-Z][A-Z]-"
		# We want to undo this... For now, we just don't want anything to be locked. In future, maybe lock based on bone groups.
		for pb in self.obj.pose.bones:
			pb.lock_location = (False, False, False)
			pb.lock_rotation = (False, False, False)
			pb.lock_rotation_w = False
			pb.lock_scale = (False, False, False)

	##############################
	# Parameters

	@classmethod
	def add_parameters(self, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		pass

	@classmethod
	def parameters_ui(self, layout, params):
		""" Create the ui for the rig parameters.
		"""
		pass