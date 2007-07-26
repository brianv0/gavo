"""
A grammar that takes values from web contexts.
"""

import urllib
import itertools

import gavo
from gavo import utils
from gavo.parsing import grammar
from gavo.web.querulator import condgens


class ContextKey(utils.Record):
	"""is a key for a ContextGrammar.
	"""
	def __init__(self, initvals):
		utils.Record.__init__(self, {
				"label": None,      # Human-readable label for display purposes
				"widgetHint": None, # Hint for building a widget
				"type": "real",     # The type of this key
				"condgen": None,    # Condition Generator to use
				"name": utils.RequiredField, # the "preterminal" we provide
				"default": "",    # a string containing a proper default value
			}, initvals)

	def _makeWidget(self, context):
		if self.get_widgetHint()==None:
			return ('<input type="text" name="%s"'
			' value="%s">')%(self.get_name(), 
				self.get_default())
		elif self.get_widgetHint()=="condgen":
			return condgens.makeCondGen(self.get_name(), "operator",
				["", "=", self.get_condgen()]).asHtml(context)
		else:
			raise Error("Invalid widget hint: %s"%self.get_widgetHint())


	def asHtml(self, context):
		widget = self._makeWidget(context)
		return ('<div class="condition"><div class="clabel">%s</div>'
			' <div class="quwidget">%s</div></div>'%(
				self.get_label(),
				widget))


class ContextGrammar(grammar.Grammar):
	"""is a grammar that gets values from a context.
	"""
	def __init__(self):
		grammar.Grammar.__init__(self, {
			"docKeys": utils.ListField,
			"rowKeys": utils.ListField,
		})

	def _iterRows(self):
		names = [k.get_name() for k in self.get_rowKeys()]
		inputs = [self.inputFile.getlist(name) 
			for name in names]
		baseLen = len(inputs[0])
		if sum([abs(len(i)-baseLen) for i in inputs]):
			raise gavo.Error("Input sequences have unequal lengths")
		for tuple in itertools.izip(*inputs):
			yield dict(itertools.izip(names, tuple))
	
	def _getDocumentRow(self):
		docdict = {}
		for key in self.get_docKeys():
			docdict[key.get_name()] = self.inputFile.getfirst(key.get_name())
		return docdict
	
	def parse(self, context):
		self.curInputFileName = "<Context>"
		self.inputFile = context
		self._parse(None)
		self.inputFile = None
		self.curInputFileName = None
