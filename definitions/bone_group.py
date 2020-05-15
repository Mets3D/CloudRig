from ..rigs import cloud_utils
import bpy
from .id import IDCollection

# Default BoneGroup color schemes that come with Blender.
presets = [
	[(0.6039215922355652, 0.0, 0.0), (0.7411764860153198, 0.06666667014360428, 0.06666667014360428), (0.9686275124549866, 0.03921568766236305, 0.03921568766236305)],
	[(0.9686275124549866, 0.250980406999588, 0.0941176563501358), (0.9647059440612793, 0.4117647409439087, 0.07450980693101883), (0.9803922176361084, 0.6000000238418579, 0.0)],
	[(0.11764706671237946, 0.5686274766921997, 0.03529411926865578), (0.3490196168422699, 0.7176470756530762, 0.04313725605607033), (0.5137255191802979, 0.9372549653053284, 0.11372549831867218)],
	[(0.03921568766236305, 0.21176472306251526, 0.5803921818733215), (0.21176472306251526, 0.40392160415649414, 0.874509871006012), (0.3686274588108063, 0.7568628191947937, 0.9372549653053284)],
	[(0.6627451181411743, 0.16078431904315948, 0.30588236451148987), (0.7568628191947937, 0.2549019753932953, 0.41568630933761597), (0.9411765336990356, 0.364705890417099, 0.5686274766921997)],
	[(0.26274511218070984, 0.0470588281750679, 0.4705882668495178), (0.3294117748737335, 0.22745099663734436, 0.6392157077789307), (0.529411792755127, 0.3921568989753723, 0.8352941870689392)],
	[(0.1411764770746231, 0.4705882668495178, 0.3529411852359772), (0.2352941334247589, 0.5843137502670288, 0.4745098352432251), (0.43529415130615234, 0.7137255072593689, 0.6705882549285889)],
	[(0.29411765933036804, 0.4392157196998596, 0.4862745404243469), (0.41568630933761597, 0.5254902243614197, 0.5686274766921997), (0.6078431606292725, 0.760784387588501, 0.803921639919281)],
	[(0.9568628072738647, 0.7882353663444519, 0.0470588281750679), (0.9333333969116211, 0.760784387588501, 0.21176472306251526), (0.9529412388801575, 1.0, 0.0)],
	[(0.11764706671237946, 0.125490203499794, 0.1411764770746231), (0.2823529541492462, 0.2980392277240753, 0.33725491166114807), (1.0, 1.0, 1.0)],
	[(0.43529415130615234, 0.18431372940540314, 0.41568630933761597), (0.5960784554481506, 0.2705882489681244, 0.7450980544090271), (0.8274510502815247, 0.1882353127002716, 0.8392157554626465)],
	[(0.4235294461250305, 0.5568627715110779, 0.13333334028720856), (0.49803924560546875, 0.6901960968971252, 0.13333334028720856), (0.7333333492279053, 0.9372549653053284, 0.35686275362968445)],
	[(0.5529412031173706, 0.5529412031173706, 0.5529412031173706), (0.6901960968971252, 0.6901960968971252, 0.6901960968971252), (0.8705883026123047, 0.8705883026123047, 0.8705883026123047)],
	[(0.5137255191802979, 0.26274511218070984, 0.14901961386203766), (0.545098066329956, 0.3450980484485626, 0.06666667014360428), (0.7411764860153198, 0.41568630933761597, 0.06666667014360428)],
	[(0.0313725508749485, 0.19215688109397888, 0.05490196496248245), (0.1098039299249649, 0.26274511218070984, 0.04313725605607033), (0.2039215862751007, 0.38431376218795776, 0.16862745583057404)],
]

class BoneGroup:
	# TODO: This should extend list, and self.bones=[] would become that list, remove_bone() would be inherited as remove(), etc.
	def __init__(self, name="Group", normal=None, select=None, active=None, *, preset=-1):
		self.name = name

		self.color_set = 'CUSTOM'
		self.normal = [0, 0, 0]
		self.select = [0, 0, 0]
		self.active = [0, 0, 0]

		if len(presets) > preset > -1:
			self.normal = presets[preset][0]
			self.select = presets[preset][1]
			self.active = presets[preset][2]
		else:
			if not normal and not select and not active:
				self.color_set = 'DEFAULT'

		if normal: self.normal = normal
		if select: self.select = select
		if active: self.active = active

		self.bones = []

	def __str__(self):
		return self.name

	def remove_bone(self, boneinfo):
		""" Remove a bone from this group. """
		if boneinfo in self.bones:
			boneinfo._bone_group = None
			self.bones.remove(boneinfo)

	def assign_bone(self, boneinfo):
		""" Assign a bone to this group. """
		# If it's already assigned to another group, remove it from there.
		if boneinfo._bone_group and boneinfo._bone_group != self:
			boneinfo.bone_group.remove_bone(boneinfo)
		boneinfo._bone_group = self
		self.bones.append(boneinfo)

	def make_real(self, rig):
		""" Create this bone group and assign the bones where possible. """
		bgs = rig.pose.bone_groups

		if not self.bones:
			# If the group doesn't contain any bones, don't create it.
			return

		bg = bgs.get(self.name)
		if not bg:
			bg = bgs.new(name=self.name)
			bg.color_set = self.color_set
			bg.colors.normal = self.normal[:]
			bg.colors.select = self.select[:]
			bg.colors.active = self.active[:]
		
		for boneinfo in self.bones:
			real_bone = rig.pose.bones.get(boneinfo.name)
			if not real_bone: 
				continue
			real_bone.bone_group = bg

class BoneGroupContainer(IDCollection):
	def __init__(self):
		self.coll_type = BoneGroup
	
	def ensure(self, name, normal=None, select=None, active=None, *, preset=-1):
		""" Return a bone group with the given name if it exists, otherwise create it. """
		if name in self:
			return self[name]

		self[name] = BoneGroup(name, normal, select, active, preset=preset)
		return self[name]

	def make_real(self, rig):
		""" Create these bone groups and assign the bones where possible. """
		for bg in self.values():
			bg.make_real(rig)