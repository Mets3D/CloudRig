import bpy, os
from bpy.props import BoolProperty, FloatProperty, StringProperty, BoolVectorProperty
from mathutils import Vector
from collections import OrderedDict

from rigify.base_rig import BaseRig, stage

from ..definitions.driver import Driver
from ..definitions.bone import BoneInfoContainer
from .cloud_utils import CloudUtilities
from .. import cloud_generator
from enum import Enum

class DefaultLayers(Enum):
	IK_MAIN = 0
	IK_SECOND = 16
	FK_MAIN = 1
	STRETCH = 2

	DEF = 29
	MCH = 30
	ORG = 31

class CloudBaseRig(BaseRig, CloudUtilities):
	"""Base for all CloudRig rigs."""

	description = "CloudRig Element (no description)"

	bone_sets = OrderedDict()

	default_layers = lambda name: DefaultLayers[name].value

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
		# TODO: move to generator?
		self.widgets = []

		parent = self.get_bone(self.base_bone).parent
		self.bones.parent = parent.name if parent else ""

		# Root bone
		self.root_bone = self.bone_infos.bone(
			name				= "root"
			,bone_group			= self.bone_groups['Root Control']
			,layers				= self.bone_layers['Root Control']
			,head				= Vector((0, 0, 0))
			,tail				= Vector((0, self.scale*5, 0))
			,bbone_width		= 1/3
			,custom_shape		= self.load_widget("Root")
			,custom_shape_scale = 1.5
		)
		self.register_parent(self.root_bone, "Root")
		if self.generator_params.cloudrig_double_root:
			self.root_parent = self.create_parent_bone(self.root_bone)
			self.root_parent.bone_group = self.bone_groups['Root Control Parent']
			self.root_parent.layers = self.bone_layers['Root Control Parent']

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
			overwrite = False,
			bone_group = self.bone_groups['Root Control'],
			layers = self.bone_layers['Root Control'],
			custom_shape = self.load_widget("Cogwheel"),
			head = Vector((0, self.scale*2, 0)),
			tail = Vector((0, self.scale*4, 0)),
			bbone_width = 1/8
		)
		return prop_bone

	def ensure_bone_groups(self):
		""" Ensure bone groups that this rig needs. """
		# Now my only concern is, where do we get the preset from? It could be stored in cls.bone_groups...
		
		self.bone_groups = {}
		self.bone_layers = {}

		class_sets = type(self).bone_sets
		for ui_name in class_sets.keys():
			set_info = class_sets[ui_name]

			group_name = getattr(self.params, set_info['param'])
			group_layers = getattr(self.params, set_info['layer_param'])
			self.bone_groups[ui_name] = self.generator.bone_groups.ensure(
				name = group_name,
				preset = set_info['preset']
			)
			self.bone_layers[ui_name] = group_layers[:]

	def prepare_bones(self):
		self.load_org_bones()

	def load_org_bones(self):
		# Load ORG bones into BoneInfo instances.
		self.org_chain = []

		for bn in self.bones.org.main:
			eb = self.get_bone(bn)
			eb.use_connect = False

			meta_org_name = eb.name[4:]
			meta_org = self.generator.metarig.pose.bones.get(meta_org_name)
			# meta_org.name = meta_org.name.replace("-", self.generator.prefix_separator)

			org_bi = self.bone_infos.bone(
				name		 = bn
				,source		 = eb
				,hide_select = self.mch_disable_select
				,bone_group	 = self.bone_groups["Original Bones"]
				,layers		 = self.bone_layers["Original Bones"]
			)

			# Rigify discards the bbone scale values from the metarig, but I'd like to keep them for easy visual scaling.
			org_bi._bbone_x = meta_org.bone.bbone_x
			org_bi._bbone_z = meta_org.bone.bbone_z

			org_bi.meta_bone = meta_org

			self.org_chain.append(org_bi)

	def generate_bones(self):
		for bd in self.bone_infos.bones:
			if (
				bd.name not in self.obj.data.edit_bones and
				bd.name not in self.bones.flatten() and
				bd.name != 'root'
			):
				self.copy_bone("root", bd.name)
				# self.new_bone(bd.name) # new_bone() is currently bugged and doesn't register the new bone, so we use copy_bone instead.

	def parent_bones(self):
		for bd in self.bone_infos.bones:
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

		# Set root bone layers
		# root_bone = self.get_bone("root")
		# self.set_layers(root_bone.bone, [0, 1, 16, 17])

		# Nuke Rigify's generated root bone shape so it cannot be applied.
		root_shape = bpy.data.objects.get("WGT-"+self.obj.name+"_root")
		if root_shape:
			bpy.data.objects.remove(root_shape)

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
	def add_bone_set(cls, params, ui_name, default_group="", default_layers=[0], preset=-1):
		""" 
		A bone set is just a set of rig parameters for choosing a bone group and list of bone layers.
		This function is responsible for creating those rig parameters, as well as storing them, 
		so they can be referenced easily when implementing the creation of a new bone 
		and assigning its bone group and layers. 

		For example, all FK chain bones of the FK chain rig are hard-coded to be part of the "FK Main" bone set.
		Then the "FK Main" bone set's bone group and bone layer can be customized via the parameters.
		"""

		group_name = ui_name.replace(" ", "_").lower()
		if default_group=="":
			default_group = ui_name

		param_name = "CR_BG_" + group_name.replace(" ", "_")
		layer_param_name = "CR_BG_LAYERS_" + group_name.replace(" ", "_")

		setattr(
			params, 
			param_name,
			StringProperty(
				default = default_group,
				description = "Select what group this set of bones should be assigned to"
			)
		)
		
		default_layers_bools = [i in default_layers for i in range(32)]
		setattr(
			params, 
			layer_param_name, 
			BoolVectorProperty(
				size = 32, 
				subtype = 'LAYER', 
				description = "Select what layers this set of bones should be assigned to",
				default = default_layers_bools
			)
		)
		
		cls.bone_sets[ui_name] = {
			'name' : ui_name,
			'preset' : preset,					# Bone Group color preset to use in case the bone group doesn't already exist.
			'param' : param_name,				# Name of the bone group name parameter
			'layer_param' : layer_param_name	# Name of the bone layers parameter
		}
		return ui_name

	@classmethod
	def add_bone_sets(cls, params):
		""" Create parameters for this rig's bone sets. """
		cls.bone_sets = OrderedDict()
		params.CR_show_bone_sets = BoolProperty(name="Bone Sets")

		cls.add_bone_set(params, "Root Control", preset=2)
		cls.add_bone_set(params, "Root Control Parent", preset=8)
		cls.add_bone_set(params, "Original Bones", default_layers=[cls.default_layers('ORG')])
		cls.add_bone_set(params, "Display Transform Helpers", default_layers=[cls.default_layers('MCH')])
		cls.add_bone_set(params, "Parent Switch Helpers", default_layers=[cls.default_layers('MCH')])

	@classmethod
	def add_parameters(cls, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		cls.add_bone_sets(params)

	
	@classmethod
	def bone_set_ui(cls, params, layout, set_info, ui_rows):
		ui_rows[set_info['param']] = col = layout.column()
		col.prop_search(params, set_info['param'], bpy.context.object.pose, "bone_groups", text=set_info['name'])
		col.prop(params, set_info['layer_param'], text="")
		layout.separator()

	@classmethod
	def bone_sets_ui(cls, layout, params, ui_rows):
		icon = 'TRIA_DOWN' if params.CR_show_bone_sets else 'TRIA_RIGHT'
		layout.prop(params, "CR_show_bone_sets", toggle=True, icon=icon)
		if not params.CR_show_bone_sets: return

		# print(f"bone sets for {cls}")
		# import json
		# print(json.dumps(cls.bone_sets, indent=2))
		for ui_name in cls.bone_sets.keys():
			set_info = cls.bone_sets[ui_name]
			cls.bone_set_ui(params, layout, set_info, ui_rows)
		
		return ui_rows

	@classmethod
	def parameters_ui(cls, layout, params):
		""" Create the ui for the rig parameters.
		"""
		ui_rows = {}
		from ..ui import ui_label_with_linebreak
		ui_label_with_linebreak(layout, cls.description)
		cls.bone_sets_ui(layout, params, ui_rows)

		# We can return a dictionary of key:UILayout elements, in case we want to affect the UI layout of inherited rig elements.
		return ui_rows