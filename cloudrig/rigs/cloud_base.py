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
from ..definitions.custom_props import CustomProp
from ..definitions.bone import BoneInfoContainer, BoneInfo
from .. import shared
from .cloud_utils import *

class CloudBaseRig(BaseRig, CloudUtilities):
	"""Base for all CloudRig rigs."""

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

		# Determine rig scale by armature height.
		self.scale = self.obj.dimensions[2]/10
		# Slap user-provided multiplier on top.
		self.display_scale = self.params.display_scale * self.scale

		self.side_suffix = ""
		self.side_prefix = ""
		base_bone_name = self.slice_name(self.base_bone)
		if "L" in base_bone_name[2]:
			self.side_suffix = "L"
			self.side_prefix = "Left"
		elif "R" in base_bone_name[2]:
			self.side_suffix = "R"
			self.side_prefix = "Right"

		self.defaults = {
			# "bbone_x" : 0.05,
			# "bbone_z" : 0.05,
			"rotation_mode" : "XYZ",
			#"use_custom_shape_bone_size" : False#True
		}
		# Bone Info container used for storing new bone info created by the script.
		self.bone_infos = BoneInfoContainer(self.obj, self.defaults)
		
		# Keep track of created widgets, so we can add them to Rigify-created Widgets collection at the end.
		self.widgets = []

		parent = self.get_bone(self.base_bone).parent
		self.bones.parent = parent.name if parent else ""

		# Properties bone and Custom Properties
		self.prop_bone = self.bone_infos.bone(
			name = "Properties_IKFK", 
			bone_group = 'Properties',
			custom_shape = self.load_widget("Cogwheel"),
			head = Vector((0, self.scale*2, 0)),
			tail = Vector((0, self.scale*4, 0)),
			bbone_x = self.scale/8,
			bbone_z = self.scale/8
		)

		# Root bone
		self.root_bone = self.bone_infos.bone(
			name = "root",
			bone_group = 'Body: Main IK Controls',
			head = Vector((0, 0, 0)),
			tail = Vector((0, self.scale*5, 0)),
			bbone_x = self.scale/3,
			bbone_z = self.scale/3,
			custom_shape = self.load_widget("Root")
		)

		self.obj.name = self.generator.metarig.name.replace("META", "RIG")
		self.obj['cloudrig'] = 1.0
	
	def prepare_bone_groups(self):
		# Wipe any existing bone groups.
		for bone_group in self.obj.pose.bone_groups:
			self.obj.pose.bone_groups.remove(bone_group)

	@stage.prepare_bones
	def load_org_bones(self):
		# Load ORG bones into BoneInfo instances.
		self.org_chain = []
		for bn in self.bones.org.main:	# NOTE: Make sure we don't define the parent bone. This rig should never define a BoneInfo instance for its parent!
			eb = self.get_bone(bn)
			eb.use_connect = False
			org_bi = self.bone_infos.bone(bn, eb, self.obj)
			
			# Rigify discards the bbone scale values from the metarig, but I'd like to keep them for easy visual scaling.
			meta_org_name = eb.name.replace("ORG-", "")
			meta_org = self.generator.metarig.pose.bones.get(meta_org_name)
			org_bi.bbone_x = meta_org.bone.bbone_x
			org_bi.bbone_z = meta_org.bone.bbone_z

			self.org_chain.append(org_bi)

	def generate_bones(self):
		root_bone = self.get_bone("root")
		root_bone.bbone_x = self.scale/10
		root_bone.bbone_z = self.scale/10

		for bd in self.bone_infos.bones:
			if (
				bd.name not in self.obj.data.edit_bones and
				bd.name not in self.bones.flatten() and
				bd.name != 'root'
			):
				bone_name = self.new_bone(bd.name)
	
	def parent_bones(self):
		for bd in self.bone_infos.bones:
			edit_bone = self.get_bone(bd.name)

			# Get a bone-specific scale factor based on the bone's original bbone scale.
			bd.scale_mult = (bd.bbone_x*10) / self.scale

			bd.write_edit_data(self.obj, edit_bone)
	
	def configure_bones(self):
		for bd in self.bone_infos.bones:
			pose_bone = self.get_bone(bd.name)
			
			# Apply scaling
			if not bd.use_custom_shape_bone_size:
				bd.custom_shape_scale *= self.display_scale * bd.scale_mult
			bd.write_pose_data(pose_bone)

	@stage.apply_bones
	def unparent_bones(self):
		# Rigify automatically parents bones that have no parent to the root bone.
		# This is fine, but we want to undo this when the bone has an Armature constraint, since such bones should never have a parent.
		# NOTE: This could be done via self.generator.disable_auto_parent(bone_name), but I prefer doing it this way.
		for eb in self.obj.data.edit_bones:
			pb = self.obj.pose.bones.get(eb.name)
			for c in pb.constraints:
				if c.type=='ARMATURE':
					eb.parent = None
					break

	@stage.rig_bones
	def rig_parent_switching(self):
		""" Rigging of parent switching is best done in a later stage rather than prepare_bones, 
		to ensure that parent rigs have been generated, 
		so that we can trust the required parent bones to actually exist.
		"""
		pass


	def finalize(self):
		self.select_layers(shared.default_active_layers)
		self.organize_widgets()
		self.configure_display()
		self.transform_locks()

		# Set root bone layers
		root_bone = self.get_bone("root")
		shared.set_layers(root_bone.bone, [0, 1, 16, 17])

	def organize_widgets(self):
		# Hijack the widget collection automatically created by Rigify.
		wgt_collection = self.generator.collection.children.get("Widgets")
		if not wgt_collection: 
			print("WARNING: Could not find Widgets collection.")
			return
		for wgt in self.widgets:
			if wgt.name not in wgt_collection.objects:
				wgt_collection.objects.link(wgt)

	def configure_display(self):
		# Armature display settings
		self.obj.display_type = 'SOLID'
		self.obj.data.display_type = 'BBONE'

	def transform_locks(self):
		# Rigify automatically locks transforms of bones whose names match this regex: "[A-Z][A-Z][A-Z]-"
		# We want to undo this... For now, we just don't want anything to be locked. In future, maybe lock based on bone groups. (TODO)
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
		params.display_scale = FloatProperty(
			name="Display Scale",
			description="Scale Bone Display Sizes",
			default=1,
			min=0.1,
			max=100
		)

	@classmethod
	def parameters_ui(self, layout, params):
		""" Create the ui for the rig parameters.
		"""
		layout.prop(params, "display_scale")

class Rig(CloudBaseRig):
	pass	# For testing purposes