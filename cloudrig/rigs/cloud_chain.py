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

class CloudChainRig(CloudBaseRig):
	"""CloudRig stretchy BBone chain."""

	def initialize(self):
		super().initialize()
		"""Gather and validate data about the rig."""

	@stage.prepare_bones
	def prepare_deform_and_stretch(self):
		chain = self.bones.org.main[:]
		# We refer to a full limb as a limb. (eg. Arm)
		# Each part of that limb is a section. (eg. Forearm)
		# And that section contains the bones. (eg. DEF-Forearm1)
		# The deform_segments parameter defines how many bones there are in each section.

		# Each DEF bbone is surrounded by an STR control on each end.
		# Each STR section's first and last bones act as a control for the bones inbetween them.
		
		### Create deform bones.
		def_sections = []
		for org_i, org_name in enumerate(chain):
			segments = self.params.deform_segments
			bbone_segments = self.params.bbone_segments
			def_section = []

			# Last bone shouldn't get segmented.
			if (org_i == len(chain)-1) and not self.params.cap_control:
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
			
				if self.params.sharp_sections:
					# First bone of the segment, but not the first bone of the chain.
					if i==0 and org_i != 0:
						def_bone.bbone_easein = 0
					# Last bone of the segment, but not the last bone of the chain.
					if i==segments-1 and org_i != len(chain)-1:
						def_bone.bbone_easeout = 0
				
				# Last bone of the chain.
				if (i==segments-1) and (org_i == len(chain)-1) and (not self.params.cap_control):
					def_bone.inherit_scale = 'FULL'	# This is not perfect - when trying to adjust the spline shape by scaling the STR control on local Y axis, it scales the last deform bone in a bad way.

				next_parent = def_bone.name
				def_section.append(def_bone)
			def_sections.append(def_section)

		def make_str_bone(def_bone, name=None, head=None, tail=None):
			if not name:
				name = def_bone.name.replace("DEF", "STR")
			if not head:
				head = def_bone.head
			if not tail:
				tail = def_bone.tail
			str_bone = self.bone_infos.bone(
				name = name,
				head = head,
				tail = tail,
				roll = def_bone.roll,
				custom_shape = self.load_widget("Sphere"),
				use_custom_shape_bone_size = False,
				custom_shape_scale = 0.4,
				bone_group = 'Body: STR - Stretch Controls',
				parent = chain[sec_i],
			)
			str_bone.scale(0.3)
			return str_bone

		### Create Stretch controls
		str_sections = []
		for sec_i, section in enumerate(def_sections):
			str_section = []
			for i, def_bone in enumerate(section):
				str_bone = make_str_bone(def_bone)
				if i==0:
					# Make first control bigger.
					str_bone.custom_shape_scale *= 1.3
				
				str_section.append(str_bone)
			str_sections.append(str_section)
		
		if self.params.cap_control:
			# Add final STR control.
			last_def = def_sections[-1][-1]
			sliced = slice_name(str_sections[-1][-1].name)
			sliced[0].append("TIP")
			str_name = make_name(*sliced)

			str_bone = make_str_bone(
				def_bone, 
				name = str_name, 
				head = def_bone.tail, 
				tail = def_bone.tail+def_bone.vec
			)
			str_bone.custom_shape_scale *= 1.3

			str_sections.append([str_bone])
	
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
					if (i==len(section)-1) and (sec_i==len(def_sections)-1) and (not self.params.cap_control): 
						# If this is also the last bone of the last section(eg. Wrist bone), don't do anything else, unless the Final Control option is enabled.
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
		super().add_parameters(params)

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
		params.sharp_sections = BoolProperty(
			name="Sharp Sections",
			description="BBone EaseIn/Out is set to 0 for controls connectiong two chain sections",
			default=True
		)
		# TODO: Not sure if this is a good idea yet. I guess we don't want to use this in cases where we want to connect another chain to this one.
		# Current use case idea is for the spine/head, where we want the final control for the head to exist. Also for a generic chain like a ponytail or a scarf.
		params.cap_control = BoolProperty(
			name="Final Control",
			description="Add the final control at the end of the chain (Turn off if you connect another chain to this one)",
			default=True
		)


	@classmethod
	def parameters_ui(self, layout, params):
		""" Create the ui for the rig parameters.
		"""
		super().parameters_ui(layout, params)

		layout.prop(params, "deform_segments")
		layout.prop(params, "bbone_segments")
		layout.prop(params, "sharp_sections")
		layout.prop(params, "cap_control")

class Rig(CloudChainRig):
	pass