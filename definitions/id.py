import bpy
from .. import utils

class ID:
	def __init__(self):
		self.name = ""
		self.custom_properties = {}	# (name : CustomProp()) dictionary

	def __str__(self):
		return self.name

	def make_real(self, target, skip=[], recursive=False):
		utils.copy_attributes(self, target, skip, recursive)
		return target

class IDCollection(dict):
	def __init__(self, coll_type):
		# coll_type is a class which can be initialized without any parameters.
		self.coll_type = coll_type

	def new(self, name, **kwargs):
		self[name] = self.coll_type(**kwargs)
	
	def ensure(self, name, **kwargs):
		""" If an element with a given name doesn't exist, create and return it. """
		if name not in self:
			self.new(name, **kwargs)
		
		return self[name]