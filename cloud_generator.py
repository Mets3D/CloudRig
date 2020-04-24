import bpy, os
from mathutils import Matrix
from bpy.props import BoolProperty, StringProperty, EnumProperty
from rigify.generate import *
from .definitions.bone_group import BoneGroupContainer
from .rigs import cloud_utils

class CloudGenerator(Generator):
	def __init__(self, context, metarig):
		super().__init__(context, metarig)
		self.params = metarig.data	# Generator parameters are stored in rig data.

		# Initialize BoneGroupContainer.
		self.bone_groups = BoneGroupContainer()

		# Initialize generator parameters (These are registered in cloudrig/__init__.py)
		self.prefix_separator = self.params.cloudrig_prefix_separator
		self.suffix_separator = self.params.cloudrig_suffix_separator
		assert self.prefix_separator != self.suffix_separator, "CloudGenerator Error: Prefix and Suffix separators cannot be the same."

	def create_rig_object(self):
		scene = self.scene

		# Check if the generated rig already exists, so we can
		# regenerate in the same object.  If not, create a new
		# object to generate the rig in.
		print("Find or create rig object.")

		metaname = self.metarig.name
		rig_name = "RIG" + self.prefix_separator + metaname
		if "META" in metaname:
			rig_name = metaname.replace("META", "RIG")

		# Try to find object from the generator parameter.
		obj = self.params.rigify_target_rig
		if not obj:
			# Try to find object in scene.
			obj = scene.objects.get(rig_name)
		if not obj:
			# Try to find object in file.
			obj = bpy.data.objects.get(rig_name)
		if not obj:
			# Object wasn't found anywhere, so create it.
			obj = bpy.data.objects.new(rig_name, bpy.data.armatures.new(rig_name))

		assert obj, "Error: Failed to find or create object!"
		obj.data.name = "Data_" + obj.name

		# Ensure rig is in the metarig's collection.
		if obj.name not in self.collection.objects:
			self.collection.objects.link(obj)

		self.params.rigify_target_rig = obj
		obj.data.pose_position = 'POSE'

		self.obj = obj
		return obj
	
	def load_ui_script(self):
		"""Load cloudrig.py (CloudRig UI script) into a text datablock, enable register checkbox and execute it."""
		
		# Check if it already exists
		script_name = "cloudrig.py"
		text = bpy.data.texts.get(script_name)
		# If not, create it.
		if not text:
			text = bpy.data.texts.new(name=script_name)
		
		text.clear()
		text.use_module = True

		filename = script_name
		filedir = os.path.dirname(os.path.realpath(__file__))
		# filedir = os.path.split(filedir)[0]

		readfile = open(os.path.join(filedir, filename), 'r')

		# The script should have a unique identifier that links it to the rigs that were generated in this file - The .blend filename should be sufficient.
		script_id = bpy.path.basename(bpy.data.filepath).split(".")[0]
		if script_id=="":
			# Default in case the file hasn't been saved yet. 
			# Falling back to this could result in an older version of the rig trying to use a newer version of the rig UI script or vice versa, so it should be avoided.
			script_id = "cloudrig"
		
		self.obj.data['cloudrig'] = script_id

		for line in readfile:
			if 'SCRIPT_ID' in line:
				line = line.replace("SCRIPT_ID", script_id)
			text.write(line)
		readfile.close()

		# Run UI script
		exec(text.as_string(), {})

		return text

	def generate(self):
		# NOTE: It should be possible to configure the generator options such that this function does nothing beside calling the generation stages of the rig elements.
		# That is to say, everything in here should be behind an if(generator_parameter) statement.
		print("CloudRig Generation begin")

		# For now we just copy-pasted Rigify's generate(). A lot of this will be modifier later though.
		# Unfortunately for some reason the Generator class has a lot of name-mangled functions, which makes it unneccessailry ugly to modify... Not sure why that choice was made.

		context = self.context
		metarig = self.metarig
		t = Timer()

		self.collection = context.scene.collection
		if len(self.metarig.users_collection) > 0:
			self.collection = self.metarig.users_collection[0]

		bpy.ops.object.mode_set(mode='OBJECT')

		#------------------------------------------
		# Create/find the rig object and set it up
		obj = self.create_rig_object()

		# Ensure it's transforms are cleared.
		backup_matrix = obj.matrix_world.copy()
		obj.matrix_world = Matrix()
		
		# Wipe any existing bone groups from the target rig. (TODO: parameter??)
		if obj.pose:
			for bone_group in obj.pose.bone_groups:
				obj.pose.bone_groups.remove(bone_group)
		
		# Rename metarig data (TODO: parameter)
		self.metarig.data.name = "Data_" + self.metarig.name

		# Get rid of anim data in case the rig already existed
		print("Clear rig animation data.")

		obj.animation_data_clear()
		obj.data.animation_data_clear()

		select_object(context, obj, deselect_all=True)

		#------------------------------------------
		# Create Group widget
		# self._Generator__create_widget_group("WGTS_" + obj.name)

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

		self._Generator__rename_org_bones()

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

		# Rigify automatically parents bones that have no parent to the root bone.
		# This is fine, but we want to undo this when the bone has an Armature constraint, since such bones should never have a parent.
		# NOTE: This could be done via self.generator.disable_auto_parent(bone_name), but I prefer doing it this way.
		for eb in obj.data.edit_bones:
			pb = obj.pose.bones.get(eb.name)
			for c in pb.constraints:
				if c.type=='ARMATURE':
					eb.parent = None
					break

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

		self._Generator__assign_layers()
		self._Generator__compute_visible_layers()
		self._Generator__restore_driver_vars()

		t.tick("Assign layers: ")

		#------------------------------------------
		bpy.ops.object.mode_set(mode='OBJECT')
		
		# Execute custom script
		script = cloud_utils.datablock_from_str(bpy.data.texts, self.params.cloudrig_custom_script)
		if script:
			exec(script.as_string(), {})

		# Load and execute cloudrig.py rig UI script
		obj.data['script'] = self.load_ui_script()

		self.invoke_finalize()

		t.tick("Finalize: ")

		#------------------------------------------
		bpy.ops.object.mode_set(mode='OBJECT')

		self._Generator__assign_widgets()

		# Create Selection Sets
		create_selection_sets(obj, metarig)

		# Create Bone Groups
		# create_bone_groups(obj, metarig, self.layer_group_priorities)

		t.tick("The rest: ")

		#----------------------------------
		# Deconfigure
		bpy.ops.object.mode_set(mode='OBJECT')
		obj.data.pose_position = 'POSE'
		# Restore rig object matrix to what it was before generation.
		obj.matrix_world = backup_matrix

		# Restore parent to bones
		for child, sub_parent in childs.items():
			if sub_parent in obj.pose.bones:
				mat = child.matrix_world.copy()
				child.parent_bone = sub_parent
				child.matrix_world = mat

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