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


class InputKey(datadef.DataField):
	"""is a key for a ContextGrammar.
	"""
	additionalFields = {
		"formalType":    None, # nevow formal type to use.
		"widgetFactory": None, # Python code to generate a formal widget factory
		                       # for this field.
		"showitems": 3,        # #items to show in multi selections
		"value": None,         # value in a constant field (rendered hidden)
		"scaling": None,       # multiply incoming value by this (will be clobbered
		                       # if you set inputUnit)
		"inputUnit": None,     # unit the user is supposed to use
	}
	
	def set_formalType(self, formalType):
		"""sets the nevow formal type for the input field.

		The argument can either be a string, in which case it is interpreted
		as an *SQL* type and translated to the corresponding formal type,
		or a formal type.
		"""
		if isinstance(formalType, basestring):
			defaultType, defaultWidget = typesystems.sqltypeToFormal(
				formalType)
			if not self.dataStore["formalType"]:
				self.dataStore["formalType"] = defaultType
			if not self.dataStore["widgetFactory"]:
				self.set_widgetFactory(defaultWidget)
		else:
			self.dataStore["formalType"] = formalType

	def get_formalType(self):
		if self.dataStore.get("formalType"):
			return self.dataStore["formalType"](
				required=not self.get_optional())
		if self.isEnumerated():
			formalType = typesystems.sqltypeToFormal(self.get_dbtype())[0]
		else:
			formalType = formal.String
		return formalType(required=not self.get_optional())

	def set_scaling(self, val):
		if val==None:
			self.dataStore["scaling"] = None
		else:
			self.dataStore["scaling"] = float(val)

	def set_inputUnit(self, val):
		if val==None:
			self.dataStore["inputUnit"] = None
			self.set_scaling(None)
		else:
			self.dataStore["inputUnit"] = val
			self.set_scaling(unitconv.getFactor(val, self.get_unit()))

	def set_widgetFactory(self, widgetFactory):
		"""sets the widget factory either from source code or from a formal
		WidgetFactory object.
		"""
		if isinstance(widgetFactory, basestring):
			self.dataStore["widgetFactory"] = gwidgets.makeWidgetFactory(
				widgetFactory)
		else:
			self.dataStore["widgetFactory"] = widgetFactory

	def get_widgetFactory(self):
		"""returns a widget factory appropriate for dbtype and values.
		"""
# XXX TODO: handle booleans
		if self.dataStore.get("widgetFactory"):
			res = self.dataStore["widgetFactory"]
		elif self.get_value():
			return formal.Hidden
		elif self.isEnumerated():
			if self.get_values().get_multiOk():
				res = formal.widgetFactory(
					gwidgets.SimpleMultiSelectChoice,
					[str(i) for i in self.get_values().get_options()],
					self.get_showitems())
			else:
				items = self.get_values().get_options()
# XXX TODO sanitize the whole default/none option mess.
#				try:
#					items.remove(self.get_values().get_default())
#				except ValueError:
#					pass
				noneLabel = None
				if self.get_optional():
					noneLabel = "ANY"
				res = formal.widgetFactory(
					gwidgets.SimpleSelectChoice,
					[str(i) for i in items], self.get_default())
		else:
			_, res = typesystems.sqltypeToFormal(self.get_dbtype())
		return res

	def getValueIn(self, *args, **kwargs):
		if self.get_value()!=None:
			return self.get_value()
		return super(InputKey, self).getValueIn(*args, **kwargs)

	@classmethod
	def fromDataField(cls, dataField, attrs={}):
		"""returns an InputKey for query input to dataField
		"""
		instance = super(InputKey, cls).fromDataField(dataField)
		instance.set_dbtype(vizierexprs.getVexprFor(instance.get_dbtype()))
		instance.set_source(instance.get_dest())
		instance.set_optional(True)
		for key, val in attrs.iteritems():
			instance.set(key, val)
		return instance

	@classmethod
	def makeAuto(cls, dataField, queryMeta={}):
		"""returns an InputKey if dataField is "queriable", None otherwise.
		"""
		if dataField.get_displayHint().get("type")=="suppress":
			return
		try:
			hasVexprType = vizierexprs.getVexprFor(dataField.get_dbtype())
		except gavo.Error:
			return
		return cls.fromDataField(dataField)


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

