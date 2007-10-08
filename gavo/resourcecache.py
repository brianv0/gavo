"""
Accessor functions for the various immutables an archive service might
deal with.

The main purpose of this module is to keep caches of resource descriptors,
templates, etc., the parsing of which may take some time.
"""

from gavo.parsing import importparser


def _makeCache(creator):
	"""returns a callable that returns a resource and caches its results.

	The creator has to be a function taking an id and returning the 
	designated object.
	"""
	cache = {}
	def func(id):
		if not id in cache:
			cache[id] = creator(id)
		return cache[id]
	return func


getRd = _makeCache(importparser.getRd)
