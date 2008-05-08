"""
A service to upload sources into databases.
"""

import os

import formal

from nevow import appserver
from nevow import inevow
from nevow import loaders
from nevow import util as nevowutil
from nevow import tags as T, entities as E

from twisted.internet import defer

import gavo
from gavo import config
from gavo import datadef
from gavo import record
from gavo import sqlsupport
from gavo import table
from gavo.parsing import resource
from gavo.parsing import contextgrammar
from gavo.parsing import nullgrammar
from gavo.web import common
from gavo.web import core
from gavo.web import standardcores
from gavo.web import resourcebased


class UploadCore(standardcores.QueryingCore):
	"""is a core handling uploads of data to the database.

	It uses the standard parsing architecture to do that.
	"""
	def __init__(self, rd, initvals):
		super(UploadCore, self).__init__(rd, initvals=initvals, additionalFields={
			"dataName": record.RequiredField})
		self.addto_condDescs(
			standardcores.CondDesc.fromInputKey(
				contextgrammar.InputKey(dest="File", formalType=formal.File,
					source="File", dbtype="file", optional=False)))
		self.addto_condDescs(
			standardcores.CondDesc.fromInputKey(
				contextgrammar.InputKey(dest="Mode", formalType=formal.String,
					source="Mode", dbtype="text", optional=False,
					values=datadef.Values(options=['i', 'u']),
					widgetFactory=formal.widgetFactory(formal.RadioChoice, 
						options=[("i", "insert"), ("u", "update")]))))

	def set_dataName(self, dataName):
		self.dataStore["dataName"] = dataName
		self.dataDesc = self.rd.getDataById(dataName)

	def _fixPermissions(self, fName):
		"""tries to chmod the newly created file to 0664 and change the group
		to config.gavoGroup.
		"""
		os.chmod(fName, 0664)
		os.chown(fName, -1, grp.getgrnam(config.get("gavoGroup")))

	def _writeFile(self, srcFile, fName):
		"""writes the contents of srcFile to fName in dataDesc's staging dir.
		"""
		targetDir = os.path.join(self.rd.get_resdir(), 
			self.dataDesc.get_property("stagingDir"))
		if not targetDir:
			raise gavo.ValidationError("Uploading is only supported for data having"
				" a staging directory.", "File")
		if not os.path.exists(targetDir):
			raise gavo.Error("Staging directory does not exist.")
		targetFName = fName.split("/")[-1].encode("iso-8859-1")
		if not targetFName:
			raise gavo.ValidationError("Bad file name", "File")
		targetPath = os.path.join(targetDir, targetFName)
		f = open(targetPath, "w")
		f.write(srcFile.read())
		f.close()
		try:
			self._fixPermissions(targetPath)
		except os.error:
			# Nothing we can do, and it may not even hurt
			pass
		return targetPath

	def _importData(self, sourcePath, mode):
		"""parses the input file at sourcePath and writes the result to the DB.
		"""
		try: # XXX TODO: just in case: make that async (resourcecache.getDBC...)
			dbConn = sqlsupport.getDbConnection(config.getDbProfileByName("feed"))
			def makeSharedTable(dataSet, recordDef):
				return table.DirectWritingTable(dataSet, recordDef, dbConn, 
					create=False, doUpdates=mode=="u", dropIndices=False)
			r = resource.InternalDataSet(self.dataDesc, tableMaker=makeSharedTable,
				dataSource=sourcePath)
		except sqlsupport.DatabaseError, msg:
			raise gavo.ValidationError("Cannot enter %s in database: %s"%
				(os.path.basename(sourcePath), str(msg)), "File")
		resDD = datadef.DataTransformer(self.rd, initvals={
			"Grammar": nullgrammar.NullGrammar(),
			"Semantics": resource.Semantics(),
			"items": [
				datadef.DataField(name="nUpdated", dbtype="integer")]})
		resData = resource.InternalDataSet(resDD)
		resData.getDocRec()["nUpdated"] = r.getPrimaryTable().nUpdated
		return resData

	def saveData(self, srcFile, fName, mode):
		"""saves data read from srcFile to both fNames staging dir and to the
		database table(s) described by dataDesc.

		mode can be "u" (for update) or "i" for insert.

		If parsing or the database operations fail, the saved file will be removed.
		Errors will ususally be gavo.ValidationErrors on either File or Mode.

		The function returns the number of items modified.  However, you should
		always use this with maybeDeferred since I'm quite sure we'll make this
		async at some point.
		"""
