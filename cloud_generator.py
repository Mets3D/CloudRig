import bpy, os
from mathutils import Matrix
from bpy.props import BoolProperty, StringProperty, EnumProperty, PointerProperty, BoolVectorProperty
from rigify.generate import *
from .definitions.bone_group import BoneGroupContainer
from .rigs import cloud_utils

separators = [
	(".", ".", "."),
	("-", "-", "-"),
	("_", "_", "_"),
]

class CloudRigProperties(bpy.types.PropertyGroup):
	options: BoolProperty(
		name		 = "CloudRig Settings"
		,description = "Show CloudRig Settings"
		,default	 = False
	)
	create_root: BoolProperty(
		name		 = "Create Root"
		,description = "Create the root control"
		,default	 = True
	)
	double_root: BoolProperty(
		name		 = "Double Root"
		,description = "Create two root controls"
		,default	 = False
	)
	custom_script: StringProperty(
		name		 = "Custom Script"
		,description = "Execute a python script after the rig is generated"
	)
	mechanism_movable: BoolProperty(
		name		 = "Movable Helpers"
		,description = "Whether helper bones can be moved or not"
		,default	 = True
	)
	mechanism_selectable: BoolProperty(
		name		 = "Selectable Helpers"
		,description = "Whether helper bones can be selected or not"
		,default	 = True
	)
	properties_bone: BoolProperty(
		name		 = "Properties Bone"
		,description = "Specify a bone to store Properties on. This bone doesn't have to exist in the metarig"
		,default	 = True
	)

	prefix_separator: EnumProperty(
		name		 = "Prefix Separator"
		,description = "Character that separates prefixes in the bone names"
		,items 		 = separators
		,default	 = "-"
	)
	suffix_separator: EnumProperty(
		name		 = "Suffix Separator"
		,description = "Character that separates suffixes in the bone names"
		,items 		 = separators
		,default	 = "."
	)

	override_options: BoolProperty(
		name = "Override Bone Layers"
		,description = "Instead of allowing rig elements to assign deform/mechanism/org bone layers individually, set it from the generator instead."
		,default=False
	)

	root_bone_group: StringProperty(
		name="Root"
		,description="Bone Group to assign the root bone to"
		,default="Root"
	)
	root_layers: BoolVectorProperty(
		size = 32, 
		subtype = 'LAYER', 
		description = "Layers to assign the root bone to",
		default = [l==0 for l in range(32)]
	)

	root_parent_group: StringProperty(
		name="Root Parent"
		,description="Bone Group to assign the second root bone to"
		,default="Root Parent"
	)
	root_parent_layers: BoolVectorProperty(
		size = 32, 
		subtype = 'LAYER', 
		description = "Layers to assign the the second root bone to",
		default = [l==0 for l in range(32)]
	)

	override_def_layers: BoolProperty(
		name		="Deform"
		,description="Instead of allowing rig elements to assign deform layers individually, set it from the generator instead"
		,default	=True
	)
	def_layers: BoolVectorProperty(
		size = 32, 
		subtype = 'LAYER', 
		description = "Select what layers this set of bones should be assigned to",
		default = [l==29 for l in range(32)]
	)

	override_mch_layers: BoolProperty(
		name		="Mechanism"
		,description="Instead of allowing rig elements to assign mechanism layers individually, set it from the generator instead"
		,default	=True
	)
	mch_layers: BoolVectorProperty(
		size = 32, 
		subtype = 'LAYER', 
		description = "Select what layers this set of bones should be assigned to",
		default = [l==30 for l in range(32)]
	)

	override_org_layers: BoolProperty(
		name		="Original"
		,description="Instead of allowing rig elements to assign original bones' layers individually, set it from the generator instead"
		,default	=True
	)
	org_layers: BoolVectorProperty(
		size = 32, 
		subtype = 'LAYER', 
		description = "Select what layers this set of bones should be assigned to",
		default = [l==31 for l in range(32)]
	)

