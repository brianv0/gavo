"""
A Template (see gavo.web.querulator.AbstractTemplate) for wrapping services.
"""

import re
import os

import gavo
from gavo.web import common
from gavo.web.querulator import forms
import runner
import servicedesc


class DataAdaptor:
	"""wraps DataDescriptors for running services described by them.
	"""
	def __init__(self, serviceDesc, serviceName, recordName="default"):
		self.sd = serviceDesc
		self.serviceName = serviceName
		self.computer = self.sd.get_computer()
		self.dd = self.sd.getDataById(self.serviceName)
		self.recordDef = self.dd.get_Semantics(
			).getRecordDefByName(recordName)

	def getRecordDef(self):
		return self.recordDef

	def getItemdefs(self):
		return [{"name": field.get_dest(), 
				"title": field.get_tablehead() or field.get_dest(), 
				"hint": field.get_displayHint().split(",")}
			for field in self.getRecordDef().get_items()]

	def setHandlers(self, data):
		return self.dd.setHandlers(data)

	def get_Grammar(self):
		return self.dd.get_Grammar()


class ServiceAdaptor(DataAdaptor):
	def _makeArguments(self, recordBuilder):
		args = [(int(ct), val) for ct, val in recordBuilder.getDocRec().items()]
		args.sort()
		return [val for ct, val in args if val!=None]

	def _parseContext(self, context):
		"""returns input(s) and command line arguments for the service
		computer as computed from the context.
		"""
		data = runner.DataCollector(self.getRecordDef())
		rb = self.setHandlers(data)
		self.dd.get_Grammar().parse(context)
		args = self._makeArguments(rb)
		return data.fetchall(), args

	def runQuery(self, context):
		"""runs the computer and returns the parsed result.

		The computer receives arguments and inputs from the context.

		The result returned is as if from an dbapi2 table of the structure given
		by the output data descriptor (outputService).

		context is a gavo.web.context instance.
		"""
		inputs, args = self._parseContext(context)
		computer = self.sd.get_computer()
		try:
			if isinstance(computer, basestring):
				return runner.runChild([os.path.join(
					context.getEnv("GAVO_HOME"), computer)]+args, inputs)
			else:
				return computer(args, inputs)
		except Exception, msg:
			import traceback
			traceback.print_exc()
			raise gavo.Error("Service computer %s failed (%s)"%(computer,
				msg))

	def getFormItems(self, context):
		allFields = (self.dd.get_Grammar().get_docKeys()+
			self.dd.get_Grammar().get_rowKeys())
		return "\n".join([field.asHtml(context)
			for field in allFields])

	def asHtml(self, serviceLocation, context):
		"""returns HTML for a from querying this service.
		"""
		return ('<form action="%(serviceLocation)s"'
			' method="get" class="masquerator">%(form)s'
			' %(submitButtons)s</form>'
			)%{
				"serviceLocation": serviceLocation,
				"form": self.getFormItems(context),
				"submitButtons": common.getSubmitButtons(context),
				}


class ServiceTemplate(forms.AbstractTemplate):
	"""is a querulator.Template for responding to service requests.
	"""
	def __init__(self, collection, inputName, outputName):
		self.collection = collection
		self.serviceName = inputName
		self.inputData = ServiceAdaptor(collection.getDescriptor(),
			inputName)
		self.outputData = DataAdaptor(collection.getDescriptor(),
			outputName)
		self._createDelegations()

	def _createDelegations(self):
		"""creates methods to call the parent template to satisfy the template
		interface.
		
		We want to delegate everything we don't have but the parent
		template has to it.  This is a pain, but it's pending a cleanup
		of the querulator to seperate the two roles of the Template class.
		"""
		import sys
		for name in dir(self.collection):
			if not hasattr(self, name):
				ob = getattr(self.collection, name)
				if hasattr(ob, "__call__"):
					def makeMethod(methName):
						return (lambda *args, **kwargs: 
							getattr(self.collection, methName)(*args, **kwargs))
					setattr(self, name, makeMethod(name))
				else:
					setattr(self, name, ob)

	def getItemdefs(self):
		return self.outputData.getItemdefs()

	def getRecordDef(self):
		return self.outputData.getItemdefs()

	def runQuery(self, context):
		rawResult = self.inputData.runQuery(context)
		
		return runner.parseAnswer(rawResult, self.outputData,
			context.hasArgument("verbose"))

	def getDefaultTable(self):
		return "%s.%s"%(self.collection.getDescriptor().get_schema(), 
			self.serviceName)

	def getHiddenForm(self, context):
		return None

	def getProductCol(self):
		return None
	
	def getConditionsAsText(self, context):
# XXX TODO
		return []


class ServiceCollection(forms.AbstractTemplate):
	"""is a collection of services defined through a resource descriptor.

	The context passed at construction time is only used for resolving
	paths -- you can later pass in different ones.

	You can use this as a querulator Template for generating HTML forms.
	For answering queries, you must use the correct service.  (Yes, this
	asymmetry is crap, and we'll have to adapt querulator to this model
	at some point.  This should make the model clearer and allow more than
	one form per page in querulator).
	"""
	servicePat = re.compile(r"<\?service\s+(\w+)\s*\?>")

	def __init__(self, templatePath, context):
		self.path = templatePath
		forms.AbstractTemplate.__init__(self, 
			common.resolvePath(context.getEnv("MASQ_TPL_ROOT"), templatePath))
		self._parseDescriptor(context)
		self.services = {}
	
	def getPath(self):
		return self.path
	
	def _parseDescriptor(self, context):
		self.descriptor = servicedesc.parseServiceDescriptor(
			common.resolvePath(context.getEnv("GAVO_HOME"), 
				self.getMeta("DESCRIPTOR")))

	def _handlePrivateElements(self, src, context):
		"""replaces all <?service?> elements within src with forms for
		querying the services.
		"""
		locationTpl = "%s/masqrun/%s/%%s"%(context.getEnv("ROOT_URL"),
			self.getPath())
		return self.servicePat.sub(lambda mat: 
				self.getServiceAdaptor(mat.group(1)).asHtml(
					locationTpl%mat.group(1), context), 
			src)

	def getDescriptor(self):
		return self.descriptor

	def getServiceAdaptor(self, serviceName):
		"""returns a ServiceAdaptor instance from a service name, or raises a KeyError
		if the not Data section with the id serviceName is in the descriptor.

		XXX TODO: You *could* instanticate output descriptors here, which would
		lead to instanity...
		"""
		if not serviceName in self.services:
			self.services[serviceName] = ServiceAdaptor(self.getDescriptor(), 
				serviceName)
		return self.services[serviceName]
