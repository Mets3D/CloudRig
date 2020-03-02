import bpy
from bpy.props import *
from mathutils import *
from math import pi

from rigify.base_rig import stage

from ..definitions.driver import *
from .cloud_base import CloudBaseRig
from .cloud_utils import make_name, slice_name

class CloudSplineIKRig(CloudBaseRig):
	"""CloudRig Spline IK chain."""

	def initialize(self):
		"""Gather and validate data about the rig."""
		super().initialize()
		self.params.sharp_sections = False
		self.params.cap_control = True
		self.params.shape_key_helpers=False

	@stage.prepare_bones
	def prepare_spline_deform(self):
		self.def_bones = []
		segments = self.params.segments

		for org_bone in self.org_chain:
			for i in range(0, segments):
				## Create Deform bones
				def_name = org_bone.name.replace("ORG", "DEF")
				sliced = slice_name(def_name)
				number = str(i+1) if segments > 1 else ""
				def_name = make_name(sliced[0], sliced[1] + number, sliced[2])

				# org_bone = self.get_bone(org_name)
				# org_vec = org_bone.tail-org_bone.head
				unit = org_bone.vec / segments

				def_bone = self.bone_infos.bone(
					name = def_name,
					source = org_bone,
					head = org_bone.head + (unit * i),
					tail = org_bone.head + (unit * (i+1)),
					roll = org_bone.roll,
					# bbone_handle_type_start = 'TANGENT',
					# bbone_handle_type_end = 'TANGENT',
					# bbone_segments = bbone_segments,
					# inherit_scale = 'NONE',
				)

				if len(self.def_bones) > 0:
					def_bone.parent = self.def_bones[-1]
				else:
					def_bone.parent = self.org_chain[0]
				
				self.def_bones.append(def_bone)


	@stage.finalize
	def create_curve(self):
		# We want to create a curve that starts and ends where our bone chain does, but where are the intermittent curve points?
		# Where the intermittent bones are does not really matter. We just want to spread our curve points out equally along the curvature of the bones.
		# But what if the bones aren't dense enough to have a curvature? Do we want to account for that?
		# I guess let's say that for now, we do not.

		# Potential solution, also bringing bbones back: Sort of self-solving, actually. If STR- bones are owned by ORG, and ORG- bones will have the spline IK constraint... The STR- bones might be rotated in just the right way for the BBones to follow the spline IK curve?

		# Just find the sum of the lengths of the bones. Then divide that by num_controls to get where on the bones' length we want each control to sit.
		
		sum_bone_length = sum([b.length for b in self.org_chain])
		length_unit = sum_bone_length / (self.params.num_controls-1)
		
		# Find or create Bezier Curve object for this rig.
		curve_name = self.obj.name.replace("RIG-", "CUR-")
		curve_ob = bpy.data.objects.get(curve_name)
		if curve_ob:
			# There is no good way in the python API to delete curve points, so deleting the entire curve is necessary to allow us to generate with fewer controls than a previous generation.
			bpy.data.objects.remove(curve_ob)	# What's not so cool about this is that if anything in the scene was referencing this curve, that reference gets broken.

		bpy.ops.curve.primitive_bezier_curve_add(radius=0.2, location=(0, 0, 0))
		curve_ob = bpy.context.view_layer.objects.active
		curve_ob.name = curve_name

		# Place the first and last bezier points to the first and last bone.
		spline = curve_ob.data.splines[0]
		points = spline.bezier_points

		# Add the necessary number of curve points
		points.add( self.params.num_controls-len(points) )

		def fit_on_bone_chain(chain, length):
			"""On a bone chain, find the point a given length down the chain."""
			length_cumultative = 0
			for b in chain:
				if length_cumultative + b.length > length:
					length_remaining = length - length_cumultative
					return b.head + b.vec.normalized()*length_remaining
				else:
					length_cumultative += b.length
			return chain[-1].tail.copy()

		# Place the curve points along the bone chain.
		for i, p in enumerate(points):
			p.co = fit_on_bone_chain(self.org_chain, i*length_unit)
			print(p.co)

		# points[0].co = self.org_chain[0].head.copy()
		# points[1].co = self.org_chain[-1].tail.copy()

		# points[0].handle_right = points[0].co + self.org_chain[0].vec * 1 # TODO: Some length factor, based on length_unit probably.
		# points[0].handle_left = points[0].co - self.org_chain[0].vec * 1 # TODO: Some length factor, based on length_unit probably.
		# points[1].handle_right = points[1].co + self.org_chain[-1].vec
		# points[1].handle_left = points[1].co - self.org_chain[-1].vec
		# Then we iterate params.num_controls number of times.
			# We subdivide the curve with the first and "latest" curve point selected. In the first iteration, that's the last curve point, from then on, it's the curve point that was created in the previous iteration.
			# A single new curve point should be created and selected - save it to a list, 
		
		for p in points:
			p.radius = 0.2
			p.handle_left_type = 'ALIGNED'
			p.handle_right_type = 'ALIGNED'

		bpy.ops.object.mode_set(mode='OBJECT')
		bpy.context.view_layer.objects.active = self.obj
		self.obj.select_set(True)


	##############################
	# Parameters

	@classmethod
	def add_parameters(cls, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		super().add_parameters(params)
		
		params.num_controls = IntProperty(
			name="Number of controls",
			description="Number of controls that will be spaced out evenly across the entire chain",
			default=3,
			min=3
		)
		params.segments = IntProperty(
			name="Subdivide bones",
			description="For each original bone, create this many deform bones in the spline chain",
			default=3,
			min=3
		)

	@classmethod
	def parameters_ui(cls, layout, params):
		""" Create the ui for the rig parameters.
		"""
		super().parameters_ui(layout, params)

		layout.prop(params, "segments")
		layout.prop(params, "num_controls")

class Rig(CloudSplineIKRig):
	pass