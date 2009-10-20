""" Global exceptions for the GAVO data center software.

All exceptions escaping modules should inherit from Error in some way.
Exceptions orginating in only one module should usually be defined there,
exceptions should only be defined here if they are raised by more than
one module.

Of course, for certain errors, built-in exceptions (e.g., NotImplemented
or so) may be raised and propagated as well, but these should always
signify internal bugs, never things a user should be confronted with.

And then there's stuff like fancyconfig that's supposed to live
independently of the rest.  It's ok if those raise other Exceptions,
but clearly there shouldn't be many of those, or error reporting will
become an even worse nightmare than it already is.
"""


#c Copyright 2009 the GAVO Project.
#c
#c This program is free software, covered by the GNU GPL.  See COPYING.

from gavo.utils.fancyconfig import NoConfigItem


class Error(Exception):
	"""is the base class for all exceptions that can be expected to escape
	a module.
	"""

class RDNotFound(Error):
	"""is raised by top-level rscdesc if a requested resource descriptor
	cannot be found.
	"""

class StructureError(Error):
	"""is raised if an error occurs during the construction of
	structures.
	"""

class ValidationError(Error):
	"""is raised when the validation of a field fails.  It has a colName
	attribute containing the field name and an optional row attribute
	saying which row caused the error.
	"""
	def __init__(self, msg, colName, row=None):
		Error.__init__(self, msg)
		self.msg = msg
		self.colName, self.row = colName, row
	
	def __str__(self):
		recStr = ""
#		if self.row:
#			recStr = ", found in: row %s"%repr(self.row)
		return "%s%s"%(self.msg, recStr)

class LiteralParseError(StructureError):
	"""is raised if an attribute literal is somehow bad.

	These have extra attributes attName and attVal.
	"""
	def __init__(self, msg, name, literal):
		StructureError.__init__(self, msg)
		self.attName, self.attVal = name, literal

class SourceParseError(Error):
	"""is raised when some syntax error occurs during a source parse.

	They are constructed with the offending input construct (a source line
	or similar, None in a pinch) and the result of the grammar's getLocator
	call.
	"""
	def __init__(self, msg, offending=None, location="unspecified location"):
		Error.__init__(self, msg)
		self.offending, self.location = offending, location

class DataError(Error):
	"""is raised when something is wrong with a data set.
	"""

class ReportableError(Error):
	"""is raised when something decides it can come up with an error message
	that should be presented to the user as-is.

	UIs should, consequently, just dump the payload and not try adornments.
	The content should be treated as a unicode string.
	"""

class NotFoundError(Error):
	"""is raised when something is asked for something that does not exist.

	lookedFor can be an arbitrary object, so be careful when your repr it --
	that may be long.
	"""
	def __init__(self, msg, lookedFor, what=None):
		Error.__init__(self, msg)
		self.lookedFor, self.what = lookedFor, what


class ExecutiveAction(Exception):
	"""is a base class for exceptions that are supposed to break out of
	deep things and trigger actions higher up.
	"""

class Replace(ExecutiveAction):
	"""is caught during adoption of children by ParseableStructures.
	The exception's value will become the new child.
	"""
	def __init__(self, newOb, newName=None):
		self.newOb, self.newName = newOb, newName
