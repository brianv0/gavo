"""
A Grammar class that imports a user-defined module and takes the RowIterator
from there.

The module has to define a RowIterator derived from CustomRowIterator.  It may
define a function makeDataPack receiving the grammar as its argument and
returning anything.  This anything will then be available as
self.grammar.dataPack to the row iterator.  Use this for expensive, one-time
preparations your row iterator has to perform.
"""

import os
import weakref

from gavo import base
from gavo import rscdef
from gavo import utils
from gavo.grammars import common


_knownModules = {}


def getModuleName():
	i = 0
	while True:
		name = "usergrammar%d"%i
		if name not in _knownModules:
			_knownModules[name] = None
			return name


class CustomGrammar(common.Grammar, base.RestrictionMixin):
	"""A Grammar with a user-defined row iterator taken from a module.

	See the separate document on user code in the DC on how to define custom
	grammars.
	"""
#	To save on time when initializing the grammar (which happens at
#	RD parsing time), we delay initializing the user grammar to when
#	it's actually used (which happens much less frequently than loading
#	the RD).

	name_ = "customGrammar"

	_module = rscdef.ResdirRelativeAttribute("module", default=base.Undefined,
		description="Path to module containing your row iterator.", copyable=True)

	def _initUserGrammar(self):
		self.userModule, _ = utils.loadPythonModule(self.module)
		self.rowIterator = self.userModule.RowIterator
		if hasattr(self.userModule, "makeDataPack"):
			self.dataPack = self.userModule.makeDataPack(self)

	def parse(self, *args, **kwargs):
		if not hasattr(self, "userModule"):
			self._initUserGrammar()
		return common.Grammar.parse(self, *args, **kwargs)

rscdef.registerGrammar(CustomGrammar)


class CustomRowIterator(common.RowIterator):
	"""is a base class for custom row iterators.

	Implement at least _iterRows.  And pass on any keyword args to __init__
	to the next constructor.
	"""
