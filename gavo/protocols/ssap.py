"""
The SSAP core and supporting code.

"""

from cStringIO import StringIO

from gavo import base
from gavo import rsc
from gavo import svcs
from gavo import votable
from gavo.formats import votablewrite
from gavo.svcs import outputdef
from gavo.votable import V


RD_ID = "//ssap"

def getRD():
	return base.caches.getRD(RD_ID)



class SSAPCore(svcs.DBCore):
	"""A core doing SSAP queries.

	This core knows about metadata queries, version negotiation, and 
	dispatches on REQUEST.  Thus, it may return formatted XML data
	under certain circumstances.
	"""
	name_ = "ssapCore"

	outputTableXML = """
		<outputTable verbLevel="30">
			<FEED source="//ssap#coreOutputAdditionals"/>
		</outputTable>"""

	def _makeMetadata(self, service):
		inputTable = self.inputTable
		inParams =[votablewrite.makeFieldFromColumn(V.PARAM, param)
			for param in inputTable.params]
		for p in inParams:
			p.name = "INPUT:"+p.name

		emptyTable = rsc.TableForDef(self.outputTable)
		ctx = votablewrite.VOTableContext()

		vot = V.VOTABLE[
			V.RESOURCE(type="meta")[
				V.DESCRIPTION[
					base.getMetaText(service, "description")],
				V.INFO(name="QUERY_STATUS", value="OK"), [
					inParams,
					votablewrite.makeTable(ctx, emptyTable)
		]]]

		res =  StringIO()
		votable.write(vot, res)
		return "application/x-votable+xml", res.getvalue()

	def run(self, service, inputTable, queryMeta):
		if inputTable.getParam("REQUEST")!="queryData":
			raise base.ValidationError("Only queryData operation supported so"
				" far for SSAP.", "REQUEST")
		if inputTable.getParam("FORMAT")=="METADATA":
			return self._makeMetadata(service)

		limits = [q for q in 
				(inputTable.getParam("MAXREC"), inputTable.getParam("TOP"))
			if q]
		if not limits:
			limits = [base.getConfig("ivoa", "dalDefaultLimit")]
		limit = min(min(limits), base.getConfig("ivoa", "dalHardLimit"))
		queryMeta["dbLimit"] = limit

		res = svcs.DBCore.run(self, service, inputTable, queryMeta)
		if len(res)==limit:
			res.addMeta("info", base.makeMetaValue(type="info", 
				value="Exactly %s rows were returned.  This means"
				" your query probably reached the match limit.  Increase MAXREC."%limit,
				infoName="QUERY_STATUS", infoValue="OVERFLOW"))

		# add shitty namespace for utypes.  sigh.
		res.addMeta("_votableRootAttributes",
			'xmlns:ssa="http://www.ivoa.net/xml/DalSsap/v1.0"')

		res.addMeta("info", base.makeMetaValue("SSAP",
			type="info",
			infoName="SERVICE_PROTOCOL", infoValue="1.04"))
		return res