# XXX TODO: this should be done asynchronously, but currently is not
		targetPath = self._writeFile(srcFile, fName)
		try:
			nUpdated = self._importData(targetPath, mode)
		except:
			os.unlink(targetPath)
			raise
		return nUpdated

	def run(self, inputData, queryMeta):
# Do we want to interpret the primary table here as well?
		data = inputData.getDocRec()
		fName, srcFile = data["File"]
		mode = data["Mode"]
		return defer.maybeDeferred(self.saveData, srcFile, fName, mode)


core.registerCore("upload", UploadCore)

	
class Uploader(resourcebased.Form):
	"""is a renderer allowing for updates to individual records.
	"""

	name = "upload"

	def __init__(self, ctx, service):
		self.uploadInfo = {}
		super(Uploader, self).__init__(ctx, service)

	def _runService(self, inputData, queryMeta, ctx):
		return defer.maybeDeferred(self.service.run, inputData, queryMeta
			).addCallback(self._processOutput, inputData, queryMeta, ctx
			).addErrback(self._handleInputErrors, ctx)

	def _processOutput(self, outputData, inputData, queryMeta, ctx):
		self.uploadInfo["nUpdated"] = outputData.getDocRec()["nUpdated"]
		# remove form identification to prevent infinite recursion
		del inevow.IRequest(ctx).args["__nevow_form__"]
		del inevow.IRequest(ctx).args["Mode"]
		inevow.IRequest(ctx).args = {}
		return self

	def render_uploadInfo(self, ctx, data):
		if not self.uploadInfo:
			return T.invisible()
		else:
			for key, val in self.uploadInfo.iteritems():
				ctx.tag.fillSlots(key, str(val))
			return ctx.tag

	docFactory = loaders.stan(T.html[
		T.head[
			T.title["Upload"],
			T.invisible(render=T.directive("commonhead")),
		],
		T.body[
			T.p(class_="procMessage", render=T.directive("uploadInfo"))[
				T.slot(name="nUpdated"),
				" record(s) modified."
			],
			T.invisible(render=T.directive("form genForm"))
		]
	])


class MachineUploader(common.CustomErrorMixin, Uploader):
	"""is a renderer allowing for updates to individual records.

	The difference to Uploader is that no form-redisplay will be done.
	All errors are reported through HTTP response codes and text strings.
	"""

	name = "mupload"

	_generateForm = Uploader.form_genForm

	def renderHTTP_exception(self, ctx, failure):
		failure.printTraceback()
		request = inevow.IRequest(ctx)
		request.setResponseCode(500)
		request.setHeader("content-type", "text/plain")
		request.write(failure.getErrorMessage())
		request.finishRequest(False)
		return appserver.errorMarker
	
	def _handleInputErrors(self, errors, ctx):
		request = inevow.IRequest(ctx)
		request.setResponseCode(400)
		request.setHeader("content-type", "text/plain")
		msg = super(MachineUploader, self)._handleInputErrors(errors, ctx)
		request.write(msg)
		request.finishRequest(False)
		return appserver.errorMarker

	def _getInputData(self, formData):
		return self.service.getInputData(formData)
	
	def _handleInputData(self, inputData, ctx):
		queryMeta = common.QueryMeta(ctx)
		queryMeta["formal_data"] = self.form.data
		return self._runService(inputData, queryMeta, ctx)

	def _processOutput(self, outputData, inputData, queryMeta, ctx):
		return str("%s uploaded, %d records modified\n"%(
			inputData.getDocRec()["File"][0], 
			outputData.getDocRec()["nUpdated"]))
