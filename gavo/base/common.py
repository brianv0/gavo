import contextlib
import threading

from gavo.utils.excs import *


class NotGivenType(type):
	def __str__(self):
		raise StructureError("%s cannot be stringified"%self.__class__.__name__)

	__unicode__ = __str__

	def __repr__(self):
		return "<Not given/empty>"

	def __nonzero__(self):
		return False


class NotGiven(object):
	"""A sentinel class for defaultless values that can remain undefined.
	"""
	__metaclass__ = NotGivenType


class Ignore(ExecutiveAction):
	"""An executive action causing an element to be not adopted by its
	parent.

	Raise this in -- typically -- onElementComplete if the element just
	built goes somewhere else but into its parent structure (or is
	somehow benignly unusable).  Classic use case: Active Tags.
	"""


class Replace(ExecutiveAction):
	"""An executive action replacing the current child with the Exception's
	argument.

	Use this sparingly.  I'd like to get rid of it.
	"""
	def __init__(self, newOb, newName=None):
		self.newOb, self.newName = newOb, newName


class Parser(object):
	"""is an object that routes events.

	It is constructed with up to three functions for handling start,
	value, and end events; these would override methods start_, end_,
	or value_.  Thus, you can simply implement when inheriting from
	Parser.  In that case, no call the the constructor is necessary
	(i.e., Parser works as a mixin as well).
	"""
	def __init__(self, start=None, value=None, end=None):
		self.start, self.value, self.end = start, value, end
	
	def feedEvent(self, ctx, type, name, value):
		if type=="start":
			return self.start_(ctx, name, value)
		elif type=="value":
			return self.value_(ctx, name, value)
		elif type=="end":
			return self.end_(ctx, name, value)
		else:
			raise StructureError("Illegal event type while building: '%s'"%type)
