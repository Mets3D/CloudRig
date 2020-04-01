import bpy
from bpy.props import BoolProperty, IntProperty, FloatProperty, StringProperty
from mathutils import Vector
from math import pi

from rigify.base_rig import stage

from ..definitions.driver import Driver
from .cloud_curve import CloudCurveRig
from .cloud_utils import make_name, slice_name

class CloudSplineIKRig(CloudCurveRig):
	"""CloudRig Spline IK chain."""

	description = "Create a bezier curve object to drive a bone chain with Spline IK constraint, controlled by Hooks."

	def initialize(self):
		"""Gather and validate data about the rig."""
		super().initialize()

		length = len(self.bones.org.main)
		subdiv = self.params.CR_subdivide_deform
		total = length * subdiv
		assert total <= 255, f"Error: Spline IK rig on {self.base_bone}: Trying to subdivide each bone {subdiv} times, in a bone chain of {length}, would result in {total} bones. The Spline IK constraint only supports a chain of 255 bones. You should lower the subdivision level"

		self.num_controls = len(self.bones.org.main)+1 if self.params.CR_match_hooks_to_bones else self.params.CR_num_hooks

	def create_curve(self):
		""" Create the Bezier Curve that will be used by the rig. """
		
		sum_bone_length = sum([b.length for b in self.org_chain])
		length_unit = sum_bone_length / (self.num_controls-1)
		handle_length = length_unit / self.params.CR_curve_handle_ratio
		
		# Find or create Bezier Curve object for this rig.
		curve_name = "CUR-" + self.generator.metarig.name.replace("META-", "")
		curve_name += "_" + (self.params.CR_hook_name if self.params.CR_hook_name!="" else self.base_bone.replace("ORG-", ""))
		curve_ob = bpy.data.objects.get(curve_name)
		if curve_ob:
			# There is no good way in the python API to delete curve points, so deleting the entire curve is necessary to allow us to generate with fewer controls than a previous generation.
			bpy.data.objects.remove(curve_ob)	# What's not so cool about this is that if anything in the scene was referencing this curve, that reference gets broken.

		org_mode = bpy.context.object.mode
		bpy.ops.curve.primitive_bezier_curve_add(radius=0.2, location=(0, 0, 0))

		curve_ob = bpy.context.view_layer.objects.active
		curve_ob.name = curve_name

		self.meta_base_bone.rigify_parameters.CR_target_curve_name = curve_ob.name

		self.curve_ob_name = curve_ob.name
		self.lock_transforms(curve_ob)

		# Place the first and last bezier points to the first and last bone.
		spline = curve_ob.data.splines[0]
		points = spline.bezier_points

		# Add the necessary number of curve points
		points.add( self.num_controls-len(points) )
		num_points = len(points)

		# Configure control points...
		for i in range(0, num_points):
			curve_ob = bpy.data.objects.get(curve_name)
			point_along_chain = i * length_unit
			spline = curve_ob.data.splines[0]
			points = spline.bezier_points
			p = points[i]

			# Place control points
			index = i if self.params.CR_match_hooks_to_bones else -1
			loc, direction = self.vector_along_bone_chain(self.org_chain, point_along_chain, index)
			p.co = loc
			p.handle_right = loc + handle_length * direction
			p.handle_left  = loc - handle_length * direction
		
		# Reset selection so Rigify can continue execution.
		bpy.context.view_layer.objects.active = self.obj
		self.obj.select_set(True)
		bpy.ops.object.mode_set(mode=org_mode)
		
		return curve_ob

	def create_def_chain(self):
		self.def_bones = []
		segments = self.params.CR_subdivide_deform

		count_def_bone = 0
		for org_bone in self.org_chain:
			for i in range(0, segments):
				## Create Deform bones
				def_name = self.params.CR_hook_name if self.params.CR_hook_name!="" else self.base_bone.replace("ORG-", "")
				def_name = "DEF-" + def_name + "_" + str(count_def_bone).zfill(3)
				count_def_bone += 1

				unit = org_bone.vec / segments
				def_bone = self.bone_infos.bone(
					name = def_name,
					source = org_bone,
					head = org_bone.head + (unit * i),
					tail = org_bone.head + (unit * (i+1)),
					roll = org_bone.roll,
					bbone_width = 0.03,
					hide_select	= self.mch_disable_select
				)

				if len(self.def_bones) > 0:
					def_bone.parent = self.def_bones[-1]
				else:
					def_bone.parent = self.org_chain[0]
				
				self.def_bones.append(def_bone)

	def create_curve_point_hooks(self):		
		sum_bone_length = sum([b.length for b in self.org_chain])
		length_unit = sum_bone_length / (self.num_controls-1)
		handle_length = length_unit / self.params.CR_curve_handle_ratio

		self.hooks = []
		
		for i in range(0, self.num_controls):
			point_along_chain = i * length_unit
			index = i if self.params.CR_match_hooks_to_bones else -1
			loc, direction = self.vector_along_bone_chain(self.org_chain, point_along_chain, index)

			self.hooks.append( 
				self.create_hooks(
					loc		  = loc, 
					loc_left  = loc - handle_length * direction, 
					loc_right = loc + handle_length * direction, 
					i		  = i
				)
			)

	def prepare_bones(self):
		super().prepare_bones()
		self.create_curve()
		self.create_def_chain()

	def configure_bones(self):
		# Add constraint to deform chain
		self.def_bones[-1].add_constraint(self.obj, 'SPLINE_IK', 
			use_curve_radius = True,
			chain_count		 = len(self.def_bones),
			target			 = bpy.data.objects.get(self.curve_ob_name),
			true_defaults	 = True
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
		
		# TODO: Implement cyclic parameter. Just need to pass it to the curve creation and the create_hooks() call, and it should work.
		# TODO: Alternatively or on top of that, implement "Create Curve Object" parameter. When disabled, we try using an existing curve. This would be useful when we want to arbitrarily modify the curve after generation. But moving the curve points around in edit mode would not be supported!

		params.CR_show_spline_ik_settings = BoolProperty(name="Spline IK Rig")
		params.CR_match_hooks_to_bones = BoolProperty(
			 name		 = "Match Controls to Bones"
			,description = "Hook controls will be created at each bone, instead of being equally distributed across the length of the chain"
			,default	 = True
		)
		params.CR_curve_handle_ratio = FloatProperty(
			 name		 = "Curve Handle Length Ratio"
			,description = "Increasing this will result in shorter curve handles, resulting in a sharper curve"
			,default	 = 2.5
		)
		params.CR_num_hooks = IntProperty(
			 name		 = "Number of Hooks"
			,description = "Number of controls that will be spaced out evenly across the entire chain"
			,default	 = 3
			,min		 = 3
			,max		 = 99
		)
		params.CR_subdivide_deform = IntProperty(
			 name="Subdivide bones"
			,description="For each original bone, create this many deform bones in the spline chain (Bendy Bones do not work well with Spline IK, so we create real bones) NOTE: Spline IK only supports 255 bones in the chain"
			,default=3
			,min=3
			,max=99
		)

	@classmethod
	def parameters_ui(cls, layout, params):
		""" Create the ui for the rig parameters.
		"""
		ui_rows = super().parameters_ui(layout, params)
		ui_rows['target_curve'].enabled=False

		icon = 'TRIA_DOWN' if params.CR_show_spline_ik_settings else 'TRIA_RIGHT'
		layout.prop(params, "CR_show_spline_ik_settings", toggle=True, icon=icon)
		if not params.CR_show_spline_ik_settings: return

		layout.prop(params, "CR_subdivide_deform")
		layout.prop(params, "CR_curve_handle_ratio")

		layout.prop(params, "CR_match_hooks_to_bones")	# TODO: When this is false, the directions of the curve points and bones don't match, and both of them are unsatisfactory. It would be nice if we would interpolate between the direction of the two bones, using length_remaining/bone.length as a factor, or something similar to that.
		if not params.CR_match_hooks_to_bones:
			layout.prop(params, "CR_num_hooks")
		
		return ui_rows

class Rig(CloudSplineIKRig):
	pass

def create_sample(obj):
    # generated by rigify.utils.write_metarig
    bpy.ops.object.mode_set(mode='EDIT')
    arm = obj.data

    bones = {}

    bone = arm.edit_bones.new('Cable_1')
    bone.head = 0.0000, 0.0000, 0.0000
    bone.tail = 0.0000, -0.5649, 0.0000
    bone.roll = -3.1416
    bone.use_connect = False
    bone.bbone_x = 0.0399
    bone.bbone_z = 0.0399
    bone.head_radius = 0.0565
    bone.tail_radius = 0.0282
    bone.envelope_distance = 0.1412
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bones['Cable_1'] = bone.name
    bone = arm.edit_bones.new('Cable_2')
    bone.head = 0.0000, -0.5649, 0.0000
    bone.tail = 0.0000, -1.1299, 0.0000
    bone.roll = -3.1416
    bone.use_connect = True
    bone.bbone_x = 0.0399
    bone.bbone_z = 0.0399
    bone.head_radius = 0.0282
    bone.tail_radius = 0.0565
    bone.envelope_distance = 0.1412
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bone.parent = arm.edit_bones[bones['Cable_1']]
    bones['Cable_2'] = bone.name
    bone = arm.edit_bones.new('Cable_3')
    bone.head = 0.0000, -1.1299, 0.0000
    bone.tail = 0.0000, -1.6948, -0.0000
    bone.roll = -3.1416
    bone.use_connect = True
    bone.bbone_x = 0.0399
    bone.bbone_z = 0.0399
    bone.head_radius = 0.0565
    bone.tail_radius = 0.0565
    bone.envelope_distance = 0.1412
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bone.parent = arm.edit_bones[bones['Cable_2']]
    bones['Cable_3'] = bone.name
    bone = arm.edit_bones.new('Cable_4')
    bone.head = 0.0000, -1.6948, -0.0000
    bone.tail = 0.0000, -2.2598, 0.0000
    bone.roll = -3.1416
    bone.use_connect = True
    bone.bbone_x = 0.0399
    bone.bbone_z = 0.0399
    bone.head_radius = 0.0565
    bone.tail_radius = 0.0565
    bone.envelope_distance = 0.1412
    bone.envelope_weight = 1.0000
    bone.use_envelope_multiply = 0.0000
    bone.parent = arm.edit_bones[bones['Cable_3']]
    bones['Cable_4'] = bone.name

    bpy.ops.object.mode_set(mode='OBJECT')
    pbone = obj.pose.bones[bones['Cable_1']]
    pbone.rigify_type = 'cloud_spline_ik'
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    try:
        pbone.rigify_parameters.CR_double_root = ""
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_subdivide_deform = 10
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_controls_for_handles = True
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_show_spline_ik_settings = True
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_show_display_settings = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_curve_handle_ratio = 2.5
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_rotatable_handles = False
    except AttributeError:
        pass
    try:
        pbone.rigify_parameters.CR_hook_name = "Cable"
    except AttributeError:
        pass
    pbone = obj.pose.bones[bones['Cable_2']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['Cable_3']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'
    pbone = obj.pose.bones[bones['Cable_4']]
    pbone.rigify_type = ''
    pbone.lock_location = (False, False, False)
    pbone.lock_rotation = (False, False, False)
    pbone.lock_rotation_w = False
    pbone.lock_scale = (False, False, False)
    pbone.rotation_mode = 'QUATERNION'

    bpy.ops.object.mode_set(mode='EDIT')
    for bone in arm.edit_bones:
        bone.select = False
        bone.select_head = False
        bone.select_tail = False
    for b in bones:
        bone = arm.edit_bones[bones[b]]
        bone.select = True
        bone.select_head = True
        bone.select_tail = True
        arm.edit_bones.active = bone

    return bones
