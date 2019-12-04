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

# <pep8 compliant> (TODO: make it so)

import bpy
from bpy.props import *
from mathutils import *

from rigify.utils.errors import MetarigError
from rigify.utils.rig import connected_children_names
from rigify.utils.naming import make_derived_name
from rigify.utils.widgets_basic import create_bone_widget
from rigify.utils.bones import BoneDict
from rigify.utils.mechanism import make_property

from rigify.base_rig import BaseRig, stage

from ..definitions.driver import *
from ..definitions.custom_props import CustomProp
from ..definitions.bone import BoneInfoContainer, BoneInfo
from .. import shared
from .cloud_utils import load_widget, make_name, slice_name

# Ideas:
# Should probably turn constraints into a class. At least it would let us more easily add drivers to them.
# I should implement a CollectionProperty-like class, for ID collections, similar to BoneInfoContainer.
# BoneInfo and other ID classes could perhaps live without all their values pre-assigned in __init__. The only ones that need to be pre-assigned are the ones that other things rely on, like how the length property relies on head and tail existing.
# I really need to make sure I can justify abstracting the entire blender rigging datastructures... it feels really silly.


# Registerable rig template classes MUST be called exactly "Rig"!!!
# (This class probably shouldn't be registered in the future)
class Rig(BaseRig):
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
		assert len(self.bones.org.main)==3, "Limb bone chain must consist of exactly 3 connected bones."
		
		self.prepare_bone_groups()

		self.defaults = {
			"bbone_x" : 0.05,
			"bbone_z" : 0.05,
			"rotation_mode" : "XYZ",
			"use_custom_shape_bone_size" : True
		}
		# Bone Info container used for storing new bone info created by the script.
		self.bone_infos = BoneInfoContainer(self.obj, self.defaults)
		# Bone Info container used for storing existing bone info from the meta-rig, which should overwrite anything done by the script.
		# TODO:  I still don't hate this idea, but we need to define how various properties are handled - eg, transforms would be overwritten, sure, but constraints? I guess figure this out when we have a use case.
		self.overriding_bone_infos = BoneInfoContainer(self.obj)
		
		self.bones.parent = self.get_bone(self.base_bone).parent.name
		self.type = self.params.type

		# Properties bone and Custom Properties
		self.prop_bone = self.bone_infos.bone("Properties_IKFK", bone_group='Properties')
		limb = "arm" if self.params.type=='ARM' else "leg"
		side = "left" if self.base_bone.endswith("L") else "right"
		ikfk_name = "ik_" + limb + "_" + side
		self.ikfk_prop = self.prop_bone.custom_props[ikfk_name] = CustomProp(ikfk_name, default=0.0)

	def prepare_bone_groups(self):
		# Wipe any existing bone groups.
		for bone_group in self.obj.pose.bone_groups:
			self.obj.pose.bone_groups.remove(bone_group)

	@stage.prepare_bones
	def prepare_fk(self):
		fk_bones = []
		fk_name = ""
		for i, bn in enumerate(self.bones.org.main):
			edit_bone = self.get_bone(bn)
			fk_name = bn.replace("ORG", "FK")
			fk_bone = self.bone_infos.bone(
				fk_name, 
				edit_bone,
				custom_shape = load_widget("FK_Limb"),
				**self.defaults
			)
			fk_bones.append(fk_bone)
			
			if i == 0 and self.params.double_first_control:
				# Make a parent for the first control.
				fk_parent_bone = shared.create_parent_bone(self, fk_bone)
				fk_parent_bone.custom_shape = load_widget("FK_Limb")
				shared.create_dsp_bone(self, fk_parent_bone)

				# Store in the beginning of the FK list, since it's the new root of the FK chain.
				fk_bones.insert(0, fk_parent_bone)
			else:
				# Parent FK bone to previous FK bone.
				fk_bone.parent = fk_bones[-2]
			
			if i < 2:
				# Setup DSP bone for all but last bone.
				shared.create_dsp_bone(self, fk_bone)
				pass
		
		# Create Hinge helper
		hng_name = self.base_bone.replace("ORG", "FK-HNG")	# Name it after the first bone in the chain.
		hng_bone = self.bone_infos.bone(
			hng_name, 
			fk_bones[0], 
			only_transform=True,
			**self.defaults,
		)
		fk_bones[0].parent = hng_bone

		hng_bone.add_constraint(self.obj, 'ARMATURE', 
			targets = [
				{
					"subtarget" : 'root'
				},
				{
					"subtarget" : self.bones.parent
				}
			],
		)

		hng_bone.layers[2]=True
		hng_bone.bone_group = 'Body: FK Helper Bones'

		# Custom property. TODO: This could be set up in initialize(), perhaps.
		base_bone = self.bone_infos.bone(self.base_bone)
		hng_prop_name = "fk_hinge_left_arm" #TODO: How do we know what limb it belongs to? Maybe we don't care, if we're storing the property locally on the relevant bone anyways.
		hinge_prop = base_bone.custom_props[hng_prop_name] = CustomProp(hng_prop_name, default=0.0)
		base_bone.custom_props_edit["edit_bone_property"] = CustomProp("edit bone property", default=1.2)

		drv1 = Driver()
		drv1.expression = "var"
		var1 = drv1.make_var("var")
		var1.type = 'SINGLE_PROP'
		var1.targets[0].id_type='OBJECT'
		var1.targets[0].id = self.obj
		var1.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (base_bone.name, hng_prop_name)

		drv2 = Driver(drv1)
		drv2.expression = "1-var"

		data_path1 = 'pose.bones["%s"].constraints["Armature"].targets[0].weight' %(hng_name)
		data_path2 = 'pose.bones["%s"].constraints["Armature"].targets[1].weight' %(hng_name)
		
		hng_bone.drivers[data_path1] = drv1
		hng_bone.drivers[data_path2] = drv2

		hng_bone.add_constraint(self.obj, 'COPY_LOCATION', true_defaults=True,
			target=self.obj,
			subtarget=self.bones.parent,
			head_tail=1
		)

		for fkb in fk_bones:
			fkb.bone_group = "Body: Main FK Controls"
	
	@stage.prepare_bones
	def prepare_ik(self):
		# What we need:
		# IK Chain (equivalents to ORG, so 3 of these) - Make sure IK Stretch is enabled on first two, and they are parented and connected to each other.
		# IK Controls: Wrist, Wrist Parent(optional)
		# IK-STR- bone with its Limit Scale constraint set automagically somehow.
		# IK Pole target and line, somehow automagically placed.
		
		chain = self.bones.org.main

		# Create IK control(s) (Wrist/Ankle)
		bn = chain[-1]
		org_bone = self.get_bone(bn)
		ik_name = bn.replace("ORG", "IK")
		ik_ctrl = self.bone_infos.bone(
			ik_name, 
			org_bone, 
			custom_shape = load_widget("Hand_IK"),
			parent=None,
			bone_group='Body: Main IK Controls'
		)
		# Parent control
		if self.params.double_ik_control:
			sliced = slice_name(ik_name)
			sliced[0].append("P")
			parent_name = make_name(*sliced)
			parent_bone = self.bone_infos.bone(
				parent_name, 
				ik_ctrl, 
				custom_shape_scale=1.1,
				bone_group='Body: Main IK Controls Extra Parents'
			)
			ik_ctrl.parent = parent_bone
		
		# Stretch mechanism
		eb = self.get_bone(chain[0])
		sliced = slice_name(ik_name)
		sliced[0].append("STR")
		str_name = make_name(*sliced)
		str_bone = self.bone_infos.bone(
			str_name, 
			eb,
			tail=Vector(ik_ctrl.head[:]),
			bone_group = 'Body: IK - IK Mechanism Bones'
		)
		
		str_bone.add_constraint(self.obj, 'STRETCH_TO', subtarget=ik_ctrl.name)
		str_bone.add_constraint(self.obj, 'LIMIT_SCALE', 
			use_max_y = True,
			max_y = 1.05, # TODO: How to calculate this correctly?
			influence = 0 # TODO: Put a driver on this, controlled by IK Stretch switch.
		)

		sliced[0].append("TIP")
		tip_name = make_name(*sliced)
		tip_bone = self.bone_infos.bone(
			tip_name, 
			org_bone, 
			parent=ik_ctrl,
			bone_group='Body: IK - IK Mechanism Bones'
		)

		# Create IK Chain (first two bones)
		ik_chain = []
		for i, bn in enumerate(chain[:-1]):
			org_bone = self.get_bone(bn)
			ik_name = bn.replace("ORG", "IK")
			ik_bone = self.bone_infos.bone(ik_name, org_bone, 
				ik_stretch=0.1,
				bone_group='Body: IK - IK Mechanism Bones'
			)
			ik_chain.append(ik_bone)
			
			if i > 0:
				ik_bone.parent = ik_chain[-2]
			else:
				ik_bone.parent = self.bone_infos.bone(self.bones.parent)
			
			if i == len(chain)-2:
				# Add the IK constraint to the 2nd-to-last bone.
				ik_bone.add_constraint(self.obj, 'IK', 
					pole_target=None,	# TODO pole target.
					subtarget=tip_bone.name
				)

	@stage.prepare_bones
	def prepare_org(self):
		# What we need:
		# Find existing ORG bones
		# Add Copy Transforms constraints targetting both FK and IK bones.
		# Put driver on only the second constraint.
		# (Completely standard setup)
		
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

			data_path = 'pose.bones["%s"].constraints["%s"].influence' %(org_bone.name, ik_ct_name)
			org_bone.drivers[data_path] = drv

	@stage.prepare_bones
	def prepare_deform(self):
		chain = self.bones.org.main
		# What we need:
		# Two bendy deform bones per limb piece, surrounded by STR- controls. 
		# BBone properties are hooked up to the STR controls' transforms via drivers.
		# limb pieces connected in some funky way so that the bending of the second part doesn't affect the BBone of the first part.
			# In Rain this was done by having two STR- controls. I think I know a better way. Have one STR- control, but the ease in/out driver is slightly modified so that it's -1 by default.
		def_bones = [self.base_bone]	# Used for chain-parenting. TODO not neccessarily well thought out.
		for i, bn in enumerate(chain):
			segments = self.params.deform_segments
			if i == len(chain)-1:
				segments = 1
			for i in range(0, segments):
				## Deform
				def_name = bn.replace("ORG", "DEF")
				sliced = slice_name(def_name)

				# Figure out relevant bone names.
				def_name 	  =	make_name(sliced[0], sliced[1] + str(i+1), sliced[2])
				prev_def_name = make_name(sliced[0], sliced[1] + str(i),   sliced[2])
				str_name = def_name.replace("DEF", "STR")
				prev_str_name = prev_def_name.replace("DEF", "STR")

				# Move head and tail into correct places
				org_bone = self.get_bone(bn)	# TODO: Using BoneInfoContainer.bone() breaks stuff, why?
				org_vec = org_bone.tail-org_bone.head
				unit = org_vec / segments

				def_bone = self.bone_infos.bone(
					name = def_name,
					head = org_bone.head + (unit * i),
					tail = org_bone.head + (unit * (i+1)),
					roll = org_bone.roll,
					bbone_handle_type_start = 'TANGENT',
					bbone_handle_type_end = 'TANGENT',
					bbone_custom_handle_start = prev_str_name,
					bbone_custom_handle_end = str_name,
					parent = def_bones[-1]
				)
				def_bones.append(def_bone.name)

				## Stretchy controls
				
				# Figure out what bones to parent to, and how to find FK names.
				# TODO: STR- bones' transforms are locked, why? 
				str_bone = self.bone_infos.bone(str_name,
					head = def_bone.head,
					tail = def_bone.tail,
					roll = def_bone.roll,
					length = 0.1,
					custom_shape = load_widget("Sphere"),
					bone_group = 'Body: STR - Stretch Controls'
				)

				# TODO: Create STR- controls with shapes, assign them as bbone tangent
				# drivers
				# parenting
				# constraints

	def generate_bones(self):
		# for bn in self.bones.flatten():
		# 	bone = self.get_bone(bn)
		# 	self.overriding_bone_infos.bone(bn, bone)

		for bd in self.bone_infos.bones:
			if bd.name not in self.obj.data.bones and bd.name not in self.bones.flatten() and bd.name!='root':
				bone_name = self.new_bone(bd.name)
	
	def parent_bones(self):
		for bd in self.bone_infos.bones:
			edit_bone = self.get_bone(bd.name)
			bd.write_edit_data(self.obj, edit_bone)
			
			# overriding_bone = self.overriding_bone_infos.find(bd.name)
	
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

	def generate_stretchy(self):
		pass

	@stage.finalize
	def configure_display(self):
		# Armature display settings
		self.obj.display_type = 'SOLID'
		self.obj.data.display_type = 'BBONE'

	##############################
	# Parameters

	@classmethod
	def add_parameters(self, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		params.type = EnumProperty(name="Type",
		items = (
			("ARM", "Arm", "Arm"),
			("LEG", "Leg", "Leg"),
			),
		)
		params.double_first_control = BoolProperty(
			name="Double First FK Control", 
			description="The first FK control has a parent control. Having two controls for the same thing can help avoid interpolation issues when the common pose in animation is far from the rest pose",
			default=True,
		)
		params.double_ik_control = BoolProperty(
			name="Double IK Control", 
			description="The IK control has a parent control. Having two controls for the same thing can help avoid interpolation issues when the common pose in animation is far from the rest pose",
			default=True,
		)
		params.display_middle = BoolProperty(
			name="Display Centered", 
			description="Display FK controls on the center of the bone, instead of at its root", 
			default=True,
		)
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

		layout.prop(params, "type")
		layout.prop(params, "double_first_control")
		layout.prop(params, "double_ik_control")
		layout.prop(params, "display_middle")
		layout.prop(params, "deform_segments")
		layout.prop(params, "bbone_segments")