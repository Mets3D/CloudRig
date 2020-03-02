from bpy.props import *
from mathutils import *
from math import pi

from rigify.base_rig import stage
from rigify.utils.bones import BoneDict
from rigify.utils.rig import connected_children_names

from ..definitions.driver import *
from ..definitions.custom_props import CustomProp
from .cloud_utils import make_name, slice_name
from .cloud_fk_chain import CloudFKChainRig

class Rig(CloudFKChainRig):
	"""CloudRig arms and legs."""

	def find_org_bones(self, bone):
		"""Populate self.bones.org."""
		# For limbs, we only care about the first three bones in the chain.
		return BoneDict(
			main=[bone.name] + connected_children_names(self.obj, bone.name),
		)
	
	def initialize(self):
		super().initialize()
		"""Gather and validate data about the rig."""
		if self.params.type=='ARM':
			assert len(self.bones.org.main) == 3, "Arm chain must be exactly 3 connected bones."
		if self.params.type=='LEG':
			assert len(self.bones.org.main) == 4, "Leg chain must be exactly 4 connected bones."

		# Properties bone and Custom Properties
		side = self.side_prefix.lower()
		limb = self.params.type.lower()

		self.category = "arms" if self.params.type == 'ARM' else "legs"
		if self.params.use_category_name:
			self.category = self.params.category_name
		self.limb_name = self.side_prefix + " " + limb.capitalize()
		if self.params.use_limb_name:
			self.limb_name = self.params.limb_name

		self.limb_name_props = self.limb_name.replace(" ", "_").lower()
		self.ikfk_name = "ik_" + self.limb_name_props
		self.ik_stretch_name = "ik_stretch_" + self.limb_name_props
		self.fk_hinge_name = "fk_hinge_" + self.limb_name_props
		self.ik_pole_follow_name = "ik_pole_follow_" + self.limb_name_props

	def get_segments(self, org_i, chain):
		segments = self.params.deform_segments
		bbone_segments = self.params.bbone_segments
		
		if self.params.type=='LEG' and org_i > len(chain)-3:
			# Force strictly 1 segment on the foot and the toe.
			return (1, self.params.bbone_segments)
		elif self.params.type=='ARM' and org_i == len(chain)-1:
			# Force strictly 1 segment and no BBone on the wrist.
			return (1, 1)
		
		return(segments, bbone_segments)

	@stage.prepare_bones
	def prepare_root_bone(self):
		# Socket/Root bone to parent IK and FK to.
		root_name = self.base_bone.replace("ORG", "ROOT")
		base_bone = self.get_bone(self.base_bone)
		self.limb_root_bone = self.bone_infos.bone(
			name 				= root_name, 
			source 				= base_bone, 
			parent 				= self.bones.parent,
			custom_shape 		= self.load_widget("Cube"),
			custom_shape_scale 	= 0.5,
			bone_group			= 'Body: IK-MCH - IK Mechanism Bones'
		)
		self.register_parent(self.limb_root_bone, self.side_suffix + " " + self.params.type.capitalize())

	@stage.prepare_bones
	def prepare_fk_limb(self):
		# Note: This runs after super().prepare_fk_chain().

		# TODO: Need bones to drive shape keys, such as HLP-Wrist2.L, HLP-Elbow2.L. (We cannot rely on ORG bone local rotations if we expect the shape keys to still behave when the STR bones are posed extremely)
		# TODO: Drivers for rotation order?

		hng_child = self.fk_chain[0]
		for i, fk_bone in enumerate(self.fk_chain):
			if i == 0 and self.params.double_first_control:
				# Make a parent for the first control.
				fk_parent_bone = self.create_parent_bone(fk_bone)
				fk_parent_bone.custom_shape = self.load_widget("FK_Limb")
				self.create_dsp_bone(fk_parent_bone, center=True)

				# Store in the beginning of the FK list, since it's the new root of the FK chain.
				#self.fk_chain.insert(0, fk_parent_bone)
				hng_child = fk_parent_bone

			if i == 1:
				fk_bone.lock_rotation[1] = self.params.lock_yz
				fk_bone.lock_rotation[2] = self.params.lock_yz

			if i < 2:
				# Setup DSP bone for all but last bone.
				self.create_dsp_bone(fk_bone, center=True)
				pass

			if i == 2:
				fk_bone.custom_shape_scale = 0.8
				if self.params.world_aligned:
					fk_name = fk_bone.name
					fk_bone.name = fk_bone.name.replace("FK-", "FK-W-")	# W for World?
					# Make child control for the world-aligned control, that will have the original transforms and name.
					# This is currently just the target of a Copy Transforms constraint on the ORG bone and therefore kindof redundant, because if we really wanted, we could use Armature constraints on those ORG bones instead of copy transforms. But then our outliner hierarchy is completely messed up ofc.
					fk_child_bone = self.bone_infos.bone(
						name = fk_name,
						source = fk_bone,
						parent = fk_bone,
						#custom_shape = self.load_widget("FK_Limb"),
						custom_shape_scale = 0.5,
						bone_group = 'Body: FK Helper Bones'
					)
					#self.fk_chain.append(fk_child_bone)
					
					fk_bone.flatten()
			
			if i == 3 and self.params.type=='LEG':
				self.fk_toe = fk_bone
		
		# Create Hinge helper
		self.hinge_setup(
			bone = hng_child, 
			category = self.category,
			parent_bone = self.limb_root_bone,
			hng_name = self.base_bone.replace("ORG", "FK-HNG"),
			prop_bone = self.prop_bone,
			prop_name = self.fk_hinge_name,
			limb_name = self.limb_name
		)

	@stage.prepare_bones
	def prepare_str_limb(self):
		# We want to make some changes to the STR chain to make it behave more limb-like.
		
		# Disable first Copy Rotation constraint on the upperarm
		for b in self.main_str_bones[0].sub_bones:
			str_h_bone = b.parent
			if len(str_h_bone.constraints) < 3:
				# print(str_h_bone.name)
				continue
			str_h_bone.constraints[2][1]['mute'] = True	# TODO IMPORTANT: We have no proper way to access already existing constraints (by name, or even type) which is pretty sad. Instead of storing constraints as a (type, attribs) tuple, just store them as a dict, and initialize them a 'name' and 'type' attrib in add_constraint(). Relying on names can be tricky though... Maybe the proper solution here is proper code splitting, so adding the constraints to the str_h_bone would be done in a rig_str_h_bone() function, which we override here in cloud_limbs.

	@stage.prepare_bones
	def prepare_ik_limb(self):
		limb_type = self.params.type
		chain = self.bones.org.main

		# Create IK Pole Control
		first_bn = chain[0]
		first_bone = self.get_bone(chain[0])
		elbow = copy.copy(first_bone.tail)
		direction = 1 if limb_type=='ARM' else -1					# Character is expected to face +Y direction.
		offset_scale = 3 if limb_type=='ARM' else 5					# Scalar on distance from the body.
		offset = Vector((0, direction*offset_scale*self.scale, 0)) * self.params.pole_offset
		limb_name = limb_type.capitalize()
		if self.params.use_limb_name:
			limb_name = self.params.limb_name
		pole_ctrl = self.pole_ctrl = self.bone_infos.bone(
			name = make_name(["IK", "POLE"], limb_name, [self.side_suffix]),
			bbone_width = 0.1,
			head = elbow + offset,
			tail = elbow + offset*1.1,
			roll = 0,
			custom_shape = self.load_widget('ArrowHead'),
			custom_shape_scale = 0.5,
			bone_group = 'Body: Main IK Controls',
		)
		pole_line = self.bone_infos.bone(
			name = make_name(["IK", "POLE", "LINE"], limb_name, [self.side_suffix]),
			source = pole_ctrl,
			tail = elbow,
			custom_shape = self.load_widget('Pole_Line'),
			use_custom_shape_bone_size = True,
			parent = pole_ctrl,
			bone_group = 'Body: Main IK Controls',
		)
		pole_line.add_constraint(self.obj, 'STRETCH_TO', 
			subtarget = first_bone.name, 
			head_tail = 1,
		)
		# Add a driver to the Line's hide property so it's hidden exactly when the pole target is hidden.
		drv = Driver()
		var = drv.make_var("var")
		var.type = 'SINGLE_PROP'
		var.targets[0].id_type = 'ARMATURE'
		var.targets[0].id = self.obj.data
		var.targets[0].data_path = 'bones["%s"].hide' %pole_ctrl.name

		pole_line.bone_drivers['hide'] = drv
		pole_line.hide_select=True
		
		pole_dsp = self.create_dsp_bone(pole_ctrl)

		def foot_dsp(bone):
			# Create foot DSP helpers
			if limb_type=='LEG':
				dsp_bone = self.create_dsp_bone(bone)
				direction = 1 if self.side_suffix=='L' else -1
				projected_head = Vector((bone.head[0], bone.head[1], 0))
				projected_tail = Vector((bone.tail[0], bone.tail[1], 0))
				projected_center = projected_head + (projected_tail-projected_head) / 2
				dsp_bone.head = projected_center
				dsp_bone.tail = projected_center + Vector((0, -self.scale/10, 0))
				dsp_bone.roll = pi/2 * direction

		# Create IK control(s) (Hand/Foot)
		bone_name = chain[2]
		org_bone = self.get_bone(bone_name)
		mstr_name = bone_name.replace("ORG", "IK-MSTR")
		wgt_name = 'Hand_IK' if limb_type=='ARM' else 'Foot_IK'
		self.ik_mstr = self.bone_infos.bone(
			name = mstr_name, 
			source = org_bone, 
			custom_shape = self.load_widget(wgt_name),
			custom_shape_scale = 0.8 if self.params.type=='ARM' else 2.8,
			parent = None,
			bone_group = 'Body: Main IK Controls'
		)
		foot_dsp(self.ik_mstr)
		# Parent control
		double_control = None
		if self.params.double_ik_control:
			double_control = self.create_parent_bone(self.ik_mstr)
			double_control.bone_group = 'Body: Main IK Controls Extra Parents'
			foot_dsp(double_control)
		
		if self.params.world_aligned:
			self.ik_mstr.flatten()
			double_control.flatten()
		
		# IK Chain
		ik_chain = []
		org_chain = []
		for i, bn in enumerate(chain):
			org_bone = self.get_bone(bn)
			org_chain.append(org_bone)
			ik_name = bn.replace("ORG", "IK")
			ik_bone = self.bone_infos.bone(ik_name, org_bone, 
				#ik_stretch = 0.1,
				bone_group = 'Body: IK-MCH - IK Mechanism Bones',
			)
			ik_chain.append(ik_bone)
			
			if i == 0:
				# Parent first bone to the limb root
				ik_bone.parent = self.limb_root_bone.name
				# Add aim constraint to pole display bone
				pole_dsp.add_constraint(self.obj, 'DAMPED_TRACK', subtarget=ik_bone.name, head_tail=1, track_axis='TRACK_NEGATIVE_Y')
			else:
				ik_bone.parent = ik_chain[-2]
			
			if i == 2:
				if self.params.type == 'LEG':
					# Create separate IK target bone, for keeping track of where IK should be before IK Roll is applied, whether IK Stretch is on or off.
					self.ik_tgt_bone = self.bone_infos.bone(
						name = bn.replace("ORG", "IK-TGT"),
						source = org_bone,
						bone_group = 'Body: IK-MCH - IK Mechanism Bones',
						parent = self.ik_mstr
					)
				else:
					self.ik_tgt_bone = ik_bone
					ik_bone.parent = self.ik_mstr
				# Add the IK constraint to the previous bone, targetting this one.
				ik_chain[-2].add_constraint(self.obj, 'IK', 
					pole_subtarget = pole_ctrl.name,
					pole_angle = direction * pi/2,
					subtarget = ik_bone.name
				)
		
		# Stretch mechanism
		str_name = bone_name.replace("ORG", "IK-STR")
		str_bone = self.bone_infos.bone(
			name = str_name, 
			source = self.get_bone(chain[0]),
			tail = copy.copy(self.ik_mstr.head),
			parent = self.limb_root_bone.name,
			bone_group = 'Body: IK-MCH - IK Mechanism Bones'
		)
		str_bone.scale_width(0.4)

		self.ik_tgt_bone.add_constraint(self.obj, 'COPY_LOCATION',
			target = self.obj,
			subtarget = str_bone.name,
			head_tail = 1,
			true_defaults=True
		)

		str_tgt_name = bone_name.replace("ORG", "IK-STR-TGT")
		# Create bone responsible for keeping track of where the feet should be when stretchy IK is ON.
		str_tgt_bone = self.bone_infos.bone(
			name = str_tgt_name, 
			source = org_chain[2], 
			parent = self.ik_mstr,
			bone_group = 'Body: IK-MCH - IK Mechanism Bones'
		)

		arm_length = ik_chain[0].length + ik_chain[1].length
		length_factor = arm_length / str_bone.length
		str_bone.add_constraint(self.obj, 'STRETCH_TO', subtarget=str_tgt_bone.name)
		str_bone.add_constraint(self.obj, 'LIMIT_SCALE', 
			use_max_y = True,
			max_y = length_factor,
			influence = 0
		)

		str_drv = Driver()
		str_drv.expression = "1-stretch"
		var = str_drv.make_var("stretch")
		var.type = 'SINGLE_PROP'
		var.targets[0].id_type = 'OBJECT'
		var.targets[0].id = self.obj
		var.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (self.prop_bone.name, self.ik_stretch_name)

		data_path = 'constraints["Limit Scale"].influence'
		
		str_bone.drivers[data_path] = str_drv

		# Store info for UI
		info = {
			"prop_bone"			: self.prop_bone.name,
			"prop_id" 			: self.ik_stretch_name,
		}
		self.store_ui_data("ik_stretches", self.category, self.limb_name, info)

		# Create custom property
		self.prop_bone.custom_props[self.ik_stretch_name] = CustomProp(self.ik_stretch_name, default=1.0)

		#######################
		##### MORE STUFF ######
		#######################

		if self.params.type == 'LEG':
			ik_chain[-2].parent = self.ik_mstr
			self.prepare_ik_foot(self.ik_tgt_bone, ik_chain[-2:], org_chain[-2:])
		
		self.ik_chain = ik_chain

		for i in range(0, self.params.deform_segments):
			factor_unit = 0.9 / self.params.deform_segments
			factor = 0.9 - factor_unit * i
			self.first_str_counterrotate_setup(self.str_bones[i], self.org_chain[0], factor)

		self.mid_str_transform_setup(self.main_str_bones[1])

		# TODO: Why do we do this? This is bad if we ever want to parent something to the IK control after this, since it will only be parented to the parent IK control.
		self.ik_ctrl = self.ik_mstr.parent if self.params.double_ik_control else self.ik_mstr
		
		self.prepare_and_store_ikfk_info(self.fk_chain, self.ik_chain, pole_ctrl)

	def prepare_and_store_ikfk_info(self, fk_chain, ik_chain, ik_pole):
		""" Prepare the data needed to be stored on the armature object for IK/FK snapping. """
		if self.params.type=='LEG':
			# Ignore toes on the chains.
			fk_chain = fk_chain[:-1]
			ik_chain = ik_chain[:-1]

		info = {	# These parameter names must be kept in sync with Snap_IK2FK in cloudrig.py
			"operator" 				: "armature.ikfk_toggle",
			"prop_bone"				: self.prop_bone.name,
			"prop_id" 				: self.ikfk_name,
			"fk_chain" 				: [b.name for b in fk_chain],
			"ik_chain" 				: [b.name for b in ik_chain],
			"str_chain"				: [b.name for b in self.main_str_bones],
			"double_first_control"	: self.params.double_first_control,
			"double_ik_control"		: self.params.double_ik_control,
			"ik_pole" 				: self.pole_ctrl.name,
			"ik_control"			: self.ik_mstr.name
		}
		self.store_ui_data("ik_switches", self.category, self.limb_name, info)
		self.prop_bone.custom_props[self.ikfk_name] = CustomProp(self.ikfk_name, default=1.0)

	def first_str_counterrotate_setup(self, str_bone, org_bone, factor):
		str_bone.add_constraint(self.obj, 'TRANSFORM',
			name = "Transformation (Counter-Rotate)",
			subtarget = org_bone.name,
			map_from = 'ROTATION', map_to = 'ROTATION',
			use_motion_extrapolate = True,
			from_min_y_rot =   -1, 
			from_max_y_rot =	1,
			to_min_y_rot   =  factor,
			to_max_y_rot   = -factor,
			from_rotation_mode = 'SWING_TWIST_Y'
		)

	def mid_str_transform_setup(self, mid_str_bone):
		""" Set up transformation constraint to mid-limb STR bone that ensures that it stays in between the root of the limb and the IK master control during IK stretching. """
		mid_str_bone = self.main_str_bones[1]
		trans_con_name = 'Transf_IK_Stretch'
		mid_str_bone.add_constraint(self.obj, 'TRANSFORM',
			subtarget = 'root',
			name = trans_con_name,
		)

		trans_drv = Driver()		# Influence driver
		trans_drv.expression = "ik*stretch"
		var_stretch = trans_drv.make_var("stretch")
		var_stretch.type = 'SINGLE_PROP'
		var_stretch.targets[0].id_type = 'OBJECT'
		var_stretch.targets[0].id = self.obj
		var_stretch.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (self.prop_bone.name, self.ik_stretch_name)

		var_ik = trans_drv.make_var("ik")
		var_ik.type = 'SINGLE_PROP'
		var_ik.targets[0].id_type = 'OBJECT'
		var_ik.targets[0].id = self.obj
		var_ik.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (self.prop_bone.name, self.ikfk_name)

		data_path = 'constraints["%s"].influence' %(trans_con_name)

		mid_str_bone.drivers[data_path] = trans_drv

		trans_loc_drv = Driver()
		distance = (self.ik_tgt_bone.head - self.ik_chain[0].head).length
		trans_loc_drv.expression = "max( 0, (distance-%0.4f * scale ) * (1/scale) /2 )" %(distance)

		var_dist = trans_loc_drv.make_var("distance")
		var_dist.type = 'LOC_DIFF'
		var_dist.targets[0].id = self.obj
		var_dist.targets[0].bone_target = self.ik_tgt_bone.name
		var_dist.targets[0].transform_space = 'WORLD_SPACE'
		var_dist.targets[1].id = self.obj
		var_dist.targets[1].bone_target = self.ik_chain[0].name
		var_dist.targets[1].transform_space = 'WORLD_SPACE'
		
		var_scale = trans_loc_drv.make_var("scale")
		var_scale.type = 'TRANSFORMS'
		var_scale.targets[0].id = self.obj
		var_scale.targets[0].transform_type = 'SCALE_Y'
		var_scale.targets[0].transform_space = 'WORLD_SPACE'
		var_scale.targets[0].bone_target = self.fk_chain[0].name

		data_path2 = 'constraints["%s"].to_min_y' %(trans_con_name)
		mid_str_bone.drivers[data_path2] = trans_loc_drv

	def prepare_ik_foot(self, ik_tgt, ik_chain, org_chain):
		ik_foot = ik_chain[0]

		# Create ROLL control behind the foot (Limit Rotation, lock other transforms)
		if self.params.use_foot_roll:	# TODO: Don't like this big if block. Maybe toe part should be moved out of this function, and the if check put before calling of this function, and then this function can be renamed to prepare_footroll.
			sliced_name = slice_name(ik_foot.name)
			roll_name = make_name(["ROLL"], sliced_name[1], sliced_name[2])
			roll_ctrl = self.bone_infos.bone(
				name = roll_name,
				bbone_width = 1/18,
				head = ik_foot.head + Vector((0, self.scale, self.scale/4)),
				tail = ik_foot.head + Vector((0, self.scale/2, self.scale/4)),
				roll = pi,
				custom_shape = self.load_widget('FootRoll'),
				bone_group = 'Body: Main IK Controls',
				parent = ik_tgt
			)

			roll_ctrl.add_constraint(self.obj, 'LIMIT_ROTATION', 
				use_limit_x=True,
				min_x = -90 * pi/180,
				max_x = 130 * pi/180,
				use_limit_y=True,
				use_limit_z=True,
				min_z = -pi/2,
				max_z = pi/2,
			)

			# Create bone to use as pivot point when rolling back. This is read from the metarig and should be placed at the heel of the shoe, pointing forward.
			# We hardcode name for ankle pivot for now. (TODO? I don't know if this could/should be avoided.)
			ankle_pivot = self.generator.metarig.data.bones.get("AnklePivot." + self.side_suffix)
			assert ankle_pivot, "ERROR: Could not find AnklePivot bone in the metarig."
			
			# I want to be able to customize the shape size of the foot controls from the metarig, via ankle pivot bone bbone scale.
			self.ik_mstr._bbone_x = ankle_pivot.bbone_x
			self.ik_mstr._bbone_z = ankle_pivot.bbone_z
			if self.params.double_ik_control:
				self.ik_mstr.parent._bbone_x = ankle_pivot.bbone_x
				self.ik_mstr.parent._bbone_z = ankle_pivot.bbone_z

			ankle_pivot_ctrl = self.bone_infos.bone(
				name = "IK-RollBack." + self.side_suffix,
				bbone_width = self.org_chain[-1].bbone_width,
				head = ankle_pivot.head_local,
				tail = ankle_pivot.tail_local,
				roll = pi,
				bone_group = 'Body: IK-MCH - IK Mechanism Bones',
				parent = ik_tgt
			)

			ankle_pivot_ctrl.add_constraint(self.obj, 'TRANSFORM',
				subtarget = roll_ctrl.name,
				map_from = 'ROTATION',
				map_to = 'ROTATION',
				from_min_x_rot = -90 * pi/180,
				to_min_x_rot = -60 * pi/180,
			)
			
			# Create reverse bones
			# TODO: Does this really need to be a loop? We are just dealing with a foot and a toe, never anything more.
			rik_chain = []
			for i, b in reversed(list(enumerate(org_chain))):
				rik_bone = self.bone_infos.bone(
					name = b.name.replace("ORG", "RIK"),
					source = b,
					head = b.tail.copy(),
					tail = b.head.copy(),
					roll = 0,
					parent = ankle_pivot_ctrl,
					bone_group = 'Body: IK-MCH - IK Mechanism Bones'
				)
				rik_chain.append(rik_bone)
				ik_chain[i].parent = rik_bone

				if i == 1:
					rik_bone.add_constraint(self.obj, 'TRANSFORM',
						subtarget = roll_ctrl.name,
						map_from = 'ROTATION',
						map_to = 'ROTATION',
						from_min_x_rot = 90 * pi/180,
						from_max_x_rot = 166 * pi/180,
						to_min_x_rot = 0 * pi/180,
						to_max_x_rot = 169 * pi/180,
						from_min_z_rot = -60 * pi/180,
						from_max_z_rot = 60 * pi/180,
						to_min_z_rot = 10 * pi/180,
						to_max_z_rot = -10 * pi/180
					)
				
				if i == 0:
					rik_bone.add_constraint(self.obj, 'COPY_LOCATION',
						true_defaults = True,
						target = self.obj,
						subtarget = rik_chain[-2].name,
						head_tail = 1,
					)

					rik_bone.add_constraint(self.obj, 'TRANSFORM',
						name = "Transformation Roll",
						subtarget = roll_ctrl.name,
						map_from = 'ROTATION',
						map_to = 'ROTATION',
						from_min_x_rot = 0 * pi/180,
						from_max_x_rot = 135 * pi/180,
						to_min_x_rot = 0 * pi/180,
						to_max_x_rot = 118 * pi/180,
						from_min_z_rot = -45 * pi/180,
						from_max_z_rot = 45 * pi/180,
						to_min_z_rot = 25 * pi/180,
						to_max_z_rot = -25 * pi/180
					)
					rik_bone.add_constraint(self.obj, 'TRANSFORM',
						name = "Transformation CounterRoll",
						subtarget = roll_ctrl.name,
						map_from = 'ROTATION',
						map_to = 'ROTATION',
						from_min_x_rot = 90 * pi/180,
						from_max_x_rot = 135 * pi/180,
						to_min_x_rot = 0 * pi/180,
						to_max_x_rot = -31.8 * pi/180
					)
			
		# FK Toe bone should be parented between FK Foot and IK Toe.
		fk_toe = self.fk_toe
		fk_toe.parent = None
		fk_toe.add_constraint(self.obj, 'ARMATURE',
			targets = [
				{
					"subtarget" : self.fk_chain[-2].name	# FK Foot
				},
				{
					"subtarget" : ik_chain[-1].name		# IK Toe
				}
			],
		)

		drv1 = Driver()
		drv1.expression = "1-ik"
		var1 = drv1.make_var("ik")
		var1.type = 'SINGLE_PROP'
		var1.targets[0].id_type='OBJECT'
		var1.targets[0].id = self.obj
		var1.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (self.prop_bone.name, self.ikfk_name)

		drv2 = drv1.clone()
		drv2.expression = "ik"

		data_path1 = 'constraints["Armature"].targets[0].weight'
		data_path2 = 'constraints["Armature"].targets[1].weight'
		
		fk_toe.drivers[data_path1] = drv1
		fk_toe.drivers[data_path2] = drv2

	@stage.prepare_bones
	def prepare_org_limb(self):
		# Note: Runs after prepare_org_chain().
		
		# Add Copy Transforms constraints targetting both FK and IK bones.
		# Put driver on only the second constraint.

		for i, org_bone in enumerate(self.org_chain):
			ik_bone = self.bone_infos.find(org_bone.name.replace("ORG", "IK"))
			if self.params.type == 'LEG' and i == len(self.org_chain)-1:
				# Don't add IK constraint to toe bone. It should always use FK control, even in IK mode.
				continue
			ik_ct_name = "Copy Transforms IK"
			ik_con = org_bone.add_constraint(self.obj, 'COPY_TRANSFORMS', true_defaults=True, target=self.obj, subtarget=ik_bone.name, name=ik_ct_name)

			drv = Driver()
			var = drv.make_var()
			var.targets[0].id = self.obj
			var.targets[0].data_path = 'pose.bones["%s"]["%s"]' %(self.prop_bone.name, self.ikfk_name)

			data_path = 'constraints["%s"].influence' %(ik_ct_name)
			org_bone.drivers[data_path] = drv

	@stage.prepare_bones
	def prepare_parent_switch(self):
		parents = []
		if self.params.type=='LEG':
			parents = ['Root', 'Torso', 'Hips', self.side_suffix + ' Leg']
		else:
			parents = ['Root', 'Torso', 'Chest', self.side_suffix + ' Arm']
		
		child_bones = [self.pole_ctrl, self.ik_ctrl]
		child_names = [b.name for b in child_bones]

		side = self.side_prefix.lower()
		limb = self.params.type.lower()
		ik_parents_prop_name = "ik_parents_" + self.limb_name_props

		for cb in child_bones:
			self.rig_child(cb, parents, self.prop_bone, ik_parents_prop_name)
		




		### IK Pole Follow option
		# Create custom property
		default = 1.0 if self.params.type=='LEG' else 0.0
		pole_follow_prop = self.prop_bone.custom_props[self.ik_pole_follow_name] = CustomProp(self.ik_pole_follow_name, default=default)

		# Get the armature constraint from the IK pole's parent, and add the IK master as a new target.
		arm_con_bone = self.pole_ctrl.parent
		arm_con = arm_con_bone.constraints[0][1]
		arm_con['targets'].append({
			"subtarget" : self.ik_ctrl.name
		})

		# Tweak each driver on the IK pole's parent, as well as add a driver to the new target.
		drv = Driver()
		data_path = 'constraints["Armature"].targets[%d].weight' %(len(arm_con['targets'])-1)
		arm_con_bone.drivers[data_path] = drv
		for i, dp in enumerate(arm_con_bone.drivers):
			d = arm_con_bone.drivers[dp]
			d.expression = "(%s) - follow" %d.expression
			if i == len(arm_con_bone.drivers)-1:
				d.expression = "follow"
			follow_var = d.make_var("follow")
			follow_var
			follow_var.type = 'SINGLE_PROP'
			follow_var.targets[0].id_type = 'OBJECT'
			follow_var.targets[0].id = self.obj
			follow_var.targets[0].data_path = 'pose.bones["%s"]["%s"]' % (self.prop_bone.name, self.ik_pole_follow_name)

		# Add option to the UI.
		info = {
			"prop_bone" : self.prop_bone.name,
			"prop_id"	: self.ik_pole_follow_name,

			"operator" : "pose.snap_simple",
			"bones" : [self.pole_ctrl.name],
			"select_bones" : True
		}
		self.store_ui_data("ik_pole_follows", self.category, self.limb_name, info)




		info = {
			"prop_bone" : self.prop_bone.name,			# Name of the properties bone that contains the property that should be changed by the parent switch operator.
			"prop_id" : ik_parents_prop_name, 			# Name of the property
			"texts" : parents,
			
			"operator" : "pose.rigify_switch_parent",
			"icon" : "COLLAPSEMENU",
			
			"bones" : child_names,		# List of child bone names that will be affected by the parent swapping. Often just one.
			"parent_names" : parents,		# List of (arbitrary) names, in order, that should be displayed for each parent option in the UI.
		}
		self.store_ui_data("parents", self.category, self.limb_name, info)

	##############################
	# Parameters

	@classmethod
	def add_parameters(cls, params):
		""" Add the parameters of this rig type to the
			RigifyParameters PropertyGroup
		"""
		super().add_parameters(params)

		params.use_limb_name = BoolProperty(
			name="Custom Limb Name", 
			default=False, 
			description='Specify a name for this limb - There can be exactly two limbs with the same name, a Left and a Right one. This name should NOT include a side indicator such as "Left" or "Right" '
		)
		params.limb_name = StringProperty(default="Left Arm")
		params.type = EnumProperty(name="Type",
		items = (
			("ARM", "Arm", "Arm (Chain of 3)"),
			("LEG", "Leg", "Leg (Chain of 5, includes foot rig)"),
			)
		)
		params.lock_yz = BoolProperty(name="Lock Elbow/Shin YZ", description="Lock Y and Z rotation of the elbow and shin.")

		params.use_category_name = BoolProperty(name="Custom Category Name", default=False, description="Specify a category for this limb. Limbs in the same category will have their settings displayed in the same column")
		params.category_name = StringProperty(default="arms")

		params.pole_offset = FloatProperty(name="Pole Vector Offset", default=1.0)
		params.use_foot_roll = BoolProperty(name="Foot Roll", default=True)

		params.double_first_control = BoolProperty(
			name="Double FK Control", 
			description="The first FK control has a parent control. Having two controls for the same thing can help avoid interpolation issues when the common pose in animation is far from the rest pose",
			default=True,
		)
		params.double_ik_control = BoolProperty(
			name="Double IK Control", 
			description="The IK control has a parent control. Having two controls for the same thing can help avoid interpolation issues when the common pose in animation is far from the rest pose",
			default=True,
		)
		params.display_middle = BoolProperty(
			name="Display Centered", 
			description="Display FK controls on the center of the bone, instead of at its root", 
			default=True,
		)
		params.world_aligned = BoolProperty(
			name="World Aligned Control", 
			description="Ankle/Wrist IK/FK controls are aligned with world axes.", 
			default=True,
		)

	@classmethod
	def parameters_ui(cls, layout, params):
		"""Create the ui for the rig parameters."""
		super().parameters_ui(layout, params)

		layout.label(text="__________________________________________________________________________")

		layout.prop(params, "type")
		if params.type=='LEG':
			layout.prop(params, "use_foot_roll")

		name_row = layout.row()
		limb_column = name_row.column()
		limb_column.prop(params, "use_limb_name")
		if params.use_limb_name:
			limb_column.prop(params, "limb_name", text="")
		category_column = name_row.column()
		category_column.prop(params, "use_category_name")
		if params.use_category_name:
			category_column.prop(params, "category_name", text="")
		
		double_row = layout.row()
		double_row.prop(params, "double_first_control")
		double_row.prop(params, "double_ik_control")
		layout.prop(params, "lock_yz")
		layout.prop(params, "world_aligned")
		layout.prop(params, "pole_offset")
		layout.prop(params, "display_middle")