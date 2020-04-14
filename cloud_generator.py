from rigify import generate as rigify_generate
from .definitions.bone_group import BoneGroupContainer
from bpy.props import BoolProperty, StringProperty, EnumProperty
import bpy

class CloudGenerator(rigify_generate.Generator):
	def generate(self):
		print("CloudRig Generation begin")
		super().generate()

def generate_rig(context, metarig):
	""" Generates a rig from a metarig.

	"""
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

def initialize_generation(riglet):
	""" All the CloudRig code that only needs to run once per rig generation is called from here."""
	# TODO: This stuff could literally be in CloudGenerator.__init__().
	rig_obj = riglet.obj
	generator = riglet.generator
	metarig = generator.metarig
	gen_params = metarig.data
	
	# Wipe any existing bone groups from the generated rig.
	for bone_group in rig_obj.pose.bone_groups:
		rig_obj.pose.bone_groups.remove(bone_group)
	
	# Initialize BoneGroupContainer on the generator.
	generator.bone_groups = BoneGroupContainer()

	# Initialize generator parameters (These are registered in cloudrig/__init__.py)
	generator.prefix_separator = gen_params.cloudrig_prefix_separator
	generator.suffix_separator = gen_params.cloudrig_suffix_separator
	assert generator.prefix_separator != generator.suffix_separator, "Error: Prefix and Suffix separators cannot be the same."

	# Replace generator functions - https://stackoverflow.com/questions/1301346/what-is-the-meaning-of-a-single-and-a-double-underscore-before-an-object-name
	# I am a determined soul.

	# There exists a cleaner solution than this. Right now we are hijacking the generator class's functions. 
	# Instead it would be a lot cleaner if we could extend rigify's generator class,
	# and hijack the generator operator, so that if it's a cloudrig, then use a cloudrig_generator.
	# Alternatively we could hijack the button so if it's a cloudrig, use a cloudrig_generate() operator.

	# Generator = rigify_generate.Generator
	# Generator.rigify_create_root_bone = Generator._Generator__create_root_bone
	# Generator._Generator__create_root_bone = __cloud_create_root_bone

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