"""
Functions for adding defaults to STC-S concrete syntax trees.

Default addition is governed by the two dicts at the bottom of
the module:

* pathFunctions -- maps path tuples to handling functions.  If there
  is a match here, no name-based defaulting is done
* nodeNameFunctions -- maps the last element of a path tuple to
  handling functions.
"""

from gavo.stc.common import *


def getSpaceFlavor(node):
	if node["type"]=="Convex":
		return "UNITSPHER"
	else:
		return "SPHER2"


def getSpaceUnit(node):
	if node["frame"].startswith("GEO"):
		return ["deg", "deg", "m"]
	elif node["flavor"].startswith("CART"):
		return ["m"]
	else:
		return ["deg"]


def getRedshiftUnit(node):
	if node["redshiftType"]=="VELOCITY":
		return ["km/s"]
	else:
		return ["nil"]


def _addDefaultsToNode(node, defaults):
	"""adds defaults to node.

	defaults is a sequence of (key, default) pairs, where default is either
	a string (which gets added in a list node), a list (which gets added
	directly) or a function(node) -> string or list to obtain the default.

	Values are only added to a node if the correponding key is not yet
	present.
	"""
	for key, value in defaults:
		if key not in node:
			if not isinstance(value, (basestring, list)):
				value = value(node)
			node[key] = value


def _makeDefaulter(defaults):
	"""returns a defaulting function filling in what is defined in
	defaults.
	"""
	def func(node):
		return _addDefaultsToNode(node, defaults)
	return func


# A dict mapping the last element of a node path to a callable supplying
# defaults.
nodeNameFunctions = {
	"space": _makeDefaulter([
		("frame", "UNKNOWNFrame"),
		("refpos", "UNKNOWNRefPos"),
		("flavor", getSpaceFlavor),
		("unit", getSpaceUnit)]),
	"time": _makeDefaulter([
		("timescale", "nil"),
		("refpos", "UNKNOWNRefPos"),
		("unit", "s")]),
	"spectral": _makeDefaulter([
		("refpos", "UNKNOWNRefPos"),
		("unit", "Hz")]),
	"redshift": _makeDefaulter([
		("refpos", "UNKNOWNRefPos"),
		("redshiftType", "VELOCITY"),
		("unit", getRedshiftUnit),
		("dopplerdef", "OPTICAL")]),
}


# A dict mapping full paths to a callable supplying defaults
pathFunctions = {
}
