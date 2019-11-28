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
from itertools import count
from mathutils import *

from ..definitions.driver import *
from ..definitions.custom_props import CustomProp
from ..definitions.bone import BoneInfoContainer

from rigify.utils.errors import MetarigError
from rigify.utils.rig import connected_children_names
from rigify.utils.naming import make_derived_name
from rigify.utils.widgets_basic import create_bone_widget
from rigify.utils.bones import BoneDict
from rigify.utils.mechanism import make_property

from rigify.base_rig import BaseRig, stage

from .cloud_utils import load_widget, make_name, slice_name

# Ideas:
# I'd rather abstract bones in a way where I don't have to worry about being in pose or edit mode at all. Ie, store all bone properties in an abstract class that mimics Blender's internal bone data structures(while combining them all)
# But I'm not sure if it's worth the hassle or if I would run into any headaches.
# (This is the same idea that we arleady did for managing Drivers, which worked out pretty well, and these could also be combined)
# (We would add a "drivers" field to our ID class, which would store a list of drivers, or whatever extra info a driver would need to be realized on that ID when it is made into a real one.)
# And then I guess we would have to do the same for constraints.
# There could also be an Armature abstraction, just for the sake of storing a list of bones. That way, armature.make_real() can make the bones real without switching between edit and pose mode multiple times.

