"""
The SSAP core and supporting code.

"""

from gavo import svcs


class SSAPCore(svcs.DBCore):
	"""A core doing SSAP queries.

	This core knows about metadata queries, version negotiation, and 
	dispatches on REQUEST.  Thus, it may return formatted XML data
	under certain circumstances.
	"""
	name_ = "ssapCore"

	def run(self, service, inputData, queryMeta):
		pars = inputData.getPrimaryTable().rows[0]
		if pars.get("REQUEST", "queryData")!="queryData":
			raise base.ProtocolError("Only queryData operation supported so"
				" far for SSAP.")
		return "text/plain", "the deuce"
