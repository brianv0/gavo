"""
A grammar that takes values from web contexts.
"""

import urllib
import itertools

import gavo
from gavo import record
from gavo import datadef
from gavo.parsing import grammar
from gavo.web.querulator import condgens


class InputKey(datadef.DataField):
	"""is a key for a ContextGrammar.
	"""
	def __init__(self, initvals):
		datadef.DataField.__init__(self, **initvals)

	def _makeWidget(self, context):
		return ('<input type="text" name="%s"'
		' value="%s">')%(self.get_name(), 
			self.get_default())

	def asHtml(self, context):
		widget = self._makeWidget(context)
		return ('<div class="condition"><div class="clabel">%s</div>'
			' <div class="quwidget">%s</div></div>'%(
				self.get_label(),
				widget))


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

	def _iterRows(self, ctx):
		yield self._getDocdict(ctx)
	
	def _getDocdict(self, ctx):
		docdict = {}
		for key in self.get_inputKeys():
			docdict[key.get_dest()] = ctx.sourceFile.get(key.get_dest())
		return docdict

	def getInputFields(self):
		return self.get_inputKeys()


if __name__=="__main__":
	from gavo import textui
	from gavo import parsing
	parsing.verbose = True
	cg = ContextGrammar()
	cg.addto_inputKeys(InputKey({"tablehead": "FK6 Number", "default": "56", 
		"dest": "star", "dbtype": "text", "optional": "False"}))
	cg.addto_inputKeys(InputKey({"tablehead": "Start date",
		"default": "", "dest": "startDate", "dbtype": "date"}))
	cg.addto_inputKeys(InputKey({"tablehead": "End date",
		"default": "", "dest": "endDate", "dbtype": "date"}))
	cg.addto_inputKeys(InputKey({"tablehead": "Interval of generation (hrs)",
		"default": "24", "dest": "hrInterval", "dbtype": "integer", 
		"optional": "False"}))
	import processors
	cg.addto_rowProcs(
		processors.DateExpander([("start", "startDate", ""),
			("end", "endDate", ""), ("hrInterval", "hrInterval", "")]))
	class FakeContext:
		sourceFile = {"star": "22", "startDate": "2008-12-12", 
			"endDate": "2008-12-24", "hrInterval": "24"}
		sourceName = "<fake>"
		def processRowdict(self, rowdict):
			print rowdict
		def processDocdict(self, docdict):
			pass
		def atExpand(self, val):
			return val
	cg.parse(FakeContext())

