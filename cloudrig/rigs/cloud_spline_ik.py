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

	def fit_on_bone_chain(self, chain, length, index=-1):
		"""On a bone chain, find the point a given length down the chain. Return its position and direction."""
		if index > -1:
			# Instead of using bone length, simply return the location and direction of a bone at a given index.
			
			# If the index is too high, return the tail of the bone.
			if index >= len(chain):
				b = chain[-1]
				return (b.tail.copy(), b.vec.normalized())
			
			b = chain[index]
			direction = b.vec.normalized()

			if index > 0:
				prev_bone = chain[index-1]
				direction = (b.vec + prev_bone.vec)#.normalized()
			return (b.head.copy(), direction)
		
		
		length_cumultative = 0
		for b in chain:
			if length_cumultative + b.length > length:
				length_remaining = length - length_cumultative
				direction = b.vec.normalized()
				loc = b.head + direction * length_remaining
				return (loc, direction)
			else:
				length_cumultative += b.length
		
		length_remaining = length - length_cumultative
		direction = chain[-1].vec.normalized()
		loc = chain[-1].tail + direction * length_remaining
		return (loc, direction)

	@stage.prepare_bones
	def create_def_chain(self):
		self.def_bones = []
		segments = self.params.segments

		for org_bone in self.org_chain:
			for i in range(0, segments):
				## Create Deform bones
				def_name = org_bone.name.replace("ORG", "DEF")
				sliced = slice_name(def_name)
				number = str(i+1) if segments > 1 else ""
				def_name = make_name(sliced[0], sliced[1] + number, sliced[2])

				unit = org_bone.vec / segments

				def_bone = self.bone_infos.bone(
					name = def_name,
					source = org_bone,
					head = org_bone.head + (unit * i),
					tail = org_bone.head + (unit * (i+1)),
					roll = org_bone.roll,
				)

				if len(self.def_bones) > 0:
					def_bone.parent = self.def_bones[-1]
				else:
					def_bone.parent = self.org_chain[0]
				
				self.def_bones.append(def_bone)

	@stage.prepare_bones
	def create_hook_controls(self):
		sum_bone_length = sum([b.length for b in self.org_chain])
		num_controls = len(self.org_chain)+1 if self.params.match_controls_to_bones else self.params.num_controls
		length_unit = sum_bone_length / (num_controls-1)

		self.hook_bones = []
		for i in range(0, num_controls):
			point_along_chain = i * length_unit
			index = i if self.params.match_controls_to_bones else -1
			loc, direction = self.fit_on_bone_chain(self.org_chain, point_along_chain, index)
			hook_ctr = self.bone_infos.bone(
				name = "Hook_" + str(i).zfill(2),
				head = loc,
				tail = loc + direction*self.scale,
				custom_shape = self.load_widget("CurveHandle")
			)
			self.hook_bones.append(hook_ctr)

	def create_curve(self):
		sum_bone_length = sum([b.length for b in self.org_chain])
		num_controls = len(self.org_chain)+1 if self.params.match_controls_to_bones else self.params.num_controls
		length_unit = sum_bone_length / (num_controls-1)
		handle_length = length_unit / self.params.curve_handle_ratio
		
		# Find or create Bezier Curve object for this rig.
		curve_name = self.obj.name.replace("RIG-", "CUR-")
		curve_ob = bpy.data.objects.get(curve_name)
		if curve_ob:
			# There is no good way in the python API to delete curve points, so deleting the entire curve is necessary to allow us to generate with fewer controls than a previous generation.
			bpy.data.objects.remove(curve_ob)	# What's not so cool about this is that if anything in the scene was referencing this curve, that reference gets broken.

		bpy.ops.curve.primitive_bezier_curve_add(radius=0.2, location=(0, 0, 0))
		self.obj.select_set(True)

		bpy.ops.object.mode_set(mode='EDIT')
		bpy.ops.curve.select_all(action='DESELECT')
		self.curve = curve_ob = bpy.context.view_layer.objects.active
		curve_ob.name = curve_name
		# TODO: move this to a util function, lock_transforms(...)
		curve_ob.lock_location = [True, True, True]
		curve_ob.lock_rotation = [True, True, True]
		curve_ob.lock_scale = [True, True, True]
		curve_ob.lock_rotation_w = True
		# TODO: parent curve object to rig object?

		# Place the first and last bezier points to the first and last bone.
		spline = curve_ob.data.splines[0]
		points = spline.bezier_points

		# Add the necessary number of curve points
		points.add( num_controls-len(points) )

		# Configure control points...
		for i, p in enumerate(points):
			point_along_chain = i * length_unit

			# p.handle_left_type = 'ALIGNED'
			# p.handle_right_type = 'ALIGNED'

			# Place control points
			index = i if self.params.match_controls_to_bones else -1
			loc, direction = self.fit_on_bone_chain(self.org_chain, point_along_chain, index)
			p.co = loc
			p.handle_right = loc + handle_length*direction
			p.handle_left  = loc - handle_length*direction

			p.select_control_point = True
			p.select_left_handle = True
			p.select_right_handle = True

			# Set active bone
			hook_b = self.obj.data.bones.get(self.hook_bones[i].name)
			self.obj.data.bones.active = hook_b

			# Add hook
			bpy.ops.object.hook_add_selob(use_bone=True)

			# Add radius driver
			D = p.driver_add("radius")
			driver = D.driver

			driver.expression = "var"
			my_var = driver.variables.new()
			my_var.name = "var"
			my_var.type = 'TRANSFORMS'
			
			var_tgt = my_var.targets[0]
			var_tgt.id = self.obj
			var_tgt.transform_space = 'LOCAL_SPACE'
			var_tgt.transform_type = 'SCALE_X'
			var_tgt.bone_target = self.hook_bones[i].name

			# Deselect
			p.select_control_point = False
			p.select_left_handle = False
			p.select_right_handle = False


		bpy.ops.object.mode_set(mode='OBJECT')
		bpy.context.scene.collection.objects.unlink(curve_ob)
		self.generator.collection.objects.link(curve_ob)
		curve_ob.hide_viewport=True
		bpy.context.view_layer.objects.active = self.obj
		self.obj.select_set(True)

	def configure_bones(self):
		self.create_curve()

		# Add constraint to deform chain
		self.def_bones[-1].add_constraint(self.obj, 'SPLINE_IK', 
			use_curve_radius=True,
			chain_count=len(self.def_bones),
			target=self.curve,
			true_defaults=True
		)

		super().configure_bones()

	##############################
	# Parameters

	@classmethod
	def add_parameters(cls, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		super().add_parameters(params)
		
		params.match_controls_to_bones = BoolProperty(
			name="Match Controls to Bones",
			description="Hook controls will be created at each bone, instead of being equally distributed across the length of the chain",
			default=True
		)
		params.controls_for_handles = BoolProperty(
			name="Controls for Handles",
			description="For every curve point control, create two children that control the handles of that curve point.",
			default=False
		)
		params.curve_handle_ratio = FloatProperty(
			name="Curve Handle Length Ratio",
			description="Increasing this will result in shorter curve handles, resulting in a sharper curve.",
			default=3.0,
		)
		params.num_controls = IntProperty(
			name="Number of controls",
			description="Number of controls that will be spaced out evenly across the entire chain",
			default=3,
			min=3,
			max=99
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
		layout.prop(params, "curve_handle_ratio")

		layout.prop(params, "controls_for_handles")	# TODO implement this.

		layout.prop(params, "match_controls_to_bones")
		if not params.match_controls_to_bones:
			layout.prop(params, "num_controls")

class Rig(CloudSplineIKRig):
	pass