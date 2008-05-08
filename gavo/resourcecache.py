"""
Accessor functions for the various immutables an archive service might
deal with.

The main purpose of this module is to keep caches of resource descriptors,
templates, etc., the parsing of which may take some time.

All you need to do is provide a function taking a "key" (a string, most
likely) and returning the "resource" and then call

resourcecache.makeCache(<accessorName>, <function>)

After that, clients can call

resourcecache.<accessorName>(key)
"""

import gavo
from gavo import config
from gavo import utils


class CacheRegistry:
	"""is a registry for caches kept to be able to clear them.

	A cache is assumed to be a dicitonary here.
	"""
	def __init__(self):
		self.knownCaches = []
	
	def clearall(self):
		for cache in self.knownCaches:
			for key in cache.keys():
				del cache[key]
	
	def register(self, cache):
		self.knownCaches.append(cache)


_cacheRegistry = CacheRegistry()
clearCaches = _cacheRegistry.clearall


def _makeCache(creator):
	"""returns a callable that returns a resource and caches its results.

	The creator has to be a function taking an id and returning the 
	designated object.
	"""
	cache = {}
	_cacheRegistry.register(cache)
	def func(id):
		if not id in cache:
			try:
				cache[id] = creator(id)
			except Exception, exc:
				cache[id] = exc
				gavo.raiseTb(exc.__class__, str(exc))
		if isinstance(cache[id], Exception):
			raise cache[id]
		else:
			return cache[id]
	return func


def makeCache(name, callable):
	"""creates a new function name to cache results to calls to callable.
	"""
	globals()[name] = _makeCache(callable)
