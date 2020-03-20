import bpy
from bpy.props import BoolProperty, IntProperty, FloatProperty, StringProperty
from mathutils import Vector
from math import pi

from rigify.base_rig import stage

from ..definitions.driver import Driver
from .cloud_base import CloudBaseRig
from .cloud_utils import make_name, slice_name

class CloudSplineIKRig(CloudBaseRig):
	"""CloudRig Spline IK chain."""

	def initialize(self):
		"""Gather and validate data about the rig."""
		super().initialize()

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
				direction = (b.vec + prev_bone.vec).normalized()
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

	@stage.prepare_bones
	def create_hook_controls(self):
		sum_bone_length = sum([b.length for b in self.org_chain])
		num_controls = len(self.org_chain)+1 if self.params.CR_match_hooks_to_bones else self.params.CR_num_hooks
		length_unit = sum_bone_length / (num_controls-1)
		handle_length = length_unit / self.params.CR_curve_handle_ratio

		self.hook_bones = []
		next_parent = self.bones.parent
		for i in range(0, num_controls):
			point_along_chain = i * length_unit
			index = i if self.params.CR_match_hooks_to_bones else -1
			loc, direction = self.fit_on_bone_chain(self.org_chain, point_along_chain, index)
			
			hook_name = self.params.CR_hook_name if self.params.CR_hook_name!="" else self.base_bone.replace("ORG-", "")
			hook_ctr = self.bone_infos.bone(
				name = "Hook_%s_%s" %(hook_name, str(i).zfill(2)),
				head = loc,
				tail = loc + direction*self.scale/10,
				parent = next_parent,
				bone_group = "Spline IK Hooks",
			)
			hook_ctr.left_handle_control = None
			hook_ctr.right_handle_control = None
			if self.params.CR_hook_parent != "":
				next_parent = self.params.CR_hook_parent
			if self.params.CR_controls_for_handles:
				hook_ctr.custom_shape = self.load_widget("Circle")
				handles = []

				if i > 0:				# Skip for first hook.
					handle_left_ctr = self.bone_infos.bone(
						name		 = "Hook_L_%s_%s" %(hook_name, str(i).zfill(2)),
						head 		 = loc,
						tail 		 = loc - handle_length * direction,
						bone_group 	 = "Spline IK Handles",
						parent 		 = hook_ctr,
						custom_shape = self.load_widget("CurveHandle"),
					)
					hook_ctr.left_handle_control = handle_left_ctr
					handles.append(handle_left_ctr)

				if i < num_controls-1:	# Skip for last hook.
					handle_right_ctr = self.bone_infos.bone(
						name 		 = "Hook_R_%s_%s" %(hook_name, str(i).zfill(2)),
						head 		 = loc,
						tail 		 = loc + handle_length * direction,
						bone_group 	 = "Spline IK Handles",
						parent 		 = hook_ctr,
						custom_shape = self.load_widget("CurveHandle"),
					)
					hook_ctr.right_handle_control = handle_right_ctr
					handles.append(handle_right_ctr)

				for handle in handles:
					handle.use_custom_shape_bone_size = True
					if self.params.CR_rotatable_handles:
						dsp_bone = self.create_dsp_bone(handle)
						dsp_bone.head = handle.tail.copy()
						dsp_bone.tail = handle.head.copy()

						self.lock_transforms(handle, loc=False, rot=False, scale=[True, False, True])

						dsp_bone.add_constraint(self.obj, 'DAMPED_TRACK', subtarget=hook_ctr.name)
						dsp_bone.add_constraint(self.obj, 'STRETCH_TO', subtarget=hook_ctr.name)
					else:
						head = handle.head.copy()
						handle.head = handle.tail.copy()
						handle.tail = head

						self.lock_transforms(handle, loc=False)

						handle.add_constraint(self.obj, 'DAMPED_TRACK', subtarget=hook_ctr.name)
						handle.add_constraint(self.obj, 'STRETCH_TO', subtarget=hook_ctr.name)

			else:
				hook_ctr.custom_shape = self.load_widget("CurvePoint")

			self.hook_bones.append(hook_ctr)

	def setup_curve(self):
		""" Create and configure the bezier curve that will be used by the rig."""

		sum_bone_length = sum([b.length for b in self.org_chain])
		num_controls = len(self.org_chain)+1 if self.params.CR_match_hooks_to_bones else self.params.CR_num_hooks
		length_unit = sum_bone_length / (num_controls-1)
		handle_length = length_unit / self.params.CR_curve_handle_ratio
		
		# Find or create Bezier Curve object for this rig.
		curve_name = "CUR-" + self.generator.metarig.name.replace("META-", "")
		curve_name += "_" + (self.params.CR_hook_name if self.params.CR_hook_name!="" else self.base_bone.replace("ORG-", ""))
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
		self.lock_transforms(curve_ob)

		# Place the first and last bezier points to the first and last bone.
		spline = curve_ob.data.splines[0]
		points = spline.bezier_points

		# Add the necessary number of curve points
		points.add( num_controls-len(points) )
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
			loc, direction = self.fit_on_bone_chain(self.org_chain, point_along_chain, index)
			p.co = loc
			p.handle_right = loc + handle_length * direction
			p.handle_left  = loc - handle_length * direction

			def add_hook(cp, boneinfo, main_handle=False, left_handle=False, right_handle=False):				
				if not boneinfo: return
				bpy.ops.curve.select_all(action='DESELECT')

				# Workaround of T74888, can be removed once D7190 is in master. (Preferably wait until it's in a release build)
				curve_ob = bpy.data.objects.get(curve_name)
				spline = curve_ob.data.splines[0]
				points = spline.bezier_points
				cp = points[i]

				cp.select_control_point = main_handle
				cp.select_left_handle = left_handle
				cp.select_right_handle = right_handle

				# Set active bone
				bone = self.obj.data.bones.get(boneinfo.name)
				self.obj.data.bones.active = bone

				# Add hook
				bpy.ops.object.hook_add_selob(use_bone=True)

			hook_b = self.hook_bones[i]
			if not self.params.CR_controls_for_handles:
				add_hook(p, hook_b, main_handle=True, left_handle=True, right_handle=True)
			else:
				add_hook(p, hook_b, main_handle=True)
				add_hook(p, hook_b.left_handle_control, left_handle=True)
				add_hook(p, hook_b.right_handle_control, right_handle=True)

			# Add radius driver
			D = curve_ob.data.driver_add(f"splines[0].bezier_points[{i}].radius")
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

		bpy.ops.object.mode_set(mode='OBJECT')

		# Collections and visibility
		if curve_ob.name not in self.generator.collection.objects:
			self.generator.collection.objects.link(curve_ob)
		for c in curve_ob.users_collection:
			if c == self.generator.collection: continue
			c.objects.unlink(curve_ob)
		curve_ob.hide_viewport=True

		# Reset selection so Rigify can continue execution.
		bpy.context.view_layer.objects.active = self.obj
		self.obj.select_set(True)

	def configure_bones(self):
		self.setup_curve()

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
		
		params.CR_show_spline_ik_settings = BoolProperty(name="Spline IK Rig")
		params.CR_hook_name = StringProperty(
			 name		 = "Custom Name"
			,description = "Used for naming control bones, deform bones and the curve object. If empty, use the base bone's name"
			,default	 = ""
		)
		params.CR_hook_parent = StringProperty(
			 name		 = "Custom Parent"
			,description = "If not empty, parent all hooks except the first one to a bone with this name"
			,default	 = ""
		)
		params.CR_match_hooks_to_bones = BoolProperty(
			 name		 = "Match Controls to Bones"
			,description = "Hook controls will be created at each bone, instead of being equally distributed across the length of the chain"
			,default	 = True
		)
		params.CR_controls_for_handles = BoolProperty(
			 name		 = "Controls for Handles"
			,description = "For every curve point control, create two children that control the handles of that curve point"
			,default	 = False
		)
		params.CR_rotatable_handles = BoolProperty(
			 name		 = "Rotatable Handles"
			,description = "Use a setup which allows handles to be rotated and scaled - Will behave oddly when rotation is done after translation"
			,default	 = False
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
		super().parameters_ui(layout, params)

		icon = 'TRIA_DOWN' if params.CR_show_spline_ik_settings else 'TRIA_RIGHT'
		layout.prop(params, "CR_show_spline_ik_settings", toggle=True, icon=icon)
		if not params.CR_show_spline_ik_settings: return

		layout.prop(params, "CR_hook_name")
		layout.prop(params, "CR_subdivide_deform")
		layout.prop(params, "CR_curve_handle_ratio")

		layout.prop(params, "CR_hook_parent")
		layout.prop(params, "CR_controls_for_handles")
		if params.CR_controls_for_handles:
			layout.prop(params, "CR_rotatable_handles")

		layout.prop(params, "CR_match_hooks_to_bones")	# TODO: When this is false, the directions of the curve points and bones don't match, and both of them are unsatisfactory. It would be nice if we would interpolate between the direction of the two bones, using length_remaining/bone.length as a factor, or something similar to that.
		if not params.CR_match_hooks_to_bones:
			layout.prop(params, "CR_num_hooks")

class Rig(CloudSplineIKRig):
	pass