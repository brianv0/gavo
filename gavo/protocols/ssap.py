"""
The SSAP core and supporting code.

"""

from gavo import base
from gavo import svcs


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

	def __init__(self, parent, **kwargs):
		svcs.DBCore.__init__(self, parent, **kwargs)
		rd = getRD()
		self.feedFrom(rd.getById("ssa_prototype"))
	
	def run(self, service, inputTable, queryMeta):
		if inputTable.getParam("REQUEST")!="queryData":
			raise base.ValidationError("Only queryData operation supported so"
				" far for SSAP.", "REQUEST")
		limits = [q for q in 
				(inputTable.getParam("MAXREC"), inputTable.getParam("TOP"))
			if q]
		if not limits:
			limits = [base.getConfig("ivoa", "dalDefaultLimit")]
		limit = min(min(limits), base.getConfig("ivoa", "dalHardLimit"))
		queryMeta["dbLimit"] = limit
		return svcs.DBCore.run(self, service, inputTable, queryMeta)
