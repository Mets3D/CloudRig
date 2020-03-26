import bpy, os
from bpy.props import BoolProperty, FloatProperty
from mathutils import Vector

from rigify.base_rig import BaseRig, stage

from ..definitions.driver import Driver
from ..definitions.bone import BoneInfoContainer
from .. import layers
from .cloud_utils import CloudUtilities

class CloudBaseRig(BaseRig, CloudUtilities):
	"""Base for all CloudRig rigs."""

	def find_org_bones(self, bone):
		"""Populate self.bones.org."""
		from rigify.utils.bones import BoneDict
		from rigify.utils.rig import connected_children_names

		return BoneDict(
			main=[bone.name] + connected_children_names(self.obj, bone.name),
		)

	def initialize(self):
		super().initialize()
		"""Gather and validate data about the rig."""
		self.generator_params = self.generator.metarig.data
		self.meta_base_bone = self.generator.metarig.pose.bones.get(self.base_bone.replace("ORG-", ""))
		
		self.parent_candidates = {}

		# Wipe any existing bone groups from the generated rig.	# TODO: Right now, every rig element nukes all the bone groups created by rig elements that generated before it, and then re-creates them. This could use smarter handling.
		for bone_group in self.obj.pose.bone_groups:
			self.obj.pose.bone_groups.remove(bone_group)

		self.script_id = bpy.path.basename(bpy.data.filepath).split(".")[0]
		if self.script_id=="":
			assert False, "Error: Save your file before generating."

		# Determine rig scale by armature height.
		self.scale = max(self.generator.metarig.dimensions)/10
		# Slap user-provided multiplier on top. TODO: Generator parameter? Or just remove this altogether, it seems superfluous. At least we never use it.
		self.display_scale = self.params.CR_display_scale * self.scale

		# TODO: Generator parameter.
		self.mch_disable_select = False

		self.side_suffix = ""
		self.side_prefix = ""
		base_bone_name = self.slice_name(self.base_bone)
		if "L" in base_bone_name[2]:
			self.side_suffix = "L"
			self.side_prefix = "Left"
		elif "R" in base_bone_name[2]:
			self.side_suffix = "R"
			self.side_prefix = "Right"

		self.defaults = {
			"bbone_width" : 0.1,
			"rotation_mode" : "XYZ",
			#"use_custom_shape_bone_size" : False#True
		}
		# Bone Info container used for storing new bone info created by the script.
		self.bone_infos = BoneInfoContainer(self)
		
		# Keep track of created widgets, so we can add them to Rigify-created Widgets collection at the end.
		self.widgets = []

		parent = self.get_bone(self.base_bone).parent
		self.bones.parent = parent.name if parent else ""

		# TODO: This should get created when attempting to add a Custom Property to it, and no sooner! Ie. it shouldn't get created when it's not being used by the rig.
		# Properties bone and Custom Properties
		self.prop_bone = self.bone_infos.bone(
			name = "Properties_IKFK", 
			bone_group = 'Properties',
			custom_shape = self.load_widget("Cogwheel"),
			head = Vector((0, self.scale*2, 0)),
			tail = Vector((0, self.scale*4, 0)),
			bbone_width = 1/8
		)

		# Root bone
		self.root_bone = self.bone_infos.bone(
			name = "root",
			bone_group = 'Body: Main IK Controls',
			head = Vector((0, 0, 0)),
			tail = Vector((0, self.scale*5, 0)),
			bbone_width = 1/3,
			custom_shape = self.load_widget("Root"),
			custom_shape_scale = 1.5
		)
		self.register_parent(self.root_bone, "Root")
		if self.generator_params.cloudrig_double_root:
			self.root_parent = self.create_parent_bone(self.root_bone)
			self.root_parent.bone_group = 'Body: Main IK Controls Extra Parents'

		for k in self.obj.data.keys():
			if k in ['_RNA_UI', 'rig_id']: continue
			del self.obj.data[k]

		# TODO: Put this under a generator parameter
		self.obj.name = self.generator.metarig.name.replace("META", "RIG")
		self.generator.metarig.data.name = "Data_" + self.generator.metarig.name
		self.obj.data.name = "Data_" + self.obj.name
		self.obj.data['cloudrig'] = self.script_id

		# TODO: Put this under a generator parameter
		# If no layers are protected, protect all layers. Otherwise, we assume protected layers were set up manually in a previously generated rig, so we don't touch them.
		if list(self.obj.data.layers_protected) == [False]*32:
			self.obj.data.layers_protected = [True]*32
		
	@stage.prepare_bones
	def load_org_bones(self):
		# Load ORG bones into BoneInfo instances.
		self.org_chain = []

		for bn in self.bones.org.main:
			eb = self.get_bone(bn)
			eb.use_connect = False
			org_bi = self.bone_infos.bone(bn, eb, self.obj, hide_select=self.mch_disable_select)
			
			# Rigify discards the bbone scale values from the metarig, but I'd like to keep them for easy visual scaling.
			meta_org_name = eb.name.replace("ORG-", "")
			meta_org = self.generator.metarig.pose.bones.get(meta_org_name)
			org_bi._bbone_x = meta_org.bone.bbone_x
			org_bi._bbone_z = meta_org.bone.bbone_z

			self.org_chain.append(org_bi)

	def generate_bones(self):
		root_bone = self.get_bone("root")
		# root_bone.bbone_width = 1/10

		for bd in self.bone_infos.bones:
			if (
				bd.name not in self.obj.data.edit_bones and
				bd.name not in self.bones.flatten() and
				bd.name != 'root'
			):
				bone_name = self.copy_bone("root", bd.name)
				# bone_name = self.new_bone(bd.name) # new_bone() is currently bugged and doesn't register the new bone, so we use copy_bone instead.
	
	def parent_bones(self):
		for bd in self.bone_infos.bones:
			edit_bone = self.get_bone(bd.name)

			bd.write_edit_data(self.obj, edit_bone)
	
	def configure_bones(self):
		self.init_bone_groups()
		for bd in self.bone_infos.bones:
			pose_bone = None
			try:
				pose_bone = self.get_bone(bd.name)
			except:
				print(f"WARNING: BoneInfo wasn't created for some reason: {bd.name}")
				continue
			# Apply scaling
			if not bd.use_custom_shape_bone_size:
				bd.custom_shape_scale *= self.display_scale * bd.bbone_width * 10
			bd.write_pose_data(pose_bone)

	@stage.apply_bones
	def unparent_bones(self):
		# Rigify automatically parents bones that have no parent to the root bone.
		# This is fine, but we want to undo this when the bone has an Armature constraint, since such bones should never have a parent.
		# NOTE: This could be done via self.generator.disable_auto_parent(bone_name), but I prefer doing it this way.
		for eb in self.obj.data.edit_bones:
			pb = self.obj.pose.bones.get(eb.name)
			for c in pb.constraints:
				if c.type=='ARMATURE':
					eb.parent = None
					break

	def finalize(self):
		self.select_layers(layers.default_active_layers)

		# Set root bone layers
		root_bone = self.get_bone("root")
		layers.set_layers(root_bone.bone, [0, 1, 16, 17])

		# Nuke Rigify's generated root bone shape so it cannot be applied.
		root_shape = bpy.data.objects.get("WGT-"+self.obj.name+"_root")
		if root_shape:
			bpy.data.objects.remove(root_shape)

		self.obj.data['script'] = self.load_ui_script()

		# For some god-forsaken reason, this is the earliest point when we can set bbone_x and bbone_z.
		for b in self.obj.data.bones:
			bi = self.bone_infos.find(b.name)
			if not bi:
				# print("How come there's no BoneInfo for %s?" %b.name)	# TODO?
				continue
			b.bbone_x = bi._bbone_x
			b.bbone_z = bi._bbone_z

	@stage.finalize
	def organize_widgets(self):
		# Hijack the widget collection automatically created by Rigify.
		wgt_collection = self.generator.collection.children.get("Widgets")
		if not wgt_collection:
			# Try finding a "Widgets" collection next to the metarig.
			for c in self.generator.metarig.users_collection:
				wgt_collection = c.children.get("Widgets")
				if wgt_collection: break

		if not wgt_collection:
			# Try finding a "Widgets" collection next to the generated rig.
			for c in self.obj.users_collection:
				wgt_collection = c.children.get("Widgets")
				if wgt_collection: break

		if not wgt_collection:
			# Fall back to master collection.
			wgt_collection = bpy.context.scene.collection
		
		for wgt in self.widgets:
			if wgt.name not in wgt_collection.objects:
				wgt_collection.objects.link(wgt)

	@stage.finalize
	def configure_display(self):
		# Armature display settings
		self.obj.display_type = 'SOLID'
		self.obj.data.display_type = 'BBONE'

	@stage.finalize
	def transform_locks(self):
		# Rigify automatically locks transforms of bones whose names match this regex: "[A-Z][A-Z][A-Z]-"
		# We want to undo this... For now, we just don't want anything to be locked. In future, maybe lock based on bone groups. (TODO)
		for bd in self.bone_infos.bones:
			pb = self.obj.pose.bones.get(bd.name)
			if not pb: continue
			pb.lock_location = bd.lock_location
			pb.lock_rotation = bd.lock_rotation
			pb.lock_rotation_w = bd.lock_rotation_w
			pb.lock_scale = bd.lock_scale

	##############################
	# Parameters

	@classmethod
	def parameters_ui_display(cls, layout, params):
		""" A separate category for display-related parameters."""
		layout.prop(params, "CR_display_scale", text='Bone Shape Scale')

	@classmethod
	def add_parameters(cls, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		params.CR_show_display_settings = BoolProperty(name="Display")
		params.CR_display_scale = FloatProperty(
			 name		 = "Display Scale"
			,description = "Scale Bone Display Sizes"
			,default	 = 1
			,min		 = 0.1
			,max		 = 100
		)

	@classmethod
	def parameters_ui(cls, layout, params):
		""" Create the ui for the rig parameters.
		"""
		ui_rows = {}
		icon = 'TRIA_DOWN' if params.CR_show_display_settings else 'TRIA_RIGHT'
		layout.prop(params, "CR_show_display_settings", toggle=True, icon=icon)

		if params.CR_show_display_settings:
			cls.parameters_ui_display(layout.box(), params	)
		
		# We can return a dictionary of key:UILayout elements, in case we want to affect the UI layout of inherited rig elements.
		return ui_rows

# For testing purposes
# class Rig(CloudBaseRig):
# 	pass