# Constraints should be automagically initialized with more sensible defaults, unless explicitly told to initialize with Blender's defaults(which are BAADDDD)

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
		
		self.defaults = {
			"bbone_x" : 0.05,
			"bbone_z" : 0.05,
			"rotation_mode" : "XYZ",
			"use_custom_shape_bone_size" : True
		}
		self.bone_infos = BoneInfoContainer(self.defaults)
		self.bones.parent = self.get_bone(self.base_bone).parent.name
		self.type = self.params.type

	# DSP bones - Display bones at the mid-point of each bone to use as display transforms for FK.
	# TODO: This should be in a shared place like utils or something.
	def create_dsp_bone(self, parent):
		if not self.params.display_middle: return
		dsp_name = "DSP-" + parent.name
		dsp_bone = self.bone_infos.bone(dsp_name, parent, custom_shape=None, parent=parent)
		dsp_bone.put(parent.center, 0.1, 0.1)
		parent.custom_shape_transform = dsp_bone
		return dsp_bone

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
				# TODO: This should be shared code, because fingers are going to need it as well.

				# Make a parent for the first control.
				sliced_name = slice_name(fk_name)
				sliced_name[1] += "_Parent"
				fk_parent_name = make_name(*sliced_name)
				fk_parent_bone = self.bone_infos.bone(
					fk_parent_name, 
					fk_bone, 
					only_transform=True, 
					custom_shape_scale=1.1, 
					custom_shape = load_widget("FK_Limb"),
					**self.defaults
				)

				# Setup DSP bone for the new parent bone.
				self.create_dsp_bone(fk_parent_bone)

				# Parent FK bone to the new parent bone.
				fk_bone.parent = fk_parent_bone
				
				# Store in the beginning of the FK list.
				fk_bones.insert(0, fk_parent_bone)
			if i > 0:
				# Parent FK bone to previous FK bone.
				fk_bone.parent = fk_bones[-2]
			if i < 2:
				# Setup DSP bone for all but last bone.
				self.create_dsp_bone(fk_bone)
				pass
		
		# Create Hinge helper
		hng_name = self.base_bone.replace("ORG", "FK-HNG")	# Name it after the first bone in the chain.
		hng_bone = self.bone_infos.bone(
			hng_name, 
			fk_bones[0], 
			only_transform=True,
			**self.defaults,
			parent=None	# TODO: This gets overridden by Rigify, as it forces parentless bones to be parented to the "root" bone, which I'm not a big fan of.
		)
		fk_bones[0].parent = hng_bone

		con_arm = {
			"name" : "Armature",
			"targets" : [
				{
					"subtarget" : 'root'
				},
				{
					"subtarget" : self.bones.parent
				}
			]
		}

		hng_bone.add_constraint(self.obj, 'ARMATURE', con_arm)

		# Custom property tests.
		hng_prop_name = "fk_hinge_left_arm" #TODO: How do we know what limb it belongs to? Maybe we don't care, if we're storing the property locally on the relevant bone anyways.
		hinge_prop = hng_bone.custom_props[hng_prop_name] = CustomProp(hng_prop_name, default=0.0)
		hng_bone.custom_props_edit["edit_bone_property"] = CustomProp("edit bone property", default=1.2)

		drv1 = Driver()
		drv1.expression = "var"
		var1 = drv1.make_var("var")
		var1.type = 'SINGLE_PROP'
		var1.targets[0].id_type='OBJECT'
		var1.targets[0].id = self.obj
		var1.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (hng_bone.name, hng_prop_name)

		drv2 = Driver(drv1)
		drv2.expression = "1-var"

		data_path1 = 'pose.bones["%s"].constraints["%s"].targets[0].weight' %(hng_name, con_arm['name'])
		data_path2 = 'pose.bones["%s"].constraints["%s"].targets[1].weight' %(hng_name, con_arm['name'])
		
		hng_bone.drivers[data_path1] = drv1
		hng_bone.drivers[data_path2] = drv2

		# con_copyloc = self.make_constraint(hng, 'COPY_LOCATION')
		# con_copyloc.target = self.obj
		# con_copyloc.subtarget = self.bones.parent
		# con_copyloc.head_tail = 1
	
	def generate_bones(self):
		self.bones.everything = []
		for bd in self.bone_infos.bones:
			bone_name = self.new_bone(bd.name)

			self.bones.everything.append(bone_name)
	
	def parent_bones(self):
		for bd in self.bone_infos.bones:
			edit_bone = self.get_bone(bd.name)
			bd.write_edit_data(self.obj, edit_bone)
			edit_bone.parent = None
	
	def configure_bones(self):
		for bd in self.bone_infos.bones:
			pose_bone = self.get_bone(bd.name)
			bd.write_pose_data(pose_bone)

	#@stage.configure_bones
	def configure_fk(self):
		# TODO: Copy Transforms constraints with drivers for the ORG- bones.

		### Hinge Setup ###
		hng = self.bones.mch.fk_hinge
		con_arm = self.make_constraint(hng, 'ARMATURE')
		target1 = con_arm.targets.new()
		target2 = con_arm.targets.new()
		target1.target = target2.target = self.obj
		target1.subtarget = 'root'
		target2.subtarget = self.bones.parent

		# TODO: Create UI for custom property, and maybe store it elsewhere. 
		# I think I like it when all options are displayed all the time, but it can be limiting, 
		# if we're adding snapping options, and more per-limb options, it can easily become UI overload.

		prop_name = 'FK_Hinge'
		make_property(self.get_bone(self.base_bone), prop_name, 0.0)

		drv = Driver()
		drv.expression = "var"
		var = drv.make_var("var")
		var.type = 'SINGLE_PROP'
		var.targets[0].id_type='OBJECT'
		var.targets[0].id = self.obj
		var.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (self.base_bone, prop_name)

		drv.make_real(target1, "weight")

		drv.expression = "1-var"
		drv.make_real(target2, "weight")

		con_copyloc = self.make_constraint(hng, 'COPY_LOCATION')
		con_copyloc.target = self.obj
		con_copyloc.subtarget = self.bones.parent
		con_copyloc.head_tail = 1

	#@stage.generate_bones
	def generate_ik(self):
		# What we need:
		# IK Chain (equivalents to ORG, so 3 of these) - Make sure IK Stretch is enabled on first two, and they are parented and connected to each other.
		# IK Controls: Wrist, Wrist Parent(optional)
		# IK-STR- bone with its Limit Scale constraint set automagically somehow.
		# IK Pole target and line, somehow automagically placed.
		
		chain = self.bones.org.main
		# Create IK Chain (first two bones)
		for i, bn in enumerate(chain[:-1]):
			ik_name = bn.replace("ORG", "IK")
			self.copy_bone(bn, ik_name)
			ik_bone = self.get_bone(ik_name)

			if 'ik' not in self.bones.mch:
				self.bones.mch.ik = []
			
			if i > 0:
				ik_bone.parent = self.get_bone(self.bones.mch.ik[-1])
			else:
				ik_bone.parent = self.get_bone(self.bones.parent)
			
			self.bones.mch.ik.append(ik_name)

		# Create IK control(s) (Wrist/Ankle)
		self.bones.ctrl.ik = []
		bn = chain[-1]
		ik_name = bn.replace("ORG", "IK")
		self.copy_bone(bn, ik_name)
		ik_bone = self.get_bone(ik_name)
		self.bones.ctrl.ik.append(ik_name)
		if self.params.double_ik_control:
			sliced = slice_name(ik_name)
			sliced[0].append("P")
			parent_name = make_name(*sliced)
			self.copy_bone(ik_name, parent_name)
			self.bones.ctrl.ik.append(parent_name)
			parent_bone = self.get_bone(parent_name)
			ik_bone.parent = parent_bone
		
		# Stretch mechanism
		sliced = slice_name(ik_name)
		sliced[0].append("STR")
		str_name = self.bones.mch.ik_stretch = make_name(*sliced)
		self.copy_bone(self.bones.mch.ik[0], str_name)
		str_bone = self.get_bone(str_name)
		str_bone.tail = ik_bone.head

		sliced[0].append("TIP")
		tip_name = self.bones.mch.ik_stretch_tip = make_name(*sliced)
		self.copy_bone(ik_name, tip_name)
		tip_bone = self.get_bone(tip_name)
		tip_bone.parent = ik_bone

	#@stage.configure_bones
	def configure_ik(self):
		ik_bone_name = self.bones.mch.ik[-1]

		stretch = self.bones.mch.ik_stretch
		str_bone = self.get_bone(stretch)
		tip = self.bones.mch.ik_stretch_tip
		tip_bone = self.get_bone(self.bones.mch.ik_stretch_tip)

		for ik in self.bones.mch.ik:
			ik_bone = self.get_bone(ik)
			ik_bone.ik_stretch = 0.1

		con_ik = self.make_constraint(ik_bone_name, 'IK')
		con_ik.chain_count = 2
		con_ik.target = self.obj
		con_ik.subtarget = tip
		# TODO pole target.

		con_str = self.make_constraint(str_bone.name, 'STRETCH_TO')
		con_str.target = self.obj
		con_str.subtarget = self.bones.ctrl.ik[0]

		con_limitscale = self.make_constraint(str_bone.name, 'LIMIT_SCALE')
		con_limitscale.use_max_y = True
		con_limitscale.max_y = 1.05 # TODO: How to calculate this correctly?
		con_limitscale.owner_space = 'LOCAL'
		con_limitscale.influence = 0 # TODO: Put driver on this, driven by IK stretch toggle custom property.

		con_copyloc = self.make_constraint(tip, 'COPY_LOCATION')
		con_copyloc.target = self.obj
		con_copyloc.subtarget = stretch
		con_copyloc.head_tail = 1

	#@stage.generate_bones
	def generate_deform(self):
		chain = self.bones.org.main
		# What we need:
		# Two bendy deform bones per limb piece, surrounded by STR- controls. 
		# BBone properties are hooked up to the STR controls' transforms via drivers.
		# limb pieces connected in some funky way so that the bending of the second part doesn't affect the BBone of the first part.
		self.bones.deform = []
		self.bones.ctrl.str = []
		for i, bn in enumerate(chain):
			for i in range(0, self.params.deform_segments):
				## Deform
				def_name = bn.replace("ORG", "DEF")
				sliced = slice_name(def_name)
				sliced[1] += str(i+1)
				def_name = make_name(*sliced)

				self.copy_bone(bn, def_name)
				self.bones.deform.append(def_name)
				def_bone = self.get_bone(def_name)

				# Move head and tail into correct places
				org_bone = self.get_bone(bn)
				org_vec = org_bone.tail - org_bone.head
				unit = org_vec / self.params.deform_segments
				def_bone.head = org_bone.head + (unit * i)
				def_bone.tail = org_bone.head + (unit * (i+1))

				## Stretchy controls
				str_name = def_name.replace("DEF", "STR")
				self.copy_bone(def_name, str_name)
				self.bones.ctrl.str.append(str_name)
				# Create at the tail of the DEF bone we're currently iterating over. 
				# TODO This means the first bone(at the head of the first DEF) will need to be handled separately.
				str_bone = self.get_bone(str_name)
				str_bone.head = def_bone.tail
				str_bone.tail = str_bone.head + org_vec
				str_bone.length = 0.1


				# TODO: Create STR- controls with shapes, assign them as bbone tangent
				# drivers
				# parenting
				# constraints

	def generate_stretchy(self):
		pass

	#@stage.configure_bones
	def configure_rot_modes(self):
		for ctb in self.bones.ctrl.flatten():
			bone = self.get_bone(ctb)
			bone.rotation_mode='XYZ'

	#@stage.finalize
	def configure_display(self):
		# DSP bones
		for i, ik in enumerate(self.bones.ctrl.ik):
			ik_bone = self.get_bone(ik)
			ik_bone.custom_shape = load_widget("Hand_IK")
			ik_bone.custom_shape_scale = 1 + 0.1*i

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
		r = layout.row()
		r.prop(params, "type")
		r = layout.row()
		r.prop(params, "double_first_control")
		r = layout.row()
		r.prop(params, "double_ik_control")
		r = layout.row()
		r.prop(params, "display_middle")