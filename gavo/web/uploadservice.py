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


class Uploader(resourcebased.GavoFormMixin, resourcebased.DataBasedRenderer):
	"""is a renderer allowing for updates to individual records.
	"""
	def __init__(self, ctx, serviceParts):
		super(Uploader, self).__init__(serviceParts)

	def form_upload(self, ctx, data={}):
		form = formal.Form()
		form.addField('File', formal.File(required=True), formal.FileUploadWidget)
		form.addField('Mode', formal.String(required=True),
    	formal.widgetFactory(formal.RadioChoice, 
				options=[("i", "insert"), ("u", "update")]))
		form.addAction(self.uploadItem)
		self.form = form
		return form

	def writeFile(self, ctx, data):
# XXX TODO: should this be async?
		targetDir = os.path.join(self.rd.get_resdir(), 
			self.dataDesc.get_property("stagingDir"))
		if not targetDir:
			raise gavo.ValidationError("Uploading is only supported for data having"
				" a staging directory.", "File")
		if not os.path.exists(targetDir):
			raise gavo.Error("Staging directory does not exist.")
		targetFName = data["File"][2].split("/")[-1].encode("iso-8859-1")
		if not targetFName:
			raise gavo.ValidationError("Bad file name", "File")
		targetPath = os.path.join(targetDir, targetFName)
		f = open(targetPath, "w")
		f.write(data["File"][1].read())
		f.close()
		return targetPath

	def uploadItem(self, ctx, form, data):
		return defer.maybeDeferred(self.writeFile, ctx, data
			).addCallback(self.parseContent, ctx, data
			).addErrback(self._handleInputError, ctx, common.QueryMeta({}))

	def parseContent(self, sourcePath, ctx, data):
# XXX TODO: sqlsupport is based on dbapi2, and twisted.enterprise doesn't 
# have that.  So, for the moment, we're writing synchronously here.
		try:
			dbConn = sqlsupport.getDbConnection(config.getDbProfileByName("feed"))
			def makeSharedTable(dataSet, recordDef):
				return table.DirectWritingTable(dataSet,recordDef, dbConn, 
					create=False, doUpdates=data["Mode"]=="u")
			r = resource.InternalDataSet(self.dataDesc, tableMaker=makeSharedTable,
				dataSource=sourcePath)
		except sqlsupport.DatabaseError, msg:
			os.unlink(sourcePath)
			raise gavo.ValidationError("Cannot enter in database: %s"%str(msg),
				"File")
		return self.signalSuccess(ctx, str(r.getPrimaryTable().nUpdated))
	
	def signalSuccess(self, ctx, nUpdated):
		return "Data uploaded, %s record(s) changed"%nUpdated

	docFactory = loaders.stan(T.html[
		T.head[
			T.title["Upload to Foo"],
			T.link(render=T.directive("rootlink"), rel="stylesheet", 
				href="/formal.css", type="text/css"),
			T.script(render=T.directive("rootlink"), type='text/javascript', 
				src='/js/formal.js'),
		],
		T.body[
			T.invisible(render=T.directive("form upload"))
		]
	])