class CloudGenerator(Generator):
	def __init__(self, context, metarig):
		super().__init__(context, metarig)
		self.params = metarig.data	# Generator parameters are stored in rig data.

		# Initialize BoneGroupContainer.
		self.bone_groups = BoneGroupContainer()

		# Root bone groups
		self.root_group = self.bone_groups.ensure(
			name = self.params.cloudrig_parameters.root_bone_group,
			preset = 2
		)
		if self.params.cloudrig_parameters.double_root:
			self.root_parent_group = self.bone_groups.ensure(
				name = self.params.cloudrig_parameters.root_parent_group,
				preset = 8
			)

		self.prefix_separator = self.params.cloudrig_parameters.prefix_separator
		self.suffix_separator = self.params.cloudrig_parameters.suffix_separator
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
		# obj.data.pose_position = 'POSE'

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

	def ensure_widget_collection(self):
		wgt_collection = None
		coll_name = "widgets_" + self.obj.name.replace("RIG-", "").lower()

		# Try finding a "Widgets" collection next to the metarig.
		for c in self.metarig.users_collection:
			wgt_collection = c.children.get(coll_name)
			if wgt_collection: break

		if not wgt_collection:
			# Try finding a "Widgets" collection next to the generated rig.
			for c in self.obj.users_collection:
				wgt_collection = c.children.get(coll_name)
				if wgt_collection: break

		if not wgt_collection:
			# Create a Widgets collection within the master collection.
			wgt_collection = bpy.data.collections.new(coll_name)
			bpy.context.scene.collection.children.link(wgt_collection)
		
		wgt_collection.hide_viewport=True
		wgt_collection.hide_render=True
		return wgt_collection

	def load_widget(self, name):
		""" Load custom shapes by appending them from a blend file, unless they already exist in this file. """
		
		# If it's already loaded, return it.
		wgt_name = "WGT-"+name
		wgt_ob = bpy.data.objects.get(wgt_name)
		
		exists = wgt_ob is not None

		if exists and not self.params.rigify_force_widget_update:
			return wgt_ob

		# If it exists, and we want to update it, rename it while we append the new one...
		if wgt_ob:
			wgt_ob.name = wgt_ob.name + "_temp"
			wgt_ob.data.name = wgt_ob.data.name + "_temp"

		# Loading bone shape object from file
		filename = "Widgets.blend"
		filedir = os.path.dirname(os.path.realpath(__file__))
		blend_path = os.path.join(filedir, filename)

		with bpy.data.libraries.load(blend_path) as (data_from, data_to):
			for o in data_from.objects:
				if o == wgt_name:
					data_to.objects.append(o)
		
		new_wgt_ob = bpy.data.objects.get(wgt_name)
		if not new_wgt_ob:
			print("WARNING: Failed to load bone shape: " + wgt_name)
			return
		elif wgt_ob:
			# Update original object with new one's data, then delete new object.
			old_data_name = wgt_ob.data.name
			wgt_ob.data = new_wgt_ob.data
			wgt_ob.name = wgt_name
			bpy.data.meshes.remove(bpy.data.meshes.get(old_data_name))
			bpy.data.objects.remove(new_wgt_ob)
		else:
			wgt_ob = new_wgt_ob

		if wgt_ob.name not in self.wgt_collection.objects:
			self.wgt_collection.objects.link(wgt_ob)
		
		return wgt_ob

	def generate(self):
		# NOTE: It should be possible to configure the generator options such that this function does nothing beside calling the generation stages of the rig elements.
		# That is to say, everything in here should be behind an if(generator_parameter) statement.
		print("CloudRig Generation begin")

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

		# Keep track of created widgets, so we can add them to Rigify-created Widgets collection at the end.
		self.wgt_collection = self.ensure_widget_collection()
		
		# Wipe any existing bone groups from the target rig. (TODO: parameter??)
		if obj.pose:
			for bone_group in obj.pose.bone_groups:
				obj.pose.bone_groups.remove(bone_group)
		
		# Rename metarig data (TODO: parameter)
		self.metarig.data.name = "Data_" + self.metarig.name

		# Enable all armature layers during generation. This is to make sure if you try to set a bone as active, it won't fail silently.
		obj.data.layers = [True]*32

		# Make sure X-Mirror editing is disabled, always!!
		obj.data.use_mirror_x = False

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

		# Copy Rigify Layers from metarig to target rig
		for i in range(len(obj.data.rigify_layers), len(self.metarig.data.rigify_layers)):
			obj.data.rigify_layers.add()
		for i, rig_layer in enumerate(self.metarig.data.rigify_layers):
			target = obj.data.rigify_layers[i]
			source = self.metarig.data.rigify_layers[i]
			target.name = source.name
			target.row = source.row
			target.selset = source.selset
			target.group = source.group

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

		# self.invoke_generate_widgets()

		# t.tick("Generate widgets: ")

		#------------------------------------------
		bpy.ops.object.mode_set(mode='OBJECT')

		obj.data.layers = self.metarig.data.layers[:]
		obj.data.layers_protected = self.metarig.data.layers_protected[:]
		self._Generator__restore_driver_vars()

		t.tick("Assign layers: ")

		#------------------------------------------
		bpy.ops.object.mode_set(mode='OBJECT')
		
		# Execute custom script
		script = cloud_utils.datablock_from_str(bpy.data.texts, self.params.cloudrig_parameters.custom_script)
		if script:
			exec(script.as_string(), {})

		# Load and execute cloudrig.py rig UI script
		obj.data['script'] = self.load_ui_script()

		# Armature display settings
		obj.display_type = self.metarig.display_type
		obj.data.display_type = self.metarig.data.display_type

		self.invoke_finalize()

		#TODO: For some reason when cloud_bone adds constraints to a bone, sometimes those constraints can be invalid even though they aren't actually.
		for pb in obj.pose.bones:
			for c in pb.constraints:
				if hasattr(c, 'subtarget'):
					c.subtarget = c.subtarget

		t.tick("Finalize: ")

		#------------------------------------------
		bpy.ops.object.mode_set(mode='OBJECT')

		self._Generator__assign_widgets()

		# Create Selection Sets
		create_selection_sets(obj, metarig)

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
	from bpy.utils import register_class
	register_class(CloudRigProperties)
	bpy.types.Armature.cloudrig_parameters = PointerProperty(type=CloudRigProperties)

def unregister():
	from bpy.utils import unregister_class
	unregister_class(CloudRigProperties)
	del bpy.types.Armature.cloudrig_parameters