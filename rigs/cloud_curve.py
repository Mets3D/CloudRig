import bpy
from bpy.props import BoolProperty, IntProperty, FloatProperty, StringProperty, PointerProperty
from mathutils import Vector
from math import pi

from rigify.base_rig import stage

from ..definitions.driver import Driver
from .cloud_base import CloudBaseRig
from .cloud_utils import make_name, slice_name

"""
Relationship and code sharing of Curve rig and Spline IK rig:

Goals:
- Spline IK should not lose functionality.
- Curve rig should be able to rig a pre-existing curve.
    - Should it be able to create a curve though, if needed? :thinking: Nah, not sure I see the point.
    - UI for curve pointerproperty needs to be disabled for Spline IK though, since that wouldn't work with a pre-existing curve, I think.

- Code for creating hooks for a single curve point and its handles should probably be split off... Only issue is, in the case of Spline IK, this happens before the curve exists. Hmm...

So, the Curve rig will only create hooks. It will not create, or require, or support, a chain of deform bones!
The Spline IK rig on the other hand, while also creating hooks, will require an existing chain of deform bones(and create more bones along the chain, as needed)

The biggest problem is this: For Spline IK, the curve setup code relies on the bones already existing.
For the Curve rig, the bone creation code relies on the curve already existing.

But they are kindof the same code!

Actually, even for the Curve rig, the Hook modifier setup will have to happen after generate stage. So that should really be split up into a separate thing.

"""

class CloudCurveRig(CloudBaseRig):
	"""CloudRig Curve Control Rig."""

	description = "Create hook controls for an existing bezier curve."

	def initialize(self):
		"""Gather and validate data about the rig."""
		super().initialize()

	def create_curve_point_hooks(self, cp, i):
		""" Create hook controls for a given bezier curve point. """

		parent = self.base_bone
		if self.params.CR_hook_parent != "":
			parent = self.params.CR_hook_parent

		hook_name = self.params.CR_hook_name if self.params.CR_hook_name!="" else self.base_bone.replace("ORG-", "")
		hook_ctr = self.bone_infos.bone(
			name = "Hook_%s_%s" %(hook_name, str(i).zfill(2)),
			head = cp.co,
			tail = cp.handle_left,
			parent = parent,
			bone_group = "Spline IK Hooks",
		)

		hook_ctr.left_handle_control = None
		hook_ctr.right_handle_control = None
		
		if self.params.CR_controls_for_handles:
			hook_ctr.custom_shape = self.load_widget("Circle")

			if i > 0:				# Skip for first hook. #TODO: Unless circular curve!
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

		else:
			hook_ctr.custom_shape = self.load_widget("CurvePoint")
		return hook_ctr

	# @stage.prepare_bones
	def do_stuff(self):
		curve_ob = self.params.CR_target_curve
		spline = curve_ob.data.splines[0]	# For now we only support a single spline per curve.

		for i, cp in enumerate(spline.bezier_points):
			hooks = self.create_curve_point_hooks(cp, i)

	def configure_bones(self):
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

		curve_poll = lambda self, obj: obj.type=='CURVE'
		params.CR_target_curve = PointerProperty(type=bpy.types.Object, name="Curve", poll=curve_poll)	# TODO: This results in warnings and errors in the console, but it shouldn't. Poll function causes Rigify to detect it as being re-defined, when it isn't. And when the UI is disabled, there's some ID user decrement error...? Doesn't seem to cause any issues though. 

	@classmethod
	def parameters_ui(cls, layout, params):
		""" Create the ui for the rig parameters.
		"""
		ui_rows = super().parameters_ui(layout, params)

		icon = 'TRIA_DOWN' if params.CR_show_curve_rig_settings else 'TRIA_RIGHT'
		layout.prop(params, "CR_show_curve_rig_settings", toggle=True, icon=icon)
		if not params.CR_show_curve_rig_settings: return

		target_curve_row = layout.row()
		ui_rows['target_curve'] = target_curve_row
		target_curve_row.prop(params, "CR_target_curve")
		layout.prop(params, "CR_hook_name")
		layout.prop(params, "CR_hook_parent")
		layout.prop(params, "CR_controls_for_handles")
		if params.CR_controls_for_handles:
			layout.prop(params, "CR_rotatable_handles")
		
		return ui_rows

class Rig(CloudCurveRig):
	pass