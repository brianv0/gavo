"""
The form renderer is the standard renderer for web-facing services.
"""


from nevow import inevow
from nevow import tags as T, entities as E
from twisted.internet import defer

from gavo import base
from gavo import svcs
from gavo.base import typesystems
from gavo.imp import formal
from gavo.svcs import customwidgets
from gavo.web import grend
from gavo.web import serviceresults


class ToFormalConverter(typesystems.FromSQLConverter):
	"""is a converter from SQL types to Formal type specifications.

	The result of the conversion is a tuple of formal type and widget factory.
	"""
	typeSystem = "Formal"
	simpleMap = {
		"smallint": (formal.Integer, formal.TextInput),
		"integer": (formal.Integer, formal.TextInput),
		"int": (formal.Integer, formal.TextInput),
		"bigint": (formal.Integer, formal.TextInput),
		"real": (formal.Float, formal.TextInput),
		"float": (formal.Float, formal.TextInput),
		"boolean": (formal.Boolean, formal.Checkbox),
		"double precision": (formal.Float, formal.TextInput),
		"double": (formal.Float, formal.TextInput),
		"text": (formal.String, formal.TextInput),
		"char": (formal.String, formal.TextInput),
		"date": (formal.Date, formal.widgetFactory(formal.DatePartsInput,
			twoCharCutoffYear=50, dayFirst=True)),
		"time": (formal.Time, formal.TextInput),
		"timestamp": (formal.Date, formal.widgetFactory(formal.DatePartsInput,
			twoCharCutoffYear=50, dayFirst=True)),
		"vexpr-float": (formal.String, customwidgets.NumericExpressionField),
		"vexpr-date": (formal.String, customwidgets.DateExpressionField),
		"vexpr-string": (formal.String, customwidgets.StringExpressionField),
		"pql-string": (formal.String, formal.TextInput),
		"pql-int": (formal.String, formal.TextInput),
		"pql-float": (formal.String, formal.TextInput),
		"pql-date": (formal.String, formal.TextInput),
		"file": (formal.File, None),
		"raw": (formal.String, formal.TextInput),
	}

	def mapComplex(self, type, length):
		if type in self._charTypes:
			return formal.String, formal.TextInput

sqltypeToFormal = ToFormalConverter().convert


def _getFormalType(inputKey):
	return sqltypeToFormal(inputKey.type)[0](required=inputKey.required)


def _getWidgetFactory(inputKey):
	if not hasattr(inputKey, "_widgetFactoryCache"):
		widgetFactory = inputKey.widgetFactory
		if widgetFactory is None:
			if inputKey.isEnumerated():
				widgetFactory = customwidgets.EnumeratedWidget(inputKey)
			else:
				widgetFactory = sqltypeToFormal(inputKey.type)[1]
		if isinstance(widgetFactory, basestring):
			widgetFactory = customwidgets.makeWidgetFactory(widgetFactory)
		inputKey._widgetFactoryCache = widgetFactory
	return inputKey._widgetFactoryCache


def getFieldArgsForInputKey(inputKey):
	# infer whether to show a unit and if so, which
	unit = ""
	if inputKey.type!="date":  # Sigh.
		unit = inputKey.inputUnit or inputKey.unit or ""
		if unit:
			unit = " [%s]"%unit
	label = inputKey.tablehead

	return {
		"label": label,
		"name": inputKey.name,
		"type": _getFormalType(inputKey),
		"widgetFactory": _getWidgetFactory(inputKey),
		"label": label+unit,
		"description": inputKey.description}


########### XXX REMOVE NONWORKING CODE START

'''
class MultiField(formal.Group):
	"""A "widget" containing multiple InputKeys (i.e., formal Fields) in
	a single line.
	"""


class MultiFieldFragment(rend.Fragment):
	"""A fragment for rendering MultiFields.
	"""
	docFactory = loaders.stan(
		T.div(class_="multifield", render=T.directive("multifield"))[
			T.label(for_=T.slot('id'))[T.slot('label')],
			T.div(class_='description')[T.slot('description')]])

	def __init__(self, multiField):
		rend.Fragment.__init__(self)
		self.multiField = multiField

	def render_multifield(self, ctx, data):
		ctx.tag.fillSlots('description', self.multiField.description)
		ctx.tag.fillSlots('label', self.multiField.label)
'''
########### XXX REMOVE NONWORKING CODE END


