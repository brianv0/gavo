""" Global exceptions for the GAVO data center software.

All exceptions escaping modules should inherit from Error in some way.
Exceptions orginating in only one module should usually be defined there,
exceptions should only be defined here if they are raised by more than
one module.

Of course, for certain errors, built-in exceptions (e.g., NotImplemented
or so) may be raised and propagated as well, but these should always
signify internal bugs, never things a user should be confronted with
under normal circumstances.

And then there's stuff like fancyconfig that's supposed to live
independently of the rest.  It's ok if those raise other Exceptions,
but clearly there shouldn't be many of those, or error reporting will
become an even worse nightmare than it already is.
"""


#c Copyright 2007-2009 the GAVO Project.
#c
#c This program is free software, covered by the GNU GPL.  See COPYING.

from gavo.utils.fancyconfig import NoConfigItem


class Error(Exception):
	"""is the base class for all exceptions that can be expected to escape
	a module.

	Apart from the normal message, you can give a "hint" constructor argument.
	"""
	def __init__(self, msg="", hint=None):
		Exception.__init__(self, msg)
		self.msg = msg
		self.hint = hint


class StructureError(Error):
	"""is raised if an error occurs during the construction of
	structures.

	You can construct these with pos; this is an opaque object that, when
	stringified, should expand to something that gives the user a rough idea
	of where something went wrong.

	Since you will usually not know where you are in the source document
	when you want to raise a StructureError, xmlstruct will try
	to fill pos in when it's still None when it sees a StructureError.
	Thus, you're probably well advised to leave it blank.
	"""
	def __init__(self, msg, pos=None, hint=None):
		Error.__init__(self, msg, hint=hint)
		self.pos = pos


	def __str__(self):
		if self.pos is None:
			return self.args[0]
		else:
			return "At %s: %s"%(str(self.pos), self.args[0])


class LiteralParseError(StructureError):
	"""is raised if an attribute literal is somehow bad.

	LiteralParseErrors are constructed with the name of the attribute
	that was being parsed, the offending literal, and optionally a 
	parse position and a hint.
	"""
	def __init__(self, attName, literal, pos=None, hint=None):
		StructureError.__init__(self, "'%s' is not a valid value for %s"%(
			literal, attName), pos=pos, hint=hint)
		self.attName, self.attVal = attName, literal


class BadCode(StructureError):
	"""is raised when some code could not be compiled.

	BadCodes are constructed with the offending code, a code type,
	the original exception, and optionally a hint and a position.
	"""
	def __init__(self, code, codeType, origExc, hint=None, pos=None):
		StructureError.__init__(self, "Bad source code in %s (%s)"%(
				codeType, unicode(origExc)), 
			pos=pos, hint=hint)
		self.code, self.codeType = code, codeType
		self.origExc = origExc


class ValidationError(Error):
	"""is raised when the validation of a field fails.  
	
	ValidationErrors are constructed with a message, a column name,
	and optionally a row (i.e., a dict) and a hint.
	"""
	def __init__(self, msg, colName, row=None, hint=None):
		Error.__init__(self, msg, hint=hint)
		self.msg = msg
		self.colName, self.row = colName, row
	
	def __str__(self):
		recStr = ""
#		if self.row:
#			recStr = ", found in: row %s"%repr(self.row)
		return "%s%s"%(self.msg, recStr)


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
	def __init__(self, lookedFor, what, within, hint=None):
		Error.__init__(self, "ignored", hint=hint)
		self.lookedFor, self.what = lookedFor, what
		self.within = within

	def __str__(self):
		return "%s %r could not be located in %s"%(
			self.what, self.lookedFor, self.within)

class RDNotFound(NotFoundError):
	"""is raised when an RD cannot be located.
	"""
	def __init__(self, rdId, hint=None):
		NotFoundError.__init__(self, rdId, hint=hint, what="resource descriptor",
			within="file system")


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


class SkipThis(ExecutiveAction):
	"""is caught in rsc.makeData.  You can raise this at any place during
	source processing to skip the rest of this source but the go on.

	You should pass something descriptive as message so upstream can
	potentially report something is skipped.
	"""
