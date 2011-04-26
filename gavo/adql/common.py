"""
Exceptions and helper functions for ADQL processing.

This module should be clean for from import *
"""

from gavo import utils

class Error(utils.Error):
	"""A base class for the exceptions from this module.
	"""
# XXX todo: We should wrap pyparsing ParseExceptions as well.
	pass

class NotImplementedError(Error):
	"""is raised for features we don't (yet) support.
	"""

class ColumnNotFound(Error, utils.NotFoundError):
	"""is raised if a column name cannot be resolved.
	"""
	def __init__(self, colName, hint=None):
		utils.NotFoundError.__init__(self, colName, "column", "table metadata",
			hint=hint)

class TableNotFound(Error, utils.NotFoundError):
	"""is raised when a table name cannot be resolved.
	"""
	def __init__(self, tableName, hint=None):
		utils.NotFoundError.__init__(self, tableName, "table", "table metadata",
			hint=hint)


class AmbiguousColumn(Error):
	"""is raised if a column name matches more than one column in a
	compound query.
	"""

class NoChild(Error):
	"""is raised if a node is asked for a non-existing child.
	"""
	def __init__(self, searchedType, toks):
		self.searchedType, self.toks = searchedType, toks
	
	def __str__(self):
		return "No %s child found in %s"%(self.searchedType, self.toks)

class MoreThanOneChild(NoChild):
	"""is raised if a node is asked for a unique child but has more than
	one.
	"""
	def __str__(self):
		return "Multiple %s children found in %s"%(self.searchedType, 
			self.toks)

class BadKeywords(Error):
	"""is raised when an ADQL node is constructed with bad keywords.

	This is a development help and should not occur in production code.
	"""

class UfuncError(Error):
	"""is raised if something is wrong with a call to a user defined
	function.
	"""

class GeometryError(Error):
	"""is raised if something is wrong with a geometry.
	"""

class RegionError(GeometryError):
	"""is raised if a region specification is in some way bad.
	"""

class FlattenError(Error):
	"""is raised when something cannot be flattened.
	"""


class Absent(object):
	"""is a sentinel to pass as default to nodes.getChildOfType.
	"""


def getUniqueMatch(matches, colName):
	"""returns the only item of matches if there is exactly one, raises an
	appropriate exception if not.
	"""
	if len(matches)==1:
		return matches[0]
	elif not matches:
		raise ColumnNotFound(colName)
	else:
		matches = set(matches)
		if len(matches)!=1:
			raise AmbiguousColumn(colName)
		else:
			return matches.pop()
