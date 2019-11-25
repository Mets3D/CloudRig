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
from mets_tools.armature_nodes.driver import *

from rigify.utils.layers import DEF_LAYER
from rigify.utils.errors import MetarigError
from rigify.utils.rig import connected_children_names
from rigify.utils.naming import make_derived_name
from rigify.utils.widgets_basic import create_bone_widget
from rigify.utils.bones import BoneDict, BoneUtilityMixin, put_bone
from rigify.utils.misc import map_list
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

		self.bones.parent = self.get_bone(self.base_bone).parent.name
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
		# Let's create a root bone for the rig, for giggles and sanity.
		# TODO: This might've been pointless. We'll keep it around for now.
		# root_name = "Root_Arm" if self.params.type=='ARM' else "Root_Leg"
		# root_name = make_name( base=root_name, suffixes=slice_name(self.base_bone)[2] )
		# self.bones.ctrl.root = self.copy_bone(self.base_bone, root_name)
		# root_bone = self.get_bone(self.bones.ctrl.root)
		# root_bone.parent = self.get_bone(self.base_bone).parent

		self.generate_fk(self.bones.org.main)
		self.generate_ik(self.bones.org.main)
		self.generate_stretchy(self.bones.org.main)
		self.generate_deform(self.bones.org.main)

	def generate_ik(self, chain):
		# What we need:
		# IK Chain (equivalents to ORG, so 3 of these) - Make sure IK Stretch is enabled on first two, and they are parented and connected to each other.
		# IK Controls: Wrist, Wrist Parent(optional)
		# IK-STR- bone with its Limit Scale constraint set automagically somehow.
		# IK Pole target and line, somehow automagically placed.
		
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


	def generate_fk(self, chain):
		for i, bn in enumerate(chain):
			fk_name = bn.replace("ORG", "FK")
			self.copy_bone(bn, fk_name)
			fk_bone = self.get_bone(fk_name)

			if 'fk' not in self.bones.ctrl:
				self.bones.ctrl.fk = []
			self.bones.ctrl.fk.append(fk_name)

			if i == 0 and self.params.double_first_control:
				# Make a parent for the first control. TODO: This should be shared code.
				sliced_name = slice_name(fk_name)
				sliced_name[1] += "_Parent"
				fk_parent_name = make_name(*sliced_name)
				self.copy_bone(fk_name, fk_parent_name)

				# Parent FK bone to the new parent bone.
				fk_parent_bone = self.get_bone(fk_parent_name)
				fk_bone.parent = fk_parent_bone

				# Setup DSP bone for the new parent bone.
				self.create_dsp_bone(fk_parent_bone)
				
				# Store in the beginning of the FK list.
				self.bones.ctrl.fk.insert(0, fk_parent_name)
			if i > 0:
				# Parent FK bone to previous FK bone.
				parent_bone = self.get_bone(self.bones.ctrl.fk[-2])
				fk_bone.parent = parent_bone

			if i < 2:
				# Setup DSP bone for all but last bone.
				self.create_dsp_bone(fk_bone)
		
		# Create Hinge helper
		fk_name = self.bones.ctrl.fk[0]
		fk_bone = self.get_bone(fk_name)
		hng_name = "HNG-"+fk_name
		self.bones.mch.fk_hinge = self.copy_bone(fk_name, hng_name)
		hng_bone = self.get_bone(hng_name)
		fk_bone.parent = hng_bone
		#hng_bone.parent = self.get_bone(self.bones.ctrl.root)

	def generate_stretchy(self, chain):
		pass

	def generate_deform(self, chain):
		pass

	@stage.configure_bones
	def configure_rot_modes(self):
		for ctb in self.bones.ctrl.flatten():
			bone = self.get_bone(ctb)
			bone.rotation_mode='XYZ'
	
	@stage.configure_bones
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

	@stage.configure_bones
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

	@stage.finalize
	def configure_display(self):
		# DSP bones
		for i, fk_name in enumerate(self.bones.ctrl.fk):
			fk_bone = self.get_bone(fk_name)
			fk_bone.custom_shape = load_widget("FK_Limb")
			if self.params.display_middle:
				try:
					dsp_name = "DSP-"+fk_name
					dsp_bone = self.get_bone(dsp_name)
					dsp_bone.bone.bbone_x = dsp_bone.bone.bbone_z = 0.05	# For some reason this can apparently only be set from finalize??
					if i != len(self.bones.ctrl.fk):
						fk_bone.custom_shape_transform = dsp_bone
				except MetarigError: 
					# If bone was not found, do nothing.
					pass

			if i == 0 and self.params.double_first_control:
				fk_bone.custom_shape_scale = 1.1
		
		for i, ik in enumerate(self.bones.ctrl.ik):
			ik_bone = self.get_bone(ik)
			ik_bone.custom_shape = load_widget("Hand_IK")
			ik_bone.custom_shape_scale = 1 + 0.1*i
		
		# root_bone = self.get_bone(self.bones.ctrl.root)
		# root_bone.custom_shape = load_widget("Cube")
		# root_bone.custom_shape_scale = 0.5

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
		print(".......add params")
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