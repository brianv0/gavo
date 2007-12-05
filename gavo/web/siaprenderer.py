"""
A real, standards-compliant siap service.

We don't want a standard resource-based service here since the entire error
handling is completely different.
"""

from nevow import inevow

from twisted.internet import defer
from twisted.python import failure

from zope.interface import implements

import gavo
from gavo import datadef
from gavo import votable
from gavo.parsing import contextgrammar
from gavo.parsing import meta
from gavo.parsing import resource
from gavo.web import common
from gavo.web import resourcebased
from gavo.web import vodal


class SiapRenderer(vodal.DalRenderer):
	implements(inevow.ICanHandleException)

	name="siap.xml"

	def renderHTTP(self, ctx):
		args = inevow.IRequest(ctx).args
		if args.get("FORMAT")==["METADATA"]:
			return self._serveMetadata(ctx)
		return super(SiapRenderer, self).renderHTTP(ctx)

	def _serveMetadata(self, ctx):
		request = inevow.IRequest(ctx)
		request.setHeader("content-type", "application/x-votable")
		inputFields = [contextgrammar.InputKey(**f.dataStore) 
			for f in self.service.getInputFields()]
		for f in inputFields:
			f.set_dest("INPUT:"+f.get_dest())
		dataDesc = resource.makeSimpleDataDesc(self.rd, 
			self.service.getOutputFields(common.QueryMeta(ctx)))
		dataDesc.set_items(inputFields)
		data = resource.InternalDataSet(dataDesc)
		data.addMeta(name="_type", content="metadata")
		data.addMeta(name="_query_status", content="OK")
		result = common.CoreResult(data, {}, common.QueryMeta(ctx))
		return resourcebased.writeVOTable(request, result, votable.VOTableMaker())

	def _handleOutputData(self, data, ctx):
		data.addMeta(name="_query_status", content=meta.InfoItem("OK", ""))
		data.addMeta(name="_type", content="result")
		data.addMeta(name="_query_status", content="OK")
		return super(SiapRenderer, self)._handleOutputData(data, ctx)
	
	def _makeErrorTable(self, ctx, msg):
		dataDesc = resource.makeSimpleDataDesc(self.rd, [])
		data = resource.InternalDataSet(dataDesc)
		data.addMeta(name="_query_status", content=meta.InfoItem(
			"ERROR", str(msg)))
		return common.CoreResult(data, {}, common.QueryMeta(ctx))