class FormMixin(formal.ResourceMixin):
	"""A mixin to produce input forms for services and display
	errors within these forms.
	"""
	parameterStyle = "form"

	def _handleInputErrors(self, failure, ctx):
		"""goes as an errback to form handling code to allow correction form
		rendering at later stages than validation.
		"""
		if isinstance(failure.value, formal.FormError):
			self.form.errors.add(failure.value)
		elif isinstance(failure.value, base.ValidationError) and isinstance(
				failure.value.colName, basestring):
			try:
				# Find out the formal name of the failing field...
				failedField = failure.value.colName
				# ...and make sure it exists
				self.form.items.getItemByName(failedField)
				self.form.errors.add(formal.FieldValidationError(
					str(failure.getErrorMessage()), failedField))
			except KeyError: # Failing field cannot be determined
				self.form.errors.add(formal.FormError("Problem with input"
					" in the internal or generated field '%s': %s"%(
						failure.value.colName, failure.getErrorMessage())))
		else:
			failure.printTraceback()
			return failure
		return self.form.errors

	def _addDefaults(self, ctx, form):
		"""adds defaults from request arguments.
		"""
		if ctx is None:  # no request context, no arguments
			return
		args = inevow.IRequest(ctx).args
		for item in form.items:
			try:
				form.data[item.key] = item.makeWidget().processInput(
					ctx, item.key, args)
			except:  # don't fail on junky things in default arguments
				pass
			
	def _addInputKey(self, form, container, inputKey):
		"""adds a form field for an inputKey to the form.
		"""
		container.addField(**getFieldArgsForInputKey(inputKey))
		if inputKey.values and inputKey.values.default:
			form.data[inputKey.name] = inputKey.values.default
		if inputKey.value:
			form.data[inputKey.name] = inputKey.value

	def _groupQueryFields(self, inputTable):
		"""returns a list of "grouped" param names from inputTable.

		The idea here is that you can define "groups" in your input table.
		Each such group can contain paramrefs.  When the input table is rendered
		in HTML, the grouped fields are created in a formal group.  To make this
		happen, they may need to be resorted.  This happens in this function.

		The returned list contains strings (parameter names), groups (meaning
		"start a new group") and None (meaning end the current group).

		This is understood and used by _addQueryFields.
		"""
		groupedKeys = {}
		for group in inputTable.groups:
			for name in group.paramRefs:
				groupedKeys[name] = group

		inputKeySequence, addedNames = [], set()
		for inputKey in inputTable.params:
			thisName = inputKey.name

			if thisName in addedNames:
				# part of a group and added as such
				continue

			newGroup = groupedKeys.get(thisName)
			if newGroup is None:
				# not part of a group
				inputKeySequence.append(thisName)
				addedNames.add(thisName)
			else:
				# current key is part of a group: add it and all others in the group
				# enclosed in group/None.
				inputKeySequence.append(newGroup)
				for groupedName in groupedKeys[inputKey.name].paramRefs:
					inputKeySequence.append(groupedName)
					addedNames.add(groupedName)
				inputKeySequence.append(None)
		return inputKeySequence

	def _addQueryFieldsForInputTable(self, form, inputTable):
		"""generates input fields form the parameters of inputTable, taking
		into account grouping if necessary.
		"""
		containers = [form]
		for item in self._groupQueryFields(inputTable):
			if item is None:  # end of group
				containers.pop()
			elif isinstance(item, basestring):  # param reference
				self._addInputKey(form, containers[-1], 
					inputTable.params.getColumnByName(item))
			else: # it's a new group
				containers.append(
					form.addGroup(item.name, description=item.description,
						label=item.getProperty("label", None),
						cssClass=item.getProperty("cssClass", None)))

	def _addQueryFields(self, form):
		"""adds the inputFields of the service to form, setting proper defaults
		from the field or from data.
		"""
		if self.service.inputDD:
			# the service has a custom inputDD; all we have is the input keys.
			for item in self.service.getInputKeysFor(self):
				self._addInputKey(form, form, item)
		else:
			# we have an inputTable.  Handle groups and other fancy stuff
			self._addQueryFieldsForInputTable(form,
				self.service.getCoreFor(self).inputTable)

	def _addMetaFields(self, form, queryMeta):
		"""adds fields to choose output properties to form.
		"""
		for serviceKey in self.service.serviceKeys:
			self._addInputKey(form, form, serviceKey)
		try:
			if self.service.core.wantsTableWidget():
				form.addField("_DBOPTIONS", svcs.FormalDict,
					formal.widgetFactory(svcs.DBOptions, self.service, queryMeta),
					label="Table")
		except AttributeError: # probably no wantsTableWidget method on core
			pass

	def _getFormLinks(self):
		"""returns stan for widgets building GET-type strings for the current 
		form content.
		"""
		return T.div(class_="formLinks")[
				T.a(href="", class_="resultlink", onmouseover=
						"this.href=makeResultLink(getEnclosingForm(this))")
					["[Result link]"],
				" ",
				T.a(href="", class_="resultlink", onmouseover=
						"this.href=makeBookmarkLink(getEnclosingForm(this))")[
					T.img(src=base.makeSitePath("/static/img/bookmark.png"), 
						class_="silentlink", title="Link to this form", alt="[bookmark]")
				],
			]

	def form_genForm(self, ctx=None, data=None):
		queryMeta = svcs.QueryMeta.fromContext(ctx)
		form = formal.Form()
		self._addQueryFields(form)
		self._addMetaFields(form, queryMeta)
		self._addDefaults(ctx, form)
		if self.name=="form":
			form.addField("_OUTPUT", formal.String, 
				formal.widgetFactory(serviceresults.OutputFormat, 
				self.service, queryMeta),
				label="Output format")
		form.addAction(self.submitAction, label="Go")
		form.actionMaterial = self._getFormLinks()
		self.form = form
		return form


