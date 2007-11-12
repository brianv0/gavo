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
from gavo import sqlsupport
from gavo import table
from gavo.parsing import resource
from gavo.web import common
from gavo.web import resourcebased


def _writeFile(srcFile, fName, dataDesc):
	"""writes the contents of srcFile to fName in dataDesc's staging dir.
	"""
	targetDir = os.path.join(dataDesc.getRD().get_resdir(), 
		dataDesc.get_property("stagingDir"))
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
	return targetPath


def _importData(sourcePath, mode, dataDesc):
	try:
		dbConn = sqlsupport.getDbConnection(config.getDbProfileByName("feed"))
		def makeSharedTable(dataSet, recordDef):
			return table.DirectWritingTable(dataSet,recordDef, dbConn, 
				create=False, doUpdates=mode=="u")
		r = resource.InternalDataSet(dataDesc, tableMaker=makeSharedTable,
			dataSource=sourcePath)
	except sqlsupport.DatabaseError, msg:
		raise gavo.ValidationError("Cannot enter %s in database: %s"%
			(os.path.basename(sourcePath), str(msg)), "File")
	return r.getPrimaryTable().nUpdated


def saveData(srcFile, fName, mode, dataDesc):
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
	targetPath = _writeFile(srcFile, fName, dataDesc)
	try:
		nUpdated = _importData(targetPath, mode, dataDesc)
	except:
		os.unlink(targetPath)
		raise
	return nUpdated

	
class Uploader(resourcebased.GavoFormMixin, resourcebased.DataBasedRenderer):
	"""is a renderer allowing for updates to individual records.
	"""
	def __init__(self, ctx, serviceParts):
		self.uploadInfo = {}
		super(Uploader, self).__init__(serviceParts)

	def form_upload(self, ctx, data={}):
		form = formal.Form()
		form.addField('File', formal.File(required=True))
		form.addField('Mode', formal.String(required=True),
    	formal.widgetFactory(formal.RadioChoice, 
				options=[("i", "insert"), ("u", "update")]))
		form.addAction(self.uploadItem)
		self.form = form
		return form

	def uploadItem(self, ctx, form, data):
		self.uploadInfo = {}
		fName, srcFile = data["File"]
		mode = data["Mode"]
		return defer.maybeDeferred(saveData, srcFile, fName, mode, self.dataDesc
			).addCallback(self.contentParsed, ctx, data
			).addErrback(self._handleInputErrors, ctx)

	def contentParsed(self, nUpdated, ctx, data):
		self.uploadInfo["nUpdated"] = nUpdated
		# ignore POSTed stuff to avoid infinite recusion
		inevow.IRequest(ctx).method = "GET"  
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
			T.title["Upload to Foo"],
			T.link(render=T.directive("rootlink"), rel="stylesheet", 
				href="/formal.css", type="text/css"),
			T.script(render=T.directive("rootlink"), type='text/javascript', 
				src='/js/formal.js'),
		],
		T.body[
			T.p(class_="procMessage", render=T.directive("uploadInfo"))[
				T.slot(name="nUpdated"),
				" record(s) modified."
			],
			T.invisible(render=T.directive("form upload"))
		]
	])


class MachineUploader(common.CustomErrorMixin, Uploader):
	"""is a renderer allowing for updates to individual records.

	The difference to Uploader is that no form-redisplay will be done.
	All errors are reported through HTTP response codes and text strings.
	"""
	_generateForm = Uploader.form_upload

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

	def _getInputData(self, data):
		return data
	
	def _handleInputData(self, data, ctx):
		return Uploader.uploadItem(self, ctx, self.form, data)

	def contentParsed(self, nUpdated, ctx, data):
		return str("%s uploaded, %d records modified\n"%(
			data["File"][0], nUpdated))
