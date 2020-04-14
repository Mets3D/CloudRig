from rigify.generate import *
from .definitions.bone_group import BoneGroupContainer
from bpy.props import BoolProperty, StringProperty, EnumProperty
import bpy

class CloudGenerator(Generator):
	def __init__(self, context, metarig):
		super().__init__(context, metarig)
		params = metarig.data	# Generator parameters are stored in rig data.
		
		# Initialize BoneGroupContainer.
		self.bone_groups = BoneGroupContainer()

		# Initialize generator parameters (These are registered in cloudrig/__init__.py)
		self.prefix_separator = params.cloudrig_prefix_separator
		self.suffix_separator = params.cloudrig_suffix_separator
		assert self.prefix_separator != self.suffix_separator, "CloudGenerator Error: Prefix and Suffix separators cannot be the same."

	
	def generate(self):
		# NOTE: It should be possible to configure the generator options such that this function does nothing beside calling the generation stages of the rig elements.
		# That is to say, everything in here should be behind an if(generator_parameter) statement.
		print("CloudRig Generation begin")
		
		# # Wipe any existing bone groups from the generated rig.
		# for bone_group in rig_obj.pose.bone_groups:
		# 	rig_obj.pose.bone_groups.remove(bone_group)

		# For now we just copy-pasted Rigify's generate(). A lot of this will be modifier later though.
		# Unfortunately for some reason the Generator class has a lot of name-mangled functions, which makes it unneccessailry ugly to modify... Not sure why that choice was made.
		
		context = self.context
		metarig = self.metarig
		scene = self.scene
		id_store = self.id_store
		view_layer = self.view_layer
		t = Timer()

		self.usable_collections = list_layer_collections(view_layer.layer_collection, selectable=True)

		if self.layer_collection not in self.usable_collections:
			metarig_collections = filter_layer_collections_by_object(self.usable_collections, self.metarig)
			self.layer_collection = (metarig_collections + [view_layer.layer_collection])[0]
			self.collection = self.layer_collection.collection

		bpy.ops.object.mode_set(mode='OBJECT')

		#------------------------------------------
		# Create/find the rig object and set it up
		obj = self._Generator__create_rig_object()

		# Get rid of anim data in case the rig already existed
		print("Clear rig animation data.")

		obj.animation_data_clear()
		obj.data.animation_data_clear()

		select_object(context, obj, deselect_all=True)

		#------------------------------------------
		# Create Group widget
		self._Generator__create_widget_group("WGTS_" + obj.name)

		t.tick("Create main WGTS: ")

		#------------------------------------------
		# Get parented objects to restore later
		childs = {}  # {object: bone}
		for child in obj.children:
			childs[child] = child.parent_bone

		#------------------------------------------
		# Copy bones from metarig to obj
		self._Generator__duplicate_rig()

		t.tick("Duplicate rig: ")

		#------------------------------------------
		# Add the ORG_PREFIX to the original bones.
		bpy.ops.object.mode_set(mode='OBJECT')

		# self._Generator__rename_org_bones()

		t.tick("Make list of org bones: ")

		#------------------------------------------
		# Put the rig_name in the armature custom properties
		rna_idprop_ui_prop_get(obj.data, "rig_id", create=True)
		obj.data["rig_id"] = self.rig_id

		self.script = rig_ui_template.ScriptGenerator(self)

		#------------------------------------------
		bpy.ops.object.mode_set(mode='OBJECT')

		self.instantiate_rig_tree()

		t.tick("Instantiate rigs: ")

		#------------------------------------------
		bpy.ops.object.mode_set(mode='OBJECT')

		self.invoke_initialize()

		t.tick("Initialize rigs: ")

		#------------------------------------------
		bpy.ops.object.mode_set(mode='EDIT')

		self.invoke_prepare_bones()

		t.tick("Prepare bones: ")

		#------------------------------------------
		bpy.ops.object.mode_set(mode='OBJECT')
		bpy.ops.object.mode_set(mode='EDIT')

		self._Generator__create_root_bone()

		self.invoke_generate_bones()

		t.tick("Generate bones: ")

		#------------------------------------------
		bpy.ops.object.mode_set(mode='OBJECT')
		bpy.ops.object.mode_set(mode='EDIT')

		self.invoke_parent_bones()

		self._Generator__parent_bones_to_root()

		t.tick("Parent bones: ")

		#------------------------------------------
		bpy.ops.object.mode_set(mode='OBJECT')

		self.invoke_configure_bones()

		t.tick("Configure bones: ")

		#------------------------------------------
		bpy.ops.object.mode_set(mode='EDIT')

		self.invoke_apply_bones()

		t.tick("Apply bones: ")

		#------------------------------------------
		bpy.ops.object.mode_set(mode='OBJECT')

		self.invoke_rig_bones()

		t.tick("Rig bones: ")

		#------------------------------------------
		bpy.ops.object.mode_set(mode='OBJECT')

		create_root_widget(obj, "root")

		self.invoke_generate_widgets()

		t.tick("Generate widgets: ")

		#------------------------------------------
		bpy.ops.object.mode_set(mode='OBJECT')

		self._Generator__lock_transforms()
		self._Generator__assign_layers()
		self._Generator__compute_visible_layers()
		self._Generator__restore_driver_vars()

		t.tick("Assign layers: ")

		#------------------------------------------
		bpy.ops.object.mode_set(mode='OBJECT')

		self.invoke_finalize()

		t.tick("Finalize: ")

		#------------------------------------------
		bpy.ops.object.mode_set(mode='OBJECT')

		self._Generator__assign_widgets()

		# Create Selection Sets
		create_selection_sets(obj, metarig)

		# Create Bone Groups
		create_bone_groups(obj, metarig, self.layer_group_priorities)

		t.tick("The rest: ")

		#----------------------------------
		# Deconfigure
		bpy.ops.object.mode_set(mode='OBJECT')
		obj.data.pose_position = 'POSE'

		# Restore parent to bones
		for child, sub_parent in childs.items():
			if sub_parent in obj.pose.bones:
				mat = child.matrix_world.copy()
				child.parent_bone = sub_parent
				child.matrix_world = mat

		#----------------------------------
		# Restore active collection
		view_layer.active_layer_collection = self.layer_collection


