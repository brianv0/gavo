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
from gavo.parsing import grammar
from gavo.web import gwidgets
from gavo.web import vizierexprs


class InputKey(datadef.DataField):
	"""is a key for a ContextGrammar.
	"""
	additionalFields = {
		"formalType":    None, # nevow formal type to use.
		"widgetFactory": None, # Python code to generate a formal widget factory
		                       # for this field.
		"showitems": 3    # items to show in selections
	}

	def set_widgetFactory(self, widgetFactory):
		"""sets the widget factory either from source code or from a formal
		WidgetFactory object.
		"""
		if isinstance(widgetFactory, basestring):
			self.dataStore["widgetFactory"] = gwidgets.makeWidgetFactory(
				widgetFactory)
		else:
			self.dataStore["widgetFactory"] = widgetFactory

	def get_formalType(self):
		return self.dataStore.get("formalType") or typesystems.sqltypeToFormal(
			self.get_dbtype())[0](required=not self.get_optional())

	def _setAutoWidget(self):
		"""returns a widget factory appropriate for dbtype and values.

		For non-enumerated fields, this is always formal.TextInput, since we 
		accept vizier-like expressions for them on auto.
# XXX TODO: handle booleans
		"""
		if self.isEnumerated():
			self.set_formalType(
				typesystems.sqltypeToFormal(self.get_dbtype())[0]())
			if self.get_values().get_multiOk():
				self.set_widgetFactory(formal.widgetFactory(
					gwidgets.SimpleMultiSelectChoice,
					[str(i) for i in self.get_values().get_options()],
					self.get_showitems()))
			else:
				items = self.get_values().get_options().copy()
				items.remove(self.get_values().get_default())
				self.set_widgetFactory(formal.widgetFactory(
					gwidgets.SimpleSelectChoice,
					[str(i) for i in items], self.get_default()))
		else:
			self.set_formalType(formal.String())
			self.set_widgetFactory(formal.TextInput)

	@classmethod
	def fromDataField(cls, dataField):
		"""returns an InputKey for query input to dataField
		"""
		instance = cls(**dataField.dataStore)
		if instance.get_values():
			instance.set_values(instance.get_values().copy())
		instance.set_dbtype(vizierexprs.getVexprFor(instance.get_dbtype()))
		instance.set_source(instance.get_dest())
		instance._setAutoWidget()
		return instance

	@classmethod
	def makeAuto(cls, dataField, queryMeta):
		"""returns an InputKey if dataField is "queriable", None otherwise.
		"""
		if dataField.get_displayHint()=="suppress":
			return
		try:
			hasVexprType = vizierexprs.getVexprFor(dataField.get_dbtype())
		except gavo.Error:
			return
		return cls.fromDataField(dataField)

# XXX TODO: remove the next two methods
"""
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
"""



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

