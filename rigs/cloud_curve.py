import bpy
from bpy.props import BoolProperty, IntProperty, FloatProperty, StringProperty, PointerProperty
from mathutils import Vector, Matrix

from rigify.base_rig import stage

from ..definitions.driver import Driver
from .cloud_base import CloudBaseRig
from .cloud_utils import make_name, slice_name

class CloudCurveRig(CloudBaseRig):
	"""CloudRig Curve Control Rig."""

	description = "Create hook controls for an existing bezier curve."

	def initialize(self):
		"""Gather and validate data about the rig."""
		super().initialize()

		# assert self.params.CR_target_curve_name, f"Error: Curve Rig has no target curve object! Base bone: {self.base_bone}" #TODO: Having this here causes assertion for spline IK rigs...
		
		self.num_controls = len(self.bones.org.main)
		self.curve_ob_name = "Curve_" + self.base_bone
		if self.params.CR_target_curve_name!="":
			self.curve_ob_name = self.params.CR_target_curve_name

	def create_root(self):
		self.root_control = self.bone_infos.bone(
			name = self.base_bone.replace("ORG", "ROOT"),
			source = self.org_chain[0],
			bone_group = "Spline IK Hooks",
			use_custom_shape_bone_size = True,
			custom_shape = self.load_widget("Cube")
		)
		self.org_chain[0].parent = self.root_control

	def create_hooks(self, loc, loc_left, loc_right, i, cyclic=False):
		""" Create hook controls for a bezier curve point defined by three points (loc, loc_left, loc_right). """

		parent = self.base_bone
		if self.params.CR_hook_parent != "":
			parent = self.params.CR_hook_parent

		hook_name = self.params.CR_hook_name if self.params.CR_hook_name!="" else self.base_bone.replace("ORG-", "")
		hook_ctr = self.bone_infos.bone(
			name = f"Hook_{hook_name}_{str(i).zfill(2)}",
			head = loc,
			tail = loc_left,
			parent = parent,
			bone_group = "Spline IK Hooks",
			use_custom_shape_bone_size = True
		)

		hook_ctr.left_handle_control = None
		hook_ctr.right_handle_control = None
		handles = []
		
		if self.params.CR_controls_for_handles:
			hook_ctr.custom_shape = self.load_widget("Circle")

			if (i > 0) or cyclic:				# Skip for first hook. #TODO: Unless circular curve!
				handle_left_ctr = self.bone_infos.bone(
					name		 = f"Hook_L_{hook_name}_{str(i).zfill(2)}",
					head 		 = loc,
					tail 		 = loc_left,
					bone_group 	 = "Spline IK Handles",
					parent 		 = hook_ctr,
					custom_shape = self.load_widget("CurveHandle")
				)
				hook_ctr.left_handle_control = handle_left_ctr
				handles.append(handle_left_ctr)

			if (i < self.num_controls-1) or cyclic:	# Skip for last hook.
				handle_right_ctr = self.bone_infos.bone(
					name 		 = f"Hook_R_{hook_name}_{str(i).zfill(2)}",
					head 		 = loc,
					tail 		 = loc_right,
					bone_group 	 = "Spline IK Handles",
					parent 		 = hook_ctr,
					custom_shape = self.load_widget("CurveHandle")
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
		
		return hook_ctr

	def create_curve_point_hooks(self):
		curve_ob = bpy.data.objects.get(self.params.CR_target_curve_name)
		if not curve_ob: return

		# Function to convert a location vector in the curve's local space into world space.

		# For some reason this doesn't work when the curve object is parented to something, and we need it to be parented to the root bone kindof.
		
		worldspace = lambda loc: (curve_ob.matrix_world @ Matrix.Translation(loc)).to_translation()

		spline = curve_ob.data.splines[0]	# For now we only support a single spline per curve.
		self.hooks = []
		for i, cp in enumerate(spline.bezier_points):
			self.hooks.append(
				self.create_hooks(
					loc		  = worldspace(cp.co), 
					loc_left  = worldspace(cp.handle_left), 
					loc_right = worldspace(cp.handle_right), 
					i		  = i, 
					cyclic	  = spline.use_cyclic_u
				)
			)

	def prepare_bones(self):
		super().prepare_bones()
		self.create_root()
		self.create_curve_point_hooks()

	def add_hook(self, cp_i, boneinfo, main_handle=False, left_handle=False, right_handle=False):				
		""" Create a Hook modifier on the curve(active object, in edit mode), hooking the control point at a given index to a given bone. The bone must exist. """
		if not boneinfo: return
		bpy.ops.curve.select_all(action='DESELECT')

		# Workaround of T74888, can be removed once D7190 is in master. (Preferably wait until it's in a release build)
		curve_ob = bpy.data.objects.get(bpy.context.object.name)
		spline = curve_ob.data.splines[0]
		points = spline.bezier_points
		cp = points[cp_i]
		
		cp.select_control_point = main_handle
		cp.select_left_handle = left_handle
		cp.select_right_handle = right_handle

		# Set active bone
		bone = self.obj.data.bones.get(boneinfo.name)
		self.obj.data.bones.active = bone

		# If the hook modifier already exists, don't re-create it.
		mod = curve_ob.modifiers.get(boneinfo.name)
		if mod:
			return

		# Add hook
		old_modifiers = [m.name for m in curve_ob.modifiers]
		bpy.ops.object.hook_add_selob(use_bone=True)

		# Find and rename the newly added modifier.
		for m in curve_ob.modifiers:
			if m.name not in old_modifiers:
				m.name = boneinfo.name

	def setup_curve(self, hooks, curve_ob_name):
		""" Configure the Hook Modifiers for the curve. This requires switching object modes. 
		hooks: List of BoneInfo objects that were created with create_hooks().
		curve_ob: The curve object.
		Only single-spline curve is supported. That one spline must have the same number of control points as the number of hooks."""

		curve_ob = bpy.data.objects.get(curve_ob_name)
		assert curve_ob, f"Error: Curve object {curve_ob_name} doesn't exist for rig: {self.base_bone}"
		self.ensure_visible(curve_ob)
		bpy.ops.object.select_all(action='DESELECT')
		self.obj.select_set(True)
		bpy.context.view_layer.objects.active = self.obj
		curve_ob.select_set(True)
		bpy.context.view_layer.objects.active = curve_ob

		bpy.ops.object.mode_set(mode='EDIT')
		bpy.ops.curve.select_all(action='DESELECT')
		spline = curve_ob.data.splines[0]
		points = spline.bezier_points
		num_points = len(points)

		assert num_points == len(hooks), f"Error: Curve object {curve_ob_name} has {num_points} points, but {len(hooks)} hooks were passed."

		for i in range(0, num_points):
			hook_b = hooks[i]
			if not self.params.CR_controls_for_handles:
				self.add_hook(i, hook_b, main_handle=True, left_handle=True, right_handle=True)
			else:
				self.add_hook(i, hook_b, main_handle=True)
				self.add_hook(i, hook_b.left_handle_control, left_handle=True)
				self.add_hook(i, hook_b.right_handle_control, right_handle=True)

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
			var_tgt.bone_target = hooks[i].name

		# Reset selection so Rigify can continue execution.
		bpy.ops.object.mode_set(mode='OBJECT')
		self.restore_visible(curve_ob)
		bpy.context.view_layer.objects.active = self.obj
		self.obj.select_set(True)

	def configure_bones(self):
		self.setup_curve(self.hooks, self.curve_ob_name)

		super().configure_bones()

	##############################
	# Parameters

	@classmethod
	def add_parameters(cls, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		super().add_parameters(params)
		
		params.CR_show_curve_rig_settings = BoolProperty(name="Curve Rig")
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

		params.CR_target_curve_name = StringProperty(name="Curve")

	@classmethod
	def parameters_ui(cls, layout, params):
		""" Create the ui for the rig parameters.
		"""
		ui_rows = super().parameters_ui(layout, params)

		icon = 'TRIA_DOWN' if params.CR_show_curve_rig_settings else 'TRIA_RIGHT'
		layout.prop(params, "CR_show_curve_rig_settings", toggle=True, icon=icon)
		if not params.CR_show_curve_rig_settings: return ui_rows

		target_curve_row = layout.row()
		ui_rows['target_curve'] = target_curve_row
		target_curve_row.prop_search(params, "CR_target_curve_name", bpy.data, 'objects')
		layout.prop(params, "CR_hook_name")
		layout.prop(params, "CR_hook_parent")
		layout.prop(params, "CR_controls_for_handles")
		if params.CR_controls_for_handles:
			layout.prop(params, "CR_rotatable_handles")
		
		return ui_rows

class Rig(CloudCurveRig):
	pass