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
	""" Base for CloudRig arms and legs.
	"""
	def find_org_bones(self, bone):
		"""Populate self.bones.org."""
		# For now we just grab all connected children of our main bone and put it in self.bones.org.main.
		return BoneDict(
			main=[bone.name] + connected_children_names(self.obj, bone.name)[:2],
		)
	
	def initialize(self):
		super().initialize()
		"""Gather and validate data about the rig."""
		assert len(self.bones.org.main)>=3, "Limb bone chain must be at least 3 connected bones."
		self.type = self.params.type

		# Properties bone and Custom Properties
		limb = "arm" if self.params.type=='ARM' else "leg"
		side = "left" if self.base_bone.endswith("L") else "right"
		ikfk_name = "ik_%s_%s" %(limb, side)
		fk_hinge_name = "fk_hinge_%s_%s" %(limb, side)
		self.ikfk_prop = self.prop_bone.custom_props[ikfk_name] = CustomProp(ikfk_name, default=0.0)
		self.fk_hinge_prop = self.prop_bone.custom_props[fk_hinge_name] = CustomProp(fk_hinge_name, default=0.0)

		# Calculate IK Pole related info
		rot_axis = self.params.rotation_axis

		if rot_axis == 'x':
			self.main_axis, self.aux_axis = 'x', 'z'
		elif rot_axis == 'z':
			self.main_axis, self.aux_axis = 'z', 'x'
		
		bones = map_list(self.get_bone, self.bones.org.main[0:2])

		self.elbow_vector = self.compute_elbow_vector(bones)
		self.pole_angle = self.compute_pole_angle(bones, self.elbow_vector)
		self.rig_parent_bone = self.get_bone_parent(self.bones.org.main[0])

	####################################################
	# Utilities

	def compute_elbow_vector(self, bones):
		lo_vector = bones[1].vector
		tot_vector = bones[1].tail - bones[0].head
		return (lo_vector.project(tot_vector) - lo_vector).normalized() * tot_vector.length

	def get_main_axis(self, bone):
		return getattr(bone, self.main_axis + '_axis')

	def get_aux_axis(self, bone):
		return getattr(bone, self.aux_axis + '_axis')

	def compute_pole_angle(self, bones, elbow_vector):
		if self.params.rotation_axis == 'z':
			return 0

		vector = self.get_aux_axis(bones[0]) + self.get_aux_axis(bones[1])

		if elbow_vector.angle(vector) > pi/2:
			return -pi/2
		else:
			return pi/2

	def get_segment_pos(self, org, seg):
		bone = self.get_bone(org)
		return bone.head + bone.vector * (seg / self.segments)

	@staticmethod
	def vector_without_z(vector):
		return Vector((vector[0], vector[1], 0))


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
		
		# Create Hinge helper
		hng_name = self.base_bone.replace("ORG", "FK-HNG")	# Name it after the first bone in the chain.
		hng_bone = self.bone_infos.bone(
			name			= hng_name, 
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
	
	@stage.prepare_bones
	def prepare_ik(self):
		# What we need:
		# DONE IK Chain (equivalents to ORG, so 3 of these) - Make sure IK Stretch is enabled on first two, and they are parented and connected to each other.
		# DONE IK Controls: Wrist, Wrist Parent(optional)
		# DONE IK-STR- bone with its Limit Scale constraint set automagically somehow.
		# TODO IK Pole target and line, somehow automagically placed.
		
		limb_type = self.params.type
		chain = self.bones.org.main

		# Create IK Pole Control
		first_bn = chain[0]
		head = self.get_bone(chain[0]).tail + self.elbow_vector
		pole_ctrl = self.bone_infos.bone(
			name = "IK-POLE-" + limb_type.capitalize() + self.side_suffix,
			head = head,
			tail = head + self.elbow_vector/8,
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
		last_bn = chain[-1]
		org_bone = self.get_bone(last_bn)
		ik_name = last_bn.replace("ORG", "IK")
		wgt_name = 'Hand_IK' if limb_type=='ARM' else 'Foot_IK'
		ik_ctrl = self.bone_infos.bone(
			name = ik_name, 
			source = org_bone, 
			custom_shape = self.load_widget(wgt_name),
			custom_shape_scale = 2.5 if limb_type=='LEG' else 1,
			parent = None,	# TODO: Parent switching with operator that corrects transforms.
			bone_group = 'Body: Main IK Controls'
		)
		foot_dsp(ik_ctrl)
		# Parent control
		if self.params.double_ik_control:
			sliced = slice_name(ik_name)
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
		sliced = slice_name(ik_name)
		sliced[0].append("STR")
		str_name = make_name(*sliced)
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
		for i, bn in enumerate(chain[:-1]):
			org_bone = self.get_bone(bn)
			ik_name = bn.replace("ORG", "IK")
			ik_bone = self.bone_infos.bone(ik_name, org_bone, 
				ik_stretch = 0.1,
				bone_group = 'Body: IK - IK Mechanism Bones',
			)
			ik_chain.append(ik_bone)
			
			if i == 0:
				ik_bone.parent = self.root_bone.name
				pole_dsp.add_constraint(self.obj, 'DAMPED_TRACK', subtarget=ik_bone.name, head_tail=1, track_axis='TRACK_NEGATIVE_Y')
			else:
				ik_bone.parent = ik_chain[-2]
			
			if i == len(chain)-2:
				# Add the IK constraint to the 2nd-to-last bone.
				ik_bone.add_constraint(self.obj, 'IK', 
					pole_subtarget=pole_ctrl.name,
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

			data_path = 'constraints["%s"].influence' %(ik_ct_name)
			org_bone.drivers[data_path] = drv

	@stage.prepare_bones
	def prepare_deform_and_stretch(self):
		chain = self.bones.org.main[:]
		# We refer to a full limb as a limb. (eg. Arm)
		# Each part of that limb is a section. (eg. Forearm)
		# And that section contains the bones. (eg. DEF-Forearm1)
		# The deform_segments parameter defines how many bones there are in each section.

		# Each DEF bone is surrounded by an STR bone on each end.
		# Each STR section's first and last bones act as a control for the bones inbetween them.
		
		### Create deform bones.
		def_sections = []
		for org_i, org_name in enumerate(chain):
			segments = self.params.deform_segments
			bbone_segments = self.params.bbone_segments
			def_section = []

			if org_i == len(chain)-1:
				segments = 1
				bbone_segments = 1
			
			for i in range(0, segments):
				## Deform
				def_name = org_name.replace("ORG", "DEF")
				sliced = slice_name(def_name)
				def_name = make_name(sliced[0], sliced[1] + str(i+1), sliced[2])

				# Move head and tail into correct places
				org_bone = self.get_bone(org_name)	# TODO: Using BoneInfoContainer.bone() breaks stuff, why?
				org_vec = org_bone.tail-org_bone.head
				unit = org_vec / segments

				def_bone = self.bone_infos.bone(
					name = def_name,
					head = org_bone.head + (unit * i),
					tail = org_bone.head + (unit * (i+1)),
					roll = org_bone.roll,
					bbone_handle_type_start = 'TANGENT',
					bbone_handle_type_end = 'TANGENT',
					bbone_segments = bbone_segments,
					inherit_scale = 'NONE',
				)
			
				# First bone of the segment, but not the first bone of the chain.
				if i==0 and org_i != 0:
					def_bone.bbone_easein = 0
				
				# Last bone of the segment, but not the last bone of the chain.
				if i==segments-1 and org_i != len(chain)-1:
					def_bone.bbone_easeout = 0
				
				# Last bone of the chain.
				if i==segments-1 and org_i == len(chain)-1:
					def_bone.inherit_scale = 'FULL'	# This is not perfect - when trying to adjust the spline shape by scaling the STR control on local Y axis, it scales the last deform bone in a bad way.

				next_parent = def_bone.name
				def_section.append(def_bone)
			def_sections.append(def_section)

		### Create Stretch controls
		str_sections = []
		for sec_i, section in enumerate(def_sections):
			str_section = []
			for i, def_bone in enumerate(section):
				# TODO Figure out what bones to parent STR to, and how to find FK names.
				# I think we parent STR to ORG though. No need to find FK names.
				str_bone = self.bone_infos.bone(
					name = def_bone.name.replace("DEF", "STR"),
					head = def_bone.head,
					tail = def_bone.tail,
					roll = def_bone.roll,
					custom_shape = self.load_widget("Sphere"),
					custom_shape_scale = 2,
					bone_group = 'Body: STR - Stretch Controls',
					parent=chain[sec_i],
				)
				str_bone.scale(0.3)
				if i==0:
					# Make first control bigger.
					str_bone.custom_shape_scale = 2.5
				
				str_section.append(str_bone)
			str_sections.append(str_section)
	
		### Create Stretch Helpers and parent STR to them
		for sec_i, section in enumerate(str_sections):
			for i, str_bone in enumerate(section):
				# If this STR bone is not the first in its section
				# Create an STR-H parent helper for it, which will hold some constraints 
				# that keep this bone between the first and last STR bone of the section.
				if i==0: continue
				str_h_bone = self.bone_infos.bone(
					name = str_bone.name.replace("STR-", "STR-H-"),
					source = str_bone,
					only_transform = True,
					bone_group = 'Body: STR-H - Stretch Helpers',
					parent = str_bone.parent
				)
				str_bone.parent = str_h_bone.name

				first_str = section[0].name
				last_str = str_sections[sec_i+1][0].name

				str_h_bone.add_constraint(self.obj, 'COPY_LOCATION', true_defaults=True, target=self.obj, subtarget=first_str)
				str_h_bone.add_constraint(self.obj, 'COPY_LOCATION', true_defaults=True, target=self.obj, subtarget=last_str, influence=0.5)
				str_h_bone.add_constraint(self.obj, 'DAMPED_TRACK', subtarget=last_str)
		
		### Configure Deform (parent to STR or previous DEF, set BBone handle)
		for sec_i, section in enumerate(def_sections):
			for i, def_bone in enumerate(section):
				if i==0:
					# If this is the first bone in the section, parent it to the STR bone of the same indices.
					def_bone.parent = str_sections[sec_i][i].name
					if i==len(section)-1 and sec_i==len(def_sections)-1: 
						# If this is also the last bone of the last section(eg. Wrist bone), don't do anything else.
						break
				else:
					# Otherwise parent to previous deform bone.
					def_bone.parent = section[i-1].name
				
				# Set BBone start handle to the same index STR bone.
				def_bone.bbone_custom_handle_start = str_sections[sec_i][i].name
				next_str = ""
				if i < len(section)-1:
					# Set BBone end handle to the next index STR bone.
					next_str = str_sections[sec_i][i+1].name
					def_bone.bbone_custom_handle_end = next_str
				else:
					# If this is the last bone in the section, use the first STR of the next section instead.
					next_str = str_sections[sec_i+1][0].name
					def_bone.bbone_custom_handle_end = next_str
				
				# Stretch To constraint
				def_bone.add_constraint(self.obj, 'STRETCH_TO', subtarget=next_str)

				# BBone scale drivers
				shared.make_bbone_scale_drivers(self.obj, def_bone)

	##############################
	# Parameters

	@classmethod
	def add_parameters(self, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		items = [
			('x', 'X manual', ''),
			('z', 'Z manual', ''),
		]

		params.rotation_axis = bpy.props.EnumProperty(
			items   = items,
			name	= "Rotation Axis",
			default = 'x'
		)

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

		layout.prop(params, "rotation_axis")