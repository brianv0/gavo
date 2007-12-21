"""
Code to deal with "static" resources. 

Static resources are defined by hand somewhere below
inputs/__system__/services/*.rr as sets of key-value pairs.  These are
parsed here into StaticResource instances.  They only contain meta data.
"""

import os

from gavo import resourcecache
from gavo.parsing import kvgrammar
from gavo.parsing import meta
from gavo.parsing import resource
from gavo.parsing import typeconversion


# The path to the resource descriptor for the servicelist & c
rdId = "__system__/services/services"


class ParseContext(resource.ParseContext):
	"""is a parse context for static resources.

	It will add all items in the doc- and rowdicts it gets as meta data
	in its data set.
	"""
	def _makeRowTargets(self):
		return
	
	def processRowdict(self, rowdict):
		for key, val in rowdict.iteritems():
			self.dataSet.addMeta(name=key, content=val)
	
	def processDocdict(self, docdict):
		self.dataSet.processRowdict(docdict)


class _FakeDescriptor:
	"""I'm too lazy to make a real data descriptor for these, but need something
	that satisfies the parse context implementation.  And that's it...
	"""
	def __init___(self):
		pass
	
	def getRD(self):
		return None

_descriptor = _FakeDescriptor()


class StaticResource(meta.MetaMixin):
	"""is a static Resource.
	"""
	def __init__(self, srcPath):
		self.srcPath = srcPath

	def getDescriptor(self):
		return _descriptor


grammar = kvgrammar.KeyValueGrammar()
literalParser = typeconversion.LiteralParser("utf-8")

def loadStaticResource(id):
	
	fName = os.path.join(resourcecache.getRd(rdId).get_resdir(), id)
	res = StaticResource(fName)
	pc = ParseContext(fName, res, literalParser)
	grammar.parse(pc)
	return res


if __name__=="__main__":
	m = loadStaticResource("__system__/services/registryrecs/registry.rr")
	print m.getMeta("managedAuthority")
