import bpy
from bpy.props import BoolProperty, IntProperty, FloatProperty, StringProperty, PointerProperty
from mathutils import Vector, Matrix

from rigify.base_rig import stage

from ...definitions.driver import Driver
from ..cloud_curve import CloudCurveRig
from ..cloud_utils import make_name, slice_name

class SettlerMouthRig(CloudCurveRig):
	"""A Curve-based control rig specifically for the Settlers project. 
	This extends the CloudCurve rig, but targets two curves instead of one,
	and also has a target for a mesh to Shrinkwrap to,
	and adds some custom properties and drivers to control the shrinkwrap strength."""

	def shrinkwrap_bones(self, bones, target_ob):
		assert target_ob, f"Error: Could not find shrinkwrap target: {target_ob}"
		
		for b in bones:
			hooks = [b]
			sub_hooks = ['left_handle_control', 'right_handle_control']
			for attrib in sub_hooks:
				if hasattr(b, attrib):
					hooks.append(getattr(b, attrib))
			
			for hook in hooks:
				hook.add_constraint(self.obj, 'SHRINKWRAP',
					target = target_ob,
					distance = 0.01,
					shrinkwrap_type = 'TARGET_PROJECT'
				)
				# Not sure if this will work, but we need to ensure shrinkwrap is the first constraint.
				hook.constraints = hook.constraints[-1:] + hook.constraints[:-1]
				# TODO some driver on Influence or so.

	def prepare_bones(self):
		super().prepare_bones()
		self.org_pose = self.obj.data.pose_position
		if self.params.SETTLERS_shrinkwrap_target:
			self.obj.data.pose_position = 'REST'
			self.shrinkwrap_bones(self.hooks, self.params.SETTLERS_shrinkwrap_target)

	def configure_bones(self):
		if self.params.SETTLERS_target_curve:
			self.setup_curve(self.hooks, self.params.SETTLERS_target_curve)

		super().configure_bones()

		self.obj.data.pose_position = self.org_pose

	##############################
	# Parameters

	@classmethod
	def add_parameters(cls, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		super().add_parameters(params)
		
		params.SETTLERS_mouth_settings = BoolProperty(name="Mouth Rig")
		params.SETTLERS_target_curve = PointerProperty(
			type=bpy.types.Object,
			name="Curve 2", 
			description="A second curve that will also be hooked to the hook controls. This should be identical to the first curve, just used for a different purpose")
		params.SETTLERS_shrinkwrap_target = PointerProperty(type=bpy.types.Object, name="Shrinkwrap Object")

	@classmethod
	def cloud_params_ui(cls, layout, params):
		""" Create the ui for the rig parameters.
		"""
		ui_rows = super().cloud_params_ui(layout, params)

		icon = 'TRIA_DOWN' if params.SETTLERS_mouth_settings else 'TRIA_RIGHT'
		layout.prop(params, "SETTLERS_mouth_settings", toggle=True, icon=icon)
		if not params.SETTLERS_mouth_settings: return ui_rows

		layout.prop(params, "SETTLERS_target_curve")
		layout.prop(params, "SETTLERS_shrinkwrap_target")
		
		return ui_rows


class Rig(SettlerMouthRig):
	pass