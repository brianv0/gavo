"""
A Grammar class that imports a user-defined module and takes a grammar from
there.

You should inherit your grammar from the UserGrammar class contained in
here and override the methods specified there.
"""

import imp
import os
import weakref

import gavo
from gavo import record
from gavo.parsing import grammar


_knownModules = {}


def getModuleName():
	i = 0
	while True:
		name = "usergrammar%d"%i
		if name not in _knownModules:
			_knownModules[name] = None
			return name


class CustomGrammar(grammar.Grammar):
	"""is an adapter for a user-defined grammar.
	"""
# The one real hack in here is that the user grammar is instanciated
# lazily, i.e., when one of its methods is required.  In this way, we
# already have a data descriptor (which we don't when this thing is
# constructed).  We don't check that later parseContexts have the same
# data descriptor.  This shouldn't hurt but still is a wart.
	def __init__(self, additionalFields={}, initvals={}):
		self.fields = {
			"module": record.RequiredField,
		}
		self.fields.update(additionalFields)

		# Seperate attributes for the user grammars from those for us
		grammarAttrs, self.userAttrs = {}, {}
		for key, val in initvals.iteritems():
			if key in self.fields or key in grammar.Grammar._grammarAttributes:
				grammarAttrs[key] = val
			else:
				self.userAttrs[key] = val

		grammar.Grammar.__init__(self, additionalFields=self.fields, 
			initvals=grammarAttrs)
		self.realGrammar = None
	
	def _loadModule(self, parseContext):
		parentDD = parseContext.getDataSet().getDescriptor()
		modPath, modName = os.path.dirname(self.get_module()
			), os.path.basename(self.get_module())
		modPath = os.path.join(parentDD.getRD().get_resdir(), modPath)
		try:
			file, pathname, description = imp.find_module(modName, [modPath])
		except ImportError:
			raise gavo.Error("Bad or missing custom grammar: %s"%self.get_module())
		try:
			imp.acquire_lock()
			modname = getModuleName()
			self.userModule = imp.load_module(modname, file, pathname, description)
			_knownModules[modname] = self.userModule
		finally:
			imp.release_lock()
			file.close()
		initvals = self.dataStore.copy()
		for f in self.fields:
			del initvals[f]
		self.realGrammar = self.userModule.getGrammar(parentDD, self.userAttrs,
			initvals=initvals)

	def _ensureRealGrammar(self, parseContext):
		if not self.realGrammar:
			self._loadModule(parseContext)
	
	def parse(self, parseContext):
		self._ensureRealGrammar(parseContext)
		return self.realGrammar.parse(parseContext)
	
	def _setupParsing(self, parseContext):
		self._ensureRealGrammar(parseContext)
		return self.realGrammar._setupParsing(parseContext)


class UserGrammar(grammar.Grammar):
	def __init__(self, parentDD, userAttrs, initvals):
		self.parentDD = weakref.proxy(parentDD)
		self.userAttrs = userAttrs
		grammar.Grammar.__init__(self, initvals=initvals)
	
	def resolvePath(self, path):
		return os.path.join(self.parentDD.getRD().get_resdir(), path)
	
	def _getDocdict(self, parseContext):
		return {}