class Form(FormMixin, 
		grend.CustomTemplateMixin,
		grend.HTMLResultRenderMixin, 
		grend.ServiceBasedPage):
	"""The "normal" renderer within DaCHS for web-facing services.

	It will display a form and allow outputs in various formats.

	It also does error reporting as long as that is possible within
	the form.
	"""
	name = "form"
	runOnEmptyInputs = False
	compute = True

	def __init__(self, ctx, service):
		grend.ServiceBasedPage.__init__(self, ctx, service)
		if "form" in self.service.templates:
			self.customTemplate = self.service.getTemplate("form")

		# enable special handling if I'm rendering fixed-behaviour services
		# (i.e., ones that never have inputs) XXX TODO: Figure out where I used this and fix that to use the fixed renderer (or whatever)
		if not self.service.getInputKeysFor(self):
			self.runOnEmptyInputs = True
		self.queryResult = None

	@classmethod
	def isBrowseable(self, service):
		return True

	@classmethod
	def isCacheable(self, segments, request):
		return segments==()

	def renderHTTP(self, ctx):
		if self.runOnEmptyInputs:
			inevow.IRequest(ctx).args[formal.FORMS_KEY] = ["genForm"]
		return FormMixin.renderHTTP(self, ctx)

	def _realSubmitAction(self, ctx, form, data):
		"""is a helper for submitAction that does the real work.

		It is here so we can add an error handler in submitAction.
		"""
		queryMeta = svcs.QueryMeta.fromContext(ctx)
		queryMeta["formal_data"] = data
		if (self.service.core.outputTable.columns and 
				not self.service.getCurOutputFields(queryMeta)):
			raise base.ValidationError("These output settings yield no"
				" output fields", "_OUTPUT")
		if queryMeta["format"]=="HTML":
			resultWriter = self
		else:
			resultWriter = serviceresults.getFormat(queryMeta["format"])
		if resultWriter.compute:
			d = self.runService(data, queryMeta)
		else:
			d = defer.succeed(None)
		return d.addCallback(resultWriter._formatOutput, ctx)

	def submitAction(self, ctx, form, data):
		"""executes the service.

		This is a callback for the formal form.
		"""
		return defer.maybeDeferred(self._realSubmitAction, ctx, form, data
			).addErrback(self._handleInputErrors, ctx)

	def _formatOutput(self, res, ctx):
		self.result = res
		if "response" in self.service.templates:
			self.customTemplate = self.service.getTemplate("response")
		return grend.ServiceBasedPage.renderHTTP(self, ctx)

	defaultDocFactory = svcs.loadSystemTemplate("defaultresponse.html")
