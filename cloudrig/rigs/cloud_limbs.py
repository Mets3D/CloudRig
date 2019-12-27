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
from .cloud_chain import CloudChainRig

class Rig(CloudChainRig):
	"""CloudRig arms and legs."""

	def find_org_bones(self, bone):
		"""Populate self.bones.org."""
		# For limbs, we only care about the first three bones in the chain.
		return BoneDict(
			main=[bone.name] + connected_children_names(self.obj, bone.name),
		)
	
	def initialize(self):
		super().initialize()
		"""Gather and validate data about the rig."""
		#assert len(self.bones.org.main)>=3, "Limb bone chain must be at least 3 connected bones."
		self.type = self.params.type

		# Properties bone and Custom Properties
		limb = "arm" if self.params.type=='ARM' else "leg"
		side = "left" if self.base_bone.endswith("L") else "right"
		ikfk_name = "ik_%s_%s" %(limb, side)
		fk_hinge_name = "fk_hinge_%s_%s" %(limb, side)
		self.ikfk_prop = self.prop_bone.custom_props[ikfk_name] = CustomProp(ikfk_name, default=0.0)
		self.fk_hinge_prop = self.prop_bone.custom_props[fk_hinge_name] = CustomProp(fk_hinge_name, default=0.0)

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
		fk_bones = []
		fk_name = ""
		for i, bn in enumerate(self.bones.org.main):
			edit_bone = self.get_bone(bn)
			fk_name = bn.replace("ORG", "FK")
			fk_bone = self.bone_infos.bone(
				name				= fk_name, 
				source				= edit_bone,
				**self.defaults,
				custom_shape 		= self.load_widget("FK_Limb"),
				custom_shape_scale 	= 0.6,
				parent				= self.root_bone.name
			)
			fk_bones.append(fk_bone)
			
			if i == 0 and self.params.double_first_control:
				# Make a parent for the first control.
				fk_parent_bone = shared.create_parent_bone(self, fk_bone)
				fk_parent_bone.custom_shape = self.load_widget("FK_Limb")
				shared.create_dsp_bone(self, fk_parent_bone, center=True)

				# Store in the beginning of the FK list, since it's the new root of the FK chain.
				fk_bones.insert(0, fk_parent_bone)
			else:
				# Parent FK bone to previous FK bone.
				fk_bone.parent = fk_bones[-2]
			
			if i < 2:
				# Setup DSP bone for all but last bone.
				shared.create_dsp_bone(self, fk_bone, center=True)
				pass

			if i == 2:
				if self.params.world_aligned:
					fk_name = fk_bone.name
					fk_bone.name = fk_bone.name.replace("FK-", "FK-W-")	# W for World?
					# Make child control for the world-aligned control, that will have the original transforms and name.
					fk_child_bone = self.bone_infos.bone(
						name = fk_name,
						source = fk_bone,
						only_transform = True,
						parent = fk_bone,
						custom_shape = self.load_widget("FK_Limb"),
						custom_shape_scale = 0.5
					)
					fk_bones.append(fk_child_bone)
				
					# Make last control world-aligned based on longest axis.
					vec = fk_bone.tail - fk_bone.head
					maxabs = 0
					max_index = 0
					for i, x in enumerate(vec):
						if abs(x) > maxabs:
							maxabs = abs(x)
							max_index = i

					for i, co in enumerate(fk_bone.tail):
						if i != max_index:
							fk_bone.tail[i] = fk_bone.head[i]
					fk_bone.roll = 0
		
		# Create Hinge helper
		hng_bone = self.bone_infos.bone(
			name			= self.base_bone.replace("ORG", "FK-HNG"), # Name it after the first bone in the chain.
			source			= fk_bones[0], 
			only_transform	= True,
			bone_group 		= 'Body: FK Helper Bones',
		)
		fk_bones[0].parent = hng_bone

		hng_bone.add_constraint(self.obj, 'ARMATURE', 
			targets = [
				{
					"subtarget" : 'root'
				},
				{
					"subtarget" : self.root_bone.name
				}
			],
		)

		drv1 = Driver()
		drv1.expression = "var"
		var1 = drv1.make_var("var")
		var1.type = 'SINGLE_PROP'
		var1.targets[0].id_type='OBJECT'
		var1.targets[0].id = self.obj
		var1.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (self.prop_bone.name, self.fk_hinge_prop.name)

		drv2 = drv1.clone()
		drv2.expression = "1-var"

		data_path1 = 'constraints["Armature"].targets[0].weight'
		data_path2 = 'constraints["Armature"].targets[1].weight'
		
		hng_bone.drivers[data_path1] = drv1
		hng_bone.drivers[data_path2] = drv2

		hng_bone.add_constraint(self.obj, 'COPY_LOCATION', true_defaults=True,
			target = self.obj,
			subtarget = self.root_bone.name,
		)

		for fkb in fk_bones:
			fkb.bone_group = "Body: Main FK Controls"

	# TODO: IK Foot with Roll	
	# Create a usual setup for STR/DEF bones, but with strictly 1 segment.

	# Create ROLL control behind the foot, parented to IK-Foot from the parent rigify_rig. (Limit Rotation, lock other transforms)

	# Create RollBack bone from the heel bone's head to the toe bone's head. Parented to IK. (Transformation Constraint)
	# Create RIK bones for Foot and Toe. (flipped orientation). 
	# 	Foot is parented to RollBack. (Copy Location of Toe tail, Roll, CounterRoll constraints)
	#	Toe is parented to RollBack. (Roll constraint)
	
	# ORG-Foot bone is parented between RIK and FK Foot with armature constraint.
	# FK-Toe bone 	is parented between RIK and FK Foot with armature constraint.

	@stage.prepare_bones
	def prepare_ik(self):
		limb_type = self.params.type
		chain = self.bones.org.main

		# Create IK Pole Control
		first_bn = chain[0]
		head = Vector( self.get_bone(chain[0]).tail[:] )
		direction = 1 if limb_type=='ARM' else -1
		offset = Vector((0, direction*self.scale*3, 0))
		pole_ctrl = self.bone_infos.bone(
			name = "IK-POLE-" + limb_type.capitalize() + self.side_suffix,
			head = head + offset,
			tail = head + offset*1.1,
			roll = 0,
			custom_shape = self.load_widget('ArrowHead'),
			bone_group = 'Body: Main IK Controls'
		)

		pole_dsp = shared.create_dsp_bone(self, pole_ctrl)

		def foot_dsp(bone):
			# Create foot DSP helpers
			if limb_type=='LEG':
				dsp_bone = shared.create_dsp_bone(self, bone)
				direction = 1 if self.side_suffix=='.L' else -1
				projected_head = Vector((bone.head[0], bone.head[1], 0))
				projected_tail = Vector((bone.tail[0], bone.tail[1], 0))
				projected_center = projected_head + (projected_tail-projected_head)/2
				dsp_bone.head = projected_center
				dsp_bone.tail = projected_center + Vector((0, -self.scale/10, 0))
				dsp_bone.roll = pi/2 * direction

		# Create IK control(s) (Wrist/Ankle)
		bone_name = chain[2]
		org_bone = self.get_bone(bone_name)
		mstr_name = bone_name.replace("ORG", "IK-MSTR")
		wgt_name = 'Hand_IK' if limb_type=='ARM' else 'Foot_IK'
		ik_ctrl = self.bone_infos.bone(
			name = mstr_name, 
			source = org_bone, 
			custom_shape = self.load_widget(wgt_name),
			custom_shape_scale = 2.5 if limb_type=='LEG' else 1,
			parent = None,	# TODO: Parent switching with operator that corrects transforms.
			bone_group = 'Body: Main IK Controls'
		)
		foot_dsp(ik_ctrl)
		# Parent control
		if self.params.double_ik_control:
			sliced = slice_name(mstr_name)
			sliced[0].append("P")
			parent_name = make_name(*sliced)
			parent_bone = self.bone_infos.bone(
				name = parent_name, 
				source = ik_ctrl, 
				custom_shape_scale = 3 if limb_type=='LEG' else 1.1,
				bone_group='Body: Main IK Controls Extra Parents'
			)
			foot_dsp(parent_bone)
			ik_ctrl.parent = parent_bone
		
		# Stretch mechanism
		str_name = bone_name.replace("ORG", "IK-STR")
		str_bone = self.bone_infos.bone(
			name = str_name, 
			source = self.get_bone(chain[0]),
			tail = Vector(ik_ctrl.head[:]),
			parent = self.root_bone.name,
			bone_group = 'Body: IK - IK Mechanism Bones'
		)
		
		str_bone.add_constraint(self.obj, 'STRETCH_TO', subtarget=ik_ctrl.name)
		str_bone.add_constraint(self.obj, 'LIMIT_SCALE', 
			use_max_y = True,
			max_y = 1.05, # TODO: How to calculate this correctly?
			influence = 0 # TODO: Put a driver on this, controlled by IK Stretch switch.
		)

		sliced = slice_name(str_name)
		sliced[0].append("TIP")
		tip_name = make_name(*sliced)
		tip_bone = self.bone_infos.bone(
			name = tip_name, 
			source = org_bone, 
			parent = ik_ctrl,
			bone_group = 'Body: IK - IK Mechanism Bones'
		)

		# Create IK Chain (first two bones)
		ik_chain = []
		for i, bn in enumerate(chain):
			org_bone = self.get_bone(bn)
			ik_name = bn.replace("ORG", "IK")
			ik_bone = self.bone_infos.bone(ik_name, org_bone, 
				ik_stretch = 0.1,
				bone_group = 'Body: IK - IK Mechanism Bones',
			)
			ik_chain.append(ik_bone)
			
			if i == 0:
				# Parent first bone to the limb root
				ik_bone.parent = self.root_bone.name
				# Add aim constraint to pole display bone
				pole_dsp.add_constraint(self.obj, 'DAMPED_TRACK', subtarget=ik_bone.name, head_tail=1, track_axis='TRACK_NEGATIVE_Y')
			else:
				ik_bone.parent = ik_chain[-2]
			
			if i == 1:
				# Add the IK constraint to the 2nd bone.
				ik_bone.add_constraint(self.obj, 'IK', 
					pole_subtarget = pole_ctrl.name,
					pole_angle = direction * pi/2,
					subtarget = tip_bone.name
				)
			
			if i == 2:
				# Parent to IK master.
				ik_bone.parent = ik_ctrl

	@stage.prepare_bones
	def prepare_org(self):
		# Find existing ORG bones
		# Add Copy Transforms constraints targetting both FK and IK bones.
		# Put driver on only the second constraint.
		
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
		super().add_parameters(params)

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
		params.world_aligned = BoolProperty(
			name="World Aligned Control", 
			description="IK/FK controls are aligned with world axes.", 
			default=True,
		)

	@classmethod
	def parameters_ui(self, layout, params):
		"""Create the ui for the rig parameters."""
		super().parameters_ui(layout, params)

		layout.prop(params, "type")
		layout.prop(params, "double_first_control")
		layout.prop(params, "double_ik_control")
		layout.prop(params, "display_middle")
		layout.prop(params, "world_aligned")