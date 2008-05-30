"""
Code for element generators.

Element generators are "macros" for resouce descriptors.  They can
be referenced in the xml serialization through 
<elgen name="whatever" [args]/>.  This will try to resolve to a generator
registered through registerElgen that then yields "events" used up by
a nodebuilder.NodeBuilder.
"""

import gavo

_elgens = {}

def registerElgen(name, callable):
	_elgens[name] = callable

def getElgen(name):
	try:
		return _elgens[name]
	except KeyError:
		raise gavo.Error("Unknown element generator: %s (did you"
			" import its module?)"%name)
