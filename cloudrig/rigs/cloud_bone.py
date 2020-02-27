from rigify.base_rig import BaseRig, stage

class CloudBoneRig(BaseRig):
	
	def find_org_bones(self, bone):
		"""Populate self.bones.org."""
		return BoneDict(
			main=[bone.name],
		)
	
	def initialize(self):
		super().initialize()
	
	##############################
	# Parameters

	@classmethod
	def add_parameters(self, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		super().add_parameters(params)

		params.constraints_additive = BoolProperty(
			name="Additive Constraints",
			description="Add the constraints of this bone to the generated bone's constraints. When disabled, we replace the constraints instead (even when there aren't any)",
			default=True
		)

		params.tweak_existing = BoolProperty(
			name="Tweak Existing",
			description="Instead of creating any new bones in the generated rig, try to find a bone with the same name as this, and modify it",
			default=True
		)

		# These parameters are valid when tweak_existing==True
		params.transforms = BoolProperty(
			name="Affect Transforms",
			description="Replace the matching generated bone's transforms with this bone's transforms", # TODO: An idea: when this is False, let the generation script affect the metarig - and move this bone, to where it is in the generated rig.
			default=False
		)
		params.transform_locks = BoolProperty(
			name="Affect Locks",
			description="Replace the matching generated bone's transform locks with this bone's transform locks",
			default=False
		)
		params.bone_shape = BoolProperty(
			name="Affect Bone Shape",
			description = "Replace the matching generated bone's shape with this bone's shape",
			default=False
		)
		params.bone_group = BoolProperty(
			name="Bone Group",
			description="When not an empty string, ensure and assign this group to the generated bone",
			default=False
		)
		params.layers = BoolProperty(
			name="Affect Layers",
			description="Set the generated bone's layers to this bone's layers",
			default=False
		)

		# These parameters are valid when tweak_existing==False
		params.deform = BoolProperty(
			name="Create Deform Bone",
			default=True
		)

	@classmethod
	def parameters_ui(self, layout, params):
		"""Create the ui for the rig parameters."""
		super().parameters_ui(layout, params)

		layout.prop(params, "constraints_additive")
		layout.prop(params, "tweak_existing")
		if self.params.tweak_existing:
			layout.prop(params, "transforms")
			layout.prop(params, "transform_locks")
			layout.prop(params, "bone_shape")
			layout.prop(params, "bone_group")
			layout.prop(params, "layers")
		else:
			layout.prop(params, "deform")


class Rig(CloudBoneRig):
	pass