"""
Code to help TAP.
"""

from gavo import base
from gavo import rsc


RD_ID = "__system__/tap"


def publishToTAP(rd, connection):
	"""publishes info for all ADQL-enabled tables of rd to the TAP_SCHEMA.
	"""
	# first check if we have any adql tables at all, and don't attempt
	# anything if we don't (this is cheap optimizing and keeps TAP_SCHEMA
	# from being created on systems that don't do ADQL.
	for table in rd.tables:
		if table.adql:
			break
	else:
		return
	tapRD = base.caches.getRD(RD_ID)
	for ddId in ["importTablesFromRD", "importColumnsFromRD", 
			"importFkeysFromRD"]:
		dd = tapRD.getById(ddId)
		rsc.makeData(dd, forceSource=rd, parseOptions=rsc.parseValidating,
			connection=connection)


def unpublishFromTAP(rd, connection):
	"""removes all information originating from rd from TAP_SCHEMA.
	"""
	rd.setProperty("moribund", "True") # the embedded grammars take this
	                                   # to mean "kill this"
	publishToTAP(rd, connection)


if __name__=="__main__":
	from gavo import api
	api.setDBProfile("admin")
	rd = api.getRD("lightmeter/q")
	publishToTAP(rd)
