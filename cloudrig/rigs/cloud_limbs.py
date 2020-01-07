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
from .cloud_fk_chain import CloudFKChainRig

class Rig(CloudFKChainRig):
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
		self.ikfk_prop = self.prop_bone.custom_props[ikfk_name] = CustomProp(ikfk_name, default=0.0)
		
		ik_stretch_name = "ik_stretch_%s_%s" %(limb, side)
		self.ik_stretch_prop = self.prop_bone.custom_props[ik_stretch_name] = CustomProp(ik_stretch_name, default=0.0)

		fk_hinge_name = "fk_hinge_%s_%s" %(limb, side)
		self.fk_hinge_prop = self.prop_bone.custom_props[fk_hinge_name] = CustomProp(fk_hinge_name, default=0.0)

	@stage.prepare_bones
	def prepare_root_bone(self):
		# Socket/Root bone to parent IK and FK to.
		root_name = self.base_bone.replace("ORG", "ROOT")
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
	def prepare_fk_limb(self):
		# Note: This runs after super().prepare_fk_chain().

		hng_child = self.fk_chain[0]
		for i, fk_bone in enumerate(self.fk_chain):
			if i == 0 and self.params.double_first_control:
				# Make a parent for the first control.
				fk_parent_bone = shared.create_parent_bone(self, fk_bone)
				fk_parent_bone.custom_shape = self.load_widget("FK_Limb")
				shared.create_dsp_bone(self, fk_parent_bone, center=True)

				# Store in the beginning of the FK list, since it's the new root of the FK chain.
				#self.fk_chain.insert(0, fk_parent_bone)
				hng_child = fk_parent_bone

			if i < 2:
				# Setup DSP bone for all but last bone.
				shared.create_dsp_bone(self, fk_bone, center=True)
				pass

			if i == 2:
				fk_bone.custom_shape_scale = 0.8
				if self.params.world_aligned:
					fk_name = fk_bone.name
					fk_bone.name = fk_bone.name.replace("FK-", "FK-W-")	# W for World?
					# Make child control for the world-aligned control, that will have the original transforms and name.
					# This is currently just the target of a Copy Transforms constraint on the ORG bone and therefore kindof redundant, because if we really wanted, we could use Armature constraints on those ORG bones instead of copy transforms. But then our outliner hierarchy is completely messed up ofc.
					fk_child_bone = self.bone_infos.bone(
						name = fk_name,
						source = fk_bone,
						only_transform = True,
						parent = fk_bone,
						#custom_shape = self.load_widget("FK_Limb"),
						custom_shape_scale = 0.5,
						bone_group = 'Body: FK Helper Bones'
					)
					#self.fk_chain.append(fk_child_bone)
					
					fk_bone.flatten()
			
			if i == 3 and self.params.type=='LEG':
				self.fk_toe = fk_bone
		
		# Create Hinge helper
		hng_bone = self.bone_infos.bone(
			name			= self.base_bone.replace("ORG", "FK-HNG"), # Name it after the first bone in the chain.
			source			= hng_child, 
			only_transform	= True,
			bone_group 		= 'Body: FK Helper Bones',
		)
		hng_child.parent = hng_bone

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

	@stage.prepare_bones
	def prepare_ik_limb(self):
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
			custom_shape_scale = 0.5,
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

		# Create IK control(s) (Hand/Foot)
		bone_name = chain[2]
		org_bone = self.get_bone(bone_name)
		mstr_name = bone_name.replace("ORG", "IK-MSTR")
		wgt_name = 'Hand_IK' if limb_type=='ARM' else 'Foot_IK'
		ik_mstr = self.bone_infos.bone(
			name = mstr_name, 
			source = org_bone, 
			custom_shape = self.load_widget(wgt_name),
			custom_shape_scale = 0.8,
			parent = None,	# TODO: Parent switching with operator that corrects transforms.
			bone_group = 'Body: Main IK Controls'
		)
		foot_dsp(ik_mstr)
		# Parent control
		double_control = None
		if self.params.double_ik_control:
			double_control = shared.create_parent_bone(self, ik_mstr)	# TODO: Test that this works, check other uses of create_parent_bone, make sure it's a good idea to use here.
			double_control.bone_group = 'Body: Main IK Controls Extra Parents'
			foot_dsp(double_control)
		
		if self.params.world_aligned:
			ik_mstr.flatten()
			double_control.flatten()
		
		# IK Chain
		ik_chain = []
		org_chain = []
		for i, bn in enumerate(chain):
			org_bone = self.get_bone(bn)
			org_chain.append(org_bone)
			ik_name = bn.replace("ORG", "IK")
			ik_bone = self.bone_infos.bone(ik_name, org_bone, 
				#ik_stretch = 0.1,
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
			
			if i == 2:
				# Create separate IK target bone
				self.ik_tgt_bone = self.bone_infos.bone(
					name = bn.replace("ORG", "IK-TGT"),
					source = org_bone,
					bone_group = 'Body: IK - IK Mechanism Bones',
					parent = ik_mstr
				)
				# Add the IK constraint to the previous bone, targetting this one.
				ik_chain[-2].add_constraint(self.obj, 'IK', 
					pole_subtarget = pole_ctrl.name,
					pole_angle = direction * pi/2,
					subtarget = self.ik_tgt_bone.name
				)
		
		# Stretch mechanism
		str_name = bone_name.replace("ORG", "IK-STR")
		str_bone = self.bone_infos.bone(
			name = str_name, 
			source = self.get_bone(chain[0]),
			tail = Vector(ik_mstr.head[:]),
			parent = self.root_bone.name,
			bone_group = 'Body: IK - IK Mechanism Bones'
		)

		sliced = slice_name(str_name)
		sliced[0].append("TIP")
		tip_name = make_name(*sliced)

		tip_bone = self.bone_infos.bone(
			name = tip_name, 
			source = org_chain[2], 
			parent = ik_mstr,#ik_chain[2],
			bone_group = 'Body: IK - IK Mechanism Bones'
		)

		tip_bone.add_constraint(self.obj, 'COPY_LOCATION',
			target = self.obj,
			subtarget = str_bone.name,
			head_tail = 1,
			true_defaults=True
		)

		str_bone.add_constraint(self.obj, 'STRETCH_TO', subtarget=self.ik_tgt_bone.name)
		str_bone.add_constraint(self.obj, 'LIMIT_SCALE', 
			use_max_y = True,
			max_y = 1.05, # TODO: How to calculate this correctly?
			influence = 0
		)

		str_drv = Driver()
		str_drv.expression = "1-stretch"
		var = str_drv.make_var("stretch")
		var.type = 'SINGLE_PROP'
		var.targets[0].id_type = 'OBJECT'
		var.targets[0].id = self.obj
		var.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (self.prop_bone.name, self.ik_stretch_prop.name)

		data_path = 'constraints["Limit Scale"].influence'
		
		str_bone.drivers[data_path] = str_drv

		if self.params.type == 'LEG':
			self.prepare_ik_foot(tip_bone, ik_chain[-2:], org_chain[-2:])
		
		self.ik_chain = ik_chain

		mid_str_transform_setup(self.main_str_bones[1])

	def mid_str_transform_setup(mid_str_bone):
		""" Set up transformation constraint to mid-limb STR bone """
		mid_str_bone = self.main_str_bones[1]
		trans_con_name = 'Transf_IK_Stretch'
		mid_str_bone.add_constraint(self.obj, 'TRANSFORM',
			subtarget = 'root',
			name = trans_con_name,
		)

		trans_drv = Driver()		# Influence driver
		trans_drv.expression = "ik*stretch"
		var_stretch = trans_drv.make_var("stretch")
		var_stretch.type = 'SINGLE_PROP'
		var_stretch.targets[0].id_type = 'OBJECT'
		var_stretch.targets[0].id = self.obj
		var_stretch.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (self.prop_bone.name, self.ik_stretch_prop.name)

		var_ik = trans_drv.make_var("ik")
		var_ik.type = 'SINGLE_PROP'
		var_ik.targets[0].id_type = 'OBJECT'
		var_ik.targets[0].id = self.obj
		var_ik.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (self.prop_bone.name, self.ikfk_prop.name)

		data_path = 'constraints["%s"].influence' %(trans_con_name)

		mid_str_bone.drivers[data_path] = trans_drv

		trans_loc_drv = Driver()
		distance = (self.ik_tgt_bone.head - ik_chain[0].head).length
		trans_loc_drv.expression = "max( 0, (distance-%0.4f * scale ) * (1/scale) /2 )" %(distance)

		var_dist = trans_loc_drv.make_var("distance")
		var_dist.type = 'LOC_DIFF'
		var_dist.targets[0].id = self.obj
		var_dist.targets[0].bone_target = self.ik_tgt_bone.name
		var_dist.targets[0].transform_space = 'WORLD_SPACE'
		var_dist.targets[1].id = self.obj
		var_dist.targets[1].bone_target = ik_chain[0].name
		var_dist.targets[1].transform_space = 'WORLD_SPACE'
		
		var_scale = trans_loc_drv.make_var("scale")
		var_scale.type = 'TRANSFORMS'
		var_scale.targets[0].id = self.obj
		var_scale.targets[0].transform_type = 'SCALE_Y'
		var_scale.targets[0].transform_space = 'WORLD_SPACE'
		var_scale.targets[0].bone_target = self.fk_chain[0].name

		data_path2 = 'constraints["%s"].to_min_y' %(trans_con_name)
		mid_str_bone.drivers[data_path2] = trans_loc_drv

	def prepare_ik_foot(self, ik_mstr, ik_chain, org_chain):
		ik_foot = ik_chain[0]
		# Create ROLL control behind the foot (Limit Rotation, lock other transforms)
		sliced_name = shared.slice_name(ik_foot.name)
		roll_name = shared.make_name(["ROLL"], sliced_name[1], sliced_name[2])
		roll_ctrl = self.bone_infos.bone(
			name = roll_name,
			head = ik_foot.head + Vector((0, self.scale, self.scale/4)),
			tail = ik_foot.head + Vector((0, self.scale/2, self.scale/4)),
			roll = pi,
			custom_shape = self.load_widget('FootRoll'),
			bone_group = 'Body: Main IK Controls',
			parent = ik_mstr
		)

		roll_ctrl.add_constraint(self.obj, 'LIMIT_ROTATION', 
			use_limit_x=True,
			min_x = -90 * pi/180,
			max_x = 130 * pi/180,
			use_limit_y=True,
			use_limit_z=True,
			min_z = -pi/2,
			max_z = pi/2,
		)

		# Create bone to use as pivot point when rolling back. This is read from the metarig and should be placed at the heel of the shoe, pointing forward.
		# We hardcode name for ankle pivot for now.
		ankle_pivot = self.generator.metarig.data.bones.get("AnklePivot" + self.side_suffix)
		assert ankle_pivot, "ERROR: Could not find AnklePivot bone in the metarig."

		ankle_pivot_ctrl = self.bone_infos.bone(
			name = "IK-RollBack" + self.side_suffix,
			head = ankle_pivot.head_local,
			tail = ankle_pivot.tail_local,
			roll = pi,
			bone_group = 'Body: IK - IK Mechanism Bones',
			parent = ik_mstr
		)

		ankle_pivot_ctrl.add_constraint(self.obj, 'TRANSFORM',
			subtarget = roll_ctrl.name,
			map_from = 'ROTATION',
			map_to = 'ROTATION',
			from_min_x_rot = -90 * pi/180,
			to_min_x_rot = -60 * pi/180,
		)
		
		# Create reverse bones
		rik_chain = []
		for i, b in reversed(list(enumerate(org_chain))):
			rik_bone = self.bone_infos.bone(
				name = b.name.replace("ORG", "RIK"),
				head = b.tail.copy(),
				tail = b.head.copy(),
				parent = ankle_pivot_ctrl,
				bone_group = 'Body: IK - IK Mechanism Bones'
			)
			rik_chain.append(rik_bone)
			ik_chain[i].parent = rik_bone

			if i == 1:
				rik_bone.add_constraint(self.obj, 'TRANSFORM',
					subtarget = roll_ctrl.name,
					map_from = 'ROTATION',
					map_to = 'ROTATION',
					from_min_x_rot = 90 * pi/180,
					from_max_x_rot = 166 * pi/180,
					to_min_x_rot = 0 * pi/180,
					to_max_x_rot = 169 * pi/180,
					from_min_z_rot = -60 * pi/180,
					from_max_z_rot = 60 * pi/180,
					to_min_z_rot = 10 * pi/180,
					to_max_z_rot = -10 * pi/180
				)
			
			if i == 0:
				rik_bone.add_constraint(self.obj, 'COPY_LOCATION',
					true_defaults = True,
					target = self.obj,
					subtarget = rik_chain[-2].name,
					head_tail = 1,
				)

				rik_bone.add_constraint(self.obj, 'TRANSFORM',
					name = "Transformation Roll",
					subtarget = roll_ctrl.name,
					map_from = 'ROTATION',
					map_to = 'ROTATION',
					from_min_x_rot = 0 * pi/180,
					from_max_x_rot = 135 * pi/180,
					to_min_x_rot = 0 * pi/180,
					to_max_x_rot = 118 * pi/180,
					from_min_z_rot = -45 * pi/180,
					from_max_z_rot = 45 * pi/180,
					to_min_z_rot = 25 * pi/180,
					to_max_z_rot = -25 * pi/180
				)
				rik_bone.add_constraint(self.obj, 'TRANSFORM',
					name = "Transformation CounterRoll",
					subtarget = roll_ctrl.name,
					map_from = 'ROTATION',
					map_to = 'ROTATION',
					from_min_x_rot = 90 * pi/180,
					from_max_x_rot = 135 * pi/180,
					to_min_x_rot = 0 * pi/180,
					to_max_x_rot = -31.8 * pi/180
				)
		
		# FK Toe bone should be parented between FK Foot and IK Toe.
		fk_toe = self.fk_toe
		fk_toe.parent = None
		fk_toe.add_constraint(self.obj, 'ARMATURE',
			targets = [
				{
					"subtarget" : self.fk_chain[-2].name	# FK Foot
				},
				{
					"subtarget" : ik_chain[-1].name		# IK Toe
				}
			],
		)

		drv1 = Driver()
		drv1.expression = "1-ik"
		var1 = drv1.make_var("ik")
		var1.type = 'SINGLE_PROP'
		var1.targets[0].id_type='OBJECT'
		var1.targets[0].id = self.obj
		var1.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (self.prop_bone.name, self.ikfk_prop.name)

		drv2 = drv1.clone()
		drv2.expression = "ik"

		data_path1 = 'constraints["Armature"].targets[0].weight'
		data_path2 = 'constraints["Armature"].targets[1].weight'
		
		fk_toe.drivers[data_path1] = drv1
		fk_toe.drivers[data_path2] = drv2

	@stage.prepare_bones
	def prepare_org_limb(self):
		# Note: Runs after prepare_org_chain().
		
		# Add Copy Transforms constraints targetting both FK and IK bones.
		# Put driver on only the second constraint.

		for i, org_bone in enumerate(self.org_chain):
			ik_bone = self.bone_infos.find(org_bone.name.replace("ORG", "IK"))
			if self.params.type == 'LEG' and i == len(self.org_chain)-1:
				# Don't add IK constraint to toe bone. It should always use FK control, even in IK mode.
				continue
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
			description="Ankle/Wrist IK/FK controls are aligned with world axes.", 
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