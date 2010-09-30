"""
The form renderer is the standard renderer for web-facing services.

This module also contains a companion renderer that runs feedback queries.
"""


from nevow import inevow
from twisted.internet import defer

from gavo import base
from gavo import svcs
from gavo.imp import formal
from gavo.web import grend
from gavo.web import serviceresults


class Form(grend.FormMixin, 
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
			self.customTemplate = self.service.templates["form"]

		# enable special handling if I'm rendering fixed-behaviour services
		# (i.e., ones that never have inputs) XXX TODO: Figure out where I used this and fix that to use the fixed renderer (or whatever)
		if not self.getInputFields(self.service):
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
		return grend.FormMixin.renderHTTP(self, ctx)

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
		"""is called by formal when input arguments indicate the service should
		run.

		This happens either when the service takes no input data or when
		the sentinel argument of the form is present.

		The method returns a deferred resource.
		"""
		return defer.maybeDeferred(self._realSubmitAction, ctx, form, data
			).addErrback(self._handleInputErrors, ctx)

	def _formatOutput(self, res, ctx):
		self.result = res
		if "response" in self.service.templates:
			self.customTemplate = self.service.templates["response"]
		return grend.ServiceBasedPage.renderHTTP(self, ctx)

	defaultDocFactory = svcs.loadSystemTemplate("defaultresponse.html")

svcs.registerRenderer(Form)


class FeedbackForm(Form):
	"""is a page that renders a form with vexprs filled in of a feedback 
	query.

	Basically, you give items in feedbackSelect arguments which
	are directly parsed into a DataSet's columns.  With these, a
	FeedbackCore is directly called (i.e., not through the service,
	since that would expect very different arguments).

	The FeedbackCore returns a data set that only has a document
	row containing vizier expressions for the ranges of the input
	parameter of the data set given in the feedbackSelect items.

	Only then is the real Form processing started.	I'll admit this
	is a funky renderer.

	This only works on DbBasedCores (and doesn't make sense otherwise).
	"""
	def renderHTTP(self, ctx):
		request = inevow.IRequest(ctx)
		# If no feedbackSelect is present, it's the feedback search or
		# the user has not selected feedback items
		if not "feedbackSelect" in request.args:
			return Form(ctx, self.service)
		# Make a feedback service on the service unless one exists.
		if not hasattr(self.service, "feedbackService"):
			self.service.feedbackService = svcs.FeedbackService.fromService(
				self.service)
		data = request.args
		return self.runServiceWithContext(data, ctx
			).addCallback(self._buildForm, request, ctx)

	def processData(self, rawData, queryMeta):
		inputData = self.service.feedbackService.makeDataFor(self, rawData)
		return self.service.feedbackService.runWithData(inputData, queryMeta)

	def _buildForm(self, feedbackExprs, request, ctx):
		request.args = feedbackExprs.original
		return Form(ctx, self.service)

svcs.registerRenderer(FeedbackForm)
