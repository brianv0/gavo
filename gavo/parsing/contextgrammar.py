"""
A grammar that takes values from web contexts.
"""

import urllib
import itertools

import formal

import gavo
from gavo import record
from gavo import datadef
from gavo import typesystems
from gavo import unitconv
from gavo.parsing import grammar
from gavo.web import gwidgets
from gavo.web import vizierexprs


class ContextGrammar(grammar.Grammar):
	"""is a grammar that gets values from a context.

	A funky property of these is that they return the context values twice,
	once as docdict, and a second time as rowdict.  This is done in order
	to let macros operate on the context values to generate more rows.
	"""
	def __init__(self, initvals={}):
		grammar.Grammar.__init__(self, {
			"inputKeys": record.ListField,
		}, initvals)

	def _iterRows(self, parseContext):
		yield self._getDocdict(parseContext)
	
	def _getDocdict(self, parseContext):
		docdict = {}
		for key in self.get_inputKeys():
			docdict[key.get_dest()] = parseContext.sourceFile.get(key.get_dest())
		return docdict

	def getInputFields(self):
		return self.get_inputKeys()