def generate_rig(context, metarig):
	""" Generates a rig from a metarig.	"""
	# Initial configuration
	rest_backup = metarig.data.pose_position
	metarig.data.pose_position = 'REST'

	try:
		CloudGenerator(context, metarig).generate()

		metarig.data.pose_position = rest_backup

	except Exception as e:
		# Cleanup if something goes wrong
		print("Rigify: failed to generate rig.")

		bpy.ops.object.mode_set(mode='OBJECT')
		metarig.data.pose_position = rest_backup

		# Continue the exception
		raise e

def register():
	bpy.types.Armature.cloudrig_options = BoolProperty(
		name		 = "CloudRig Settings"
		,description = "Show CloudRig Settings"
		,default	 = False
	)
	bpy.types.Armature.cloudrig_create_root = BoolProperty(
		name		 = "Create Root"
		,description = "Create the root control"
		,default	 = True
	)
	bpy.types.Armature.cloudrig_double_root = BoolProperty(
		name		 = "Double Root"
		,description = "Create two root controls"
		,default	 = False
	)
	bpy.types.Armature.cloudrig_custom_script = StringProperty(
		name		 = "Custom Script"
		,description = "Execute a python script after the rig is generated"
	)
	bpy.types.Armature.cloudrig_mechanism_movable = BoolProperty(
		name		 = "Movable Helpers"
		,description = "Whether helper bones can be moved or not"
		,default	 = True
	)
	bpy.types.Armature.cloudrig_mechanism_selectable = BoolProperty(
		name		 = "Selectable Helpers"
		,description = "Whether helper bones can be selected or not"
		,default	 = True
	)
	bpy.types.Armature.cloudrig_properties_bone = BoolProperty(
		name		 = "Properties Bone"
		,description = "Specify a bone to store Properties on. This bone doesn't have to exist in the metarig"
		,default	 = True
	)

	separators = [
		(".", ".", "."),
		("-", "-", "-"),
		("_", "_", "_"),
	]
	bpy.types.Armature.cloudrig_prefix_separator = EnumProperty(
		name		 = "Prefix Separator"
		,description = "Character that separates prefixes in the bone names"
		,items 		 = separators
		,default	 = "-"
	)
	bpy.types.Armature.cloudrig_suffix_separator = EnumProperty(
		name		 = "Suffix Separator"
		,description = "Character that separates suffixes in the bone names"
		,items 		 = separators
		,default	 = "."
	)

def unregister():
	ArmStore = bpy.types.Armature
	del ArmStore.cloudrig_options
	del ArmStore.cloudrig_create_root
	del ArmStore.cloudrig_double_root
	del ArmStore.cloudrig_custom_script
	del ArmStore.cloudrig_mechanism_movable
	del ArmStore.cloudrig_mechanism_selectable
	del ArmStore.cloudrig_properties_bone
	del ArmStore.cloudrig_prefix_separator
	del ArmStore.cloudrig_suffix_separator