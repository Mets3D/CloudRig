import bpy, os
from bpy.props import BoolProperty, FloatProperty
from mathutils import Vector

from rigify.base_rig import BaseRig, stage

from ..definitions.driver import Driver
from ..definitions.bone import BoneInfoContainer
from .cloud_utils import CloudUtilities
from .. import cloud_generator

class CloudBaseRig(BaseRig, CloudUtilities):
	"""Base for all CloudRig rigs."""

	description = "CloudRig Element (no description)"

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
		
		assert type(self.generator) == cloud_generator.CloudGenerator, "Error: CloudRig has wrong Generator type. CloudRig requires its own Generator class - Perhaps you're using bpy.ops.rigify_generate instead of bpy.ops.cloudrig_generate?"

		self.generator_params = self.generator.metarig.data

		self.mch_disable_select = not self.generator_params.cloudrig_mechanism_selectable
		
		self.meta_base_bone = self.generator.metarig.pose.bones.get(self.base_bone.replace("ORG-", ""))
		self.parent_candidates = {}
		self.ensure_bone_groups()

		# Determine rig scale by armature height.
		self.scale = max(self.generator.metarig.dimensions)/10

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
		# Bone Info container used for storing bones created by this rig element.
		self.bone_infos = BoneInfoContainer(self)
		
		# Keep track of created widgets, so we can add them to Rigify-created Widgets collection at the end.
		self.widgets = []

		parent = self.get_bone(self.base_bone).parent
		self.bones.parent = parent.name if parent else ""

		# Root bone TODO: This should be moved to generator code. However, that means the generator should have its own list of bone_infos. And how would that work?
		# Is that then the only list of bone_infos? That would mean any rig can access any bone as long as it knows its name, which would be interesting...
		# But it would also mean a rig no longer can differentiate between bones that belong to itself vs random bones from other rigs.
		# Not a big deal either way... probably worth a shot.
		if self.generator_params.cloudrig_create_root:
			self.root_bone = self.bone_infos.bone(
				name = "root",
				bone_group = self.group_root,
				head = Vector((0, 0, 0)),
				tail = Vector((0, self.scale*5, 0)),
				bbone_width = 1/3,
				custom_shape = self.load_widget("Root"),
				custom_shape_scale = 1.5
			)
			self.register_parent(self.root_bone, "Root")
			if self.generator_params.cloudrig_double_root:
				self.root_parent = self.create_parent_bone(self.root_bone)
				self.root_parent.bone_group = self.group_root_parent

		for k in self.obj.data.keys():
			if k in ['_RNA_UI', 'rig_id']: continue
			del self.obj.data[k]

		# TODO: Put this under a generator parameter
		# If no layers are protected, protect all layers. Otherwise, we assume protected layers were set up manually in a previously generated rig, so we don't touch them.
		if list(self.obj.data.layers_protected) == [False]*32:
			self.obj.data.layers_protected = [True]*32

	@property
	def prop_bone(self):
		""" Ensure that a Properties bone exists, and return it. """
		# This is a @property so that if it's never called(like in the case of very simple rigs), the properties bone is not created.
		prop_bone = self.bone_infos.bone(
			name = "Properties_IKFK", # TODO: Rename to just "Properties"... just don't want to do it mid-production.
			bone_group = self.group_root,
			custom_shape = self.load_widget("Cogwheel"),
			head = Vector((0, self.scale*2, 0)),
			tail = Vector((0, self.scale*4, 0)),
			bbone_width = 1/8
		)
		return prop_bone

	def ensure_bone_groups(self):
		""" Ensure bone groups that this rig needs. """
		IK_MAIN = 0
		IK_SECOND = 16
		self.group_root = self.generator.bone_groups.ensure(
			name = "Root Control"
			,layers = [IK_MAIN, IK_SECOND]
			,preset = 2
		)
		self.group_root_parent = self.generator.bone_groups.ensure(
			name = "Root Control Parent"
			,layers = [IK_MAIN, IK_SECOND]
			,preset = 8
		)

	def prepare_bones(self):
		self.load_org_bones()

	def load_org_bones(self):
		# Load ORG bones into BoneInfo instances.
		self.org_chain = []

		for bn in self.bones.org.main:
			eb = self.get_bone(bn)
			eb.use_connect = False

			meta_org_name = eb.name.replace("ORG-", "")
			meta_org = self.generator.metarig.pose.bones.get(meta_org_name)
			# meta_org.name = meta_org.name.replace("-", self.generator.prefix_separator)

			org_bi = self.bone_infos.bone(bn, eb, self.obj, hide_select=self.mch_disable_select)

			# Rigify discards the bbone scale values from the metarig, but I'd like to keep them for easy visual scaling.
			org_bi._bbone_x = meta_org.bone.bbone_x
			org_bi._bbone_z = meta_org.bone.bbone_z

			org_bi.meta_bone = meta_org

			self.org_chain.append(org_bi)

	def generate_bones(self):
		pass

	def parent_bones(self):
		for bd in self.bone_infos.bones:
			if bd.name not in self.obj.data.bones:
				print(f"Warning: BoneInfo {bd.name} in riglet {self.base_bone} doesn't exist, edit data could not be written: ")
				continue
			edit_bone = self.get_bone(bd.name)

			bd.write_edit_data(self.obj, edit_bone)

	def create_real_bone_groups(self):
		bgs = self.generator.bone_groups
		# If the metarig has a group with the same name as what we're about to create, modify bone group's colors accordingly.
		for meta_bg in self.generator.metarig.pose.bone_groups:
			if meta_bg.name in bgs:
				bgs[meta_bg.name].normal = meta_bg.colors.normal[:]
				bgs[meta_bg.name].select = meta_bg.colors.select[:]
				bgs[meta_bg.name].active = meta_bg.colors.active[:]
	
		# Create bone groups on the metarig
		self.generator.bone_groups.make_real(self.generator.metarig)

		# Check for Unified Selected/Active color settings
		if self.generator.metarig.data.rigify_colors_lock:
			for bg in bgs.values():
				bg.select = self.generator.metarig.data.rigify_selection_colors.select[:]
				bg.active = self.generator.metarig.data.rigify_selection_colors.active[:]
		
		self.generator.bone_groups.make_real(self.obj)

	def configure_bones(self):
		self.create_real_bone_groups()

		for bd in self.bone_infos.bones:
			pose_bone = None
			try:
				pose_bone = self.get_bone(bd.name)
			except:
				print(f"WARNING: BoneInfo wasn't created for some reason: {bd.name}")
				continue
			# Apply scaling
			if not bd.use_custom_shape_bone_size:
				bd.custom_shape_scale *= self.scale * bd.bbone_width * 10
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

	def configure_display(self):
		# Armature display settings
		self.obj.display_type = 'SOLID'
		self.obj.data.display_type = 'BBONE'

	def finalize(self):
		self.set_layers(self.obj.data, [0, 16, 1, 17])

		if self.generator_params.cloudrig_create_root:
			# Set root bone layers
			root_bone = self.get_bone("root")
			self.set_layers(root_bone.bone, [0, 1, 16, 17])

		# # Nuke Rigify's generated root bone shape so it cannot be applied.
		# root_shape = bpy.data.objects.get("WGT-"+self.obj.name+"_root")
		# if root_shape:
		# 	bpy.data.objects.remove(root_shape)

		# For some god-forsaken reason, this is the earliest point when we can set bbone_x and bbone_z.
		for b in self.obj.data.bones:
			bi = self.bone_infos.find(b.name)
			if not bi:
				# print("How come there's no BoneInfo for {b.name}?")	# TODO?
				continue
			b.bbone_x = bi._bbone_x
			b.bbone_z = bi._bbone_z

		self.organize_widgets()
		self.configure_display()

	##############################
	# Parameters

	@classmethod
	def add_parameters(cls, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		pass

	@classmethod
	def parameters_ui(cls, layout, params):
		""" Create the ui for the rig parameters.
		"""
		ui_label_with_linebreak(layout, cls.description, bpy.context)

		# We can return a dictionary of key:UILayout elements, in case we want to affect the UI layout of inherited rig elements.
		return {}

def ui_label_with_linebreak(layout, text, context):
	words = text.split(" ")
	word_index = 0

	lines = [""]
	line_index = 0

	cur_line_length = 0
	max_line_length = context.area.width/6	# Try to determine maximum allowed characters in this line, based on pixel width of the area. Not a great solution, but a start.

	while word_index < len(words):
		word = words[word_index]

		if cur_line_length + len(word)+1 < max_line_length:
			word_index += 1
			cur_line_length += len(word)+1
			lines[line_index] += word + " "
		else:
			cur_line_length = 0
			line_index += 1
			lines.append("")
	
	for line in lines:
		layout.label(text=line)