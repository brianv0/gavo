"""
"Publishing" service records -- grammar-type stuff and UI.

This module basically turns "publishable things" -- services, resource
records, data items -- into row dictionaries that can be entered into
the database.

This is one half of getting them into the registry.  The other half is
done in identifiers and builders; these take the stuff from the database,
rebuilds actual objects and creates registry records from them.  So,
the content of the service table is not actually used to build resource
records.
"""

import datetime
import itertools
import os
import sys
import time
import traceback
import warnings

import pkg_resources

from gavo import base
from gavo import grammars
from gavo import rsc
from gavo import utils

from gavo.registry import builders
from gavo.registry import identifiers
from gavo.registry import nonservice
from gavo.registry.common import *


def makeBaseRecord(res):
	"""returns a dictionary giving the metadata common to resource records.
	"""
	# bomb out if critical metadata is missing
	base.validateStructure(res)
	# bomb out if, for some reason, we can't come up with a resource record
	# for this guy
	ignored = builders.getVOResourceElement(res)

	rec = {}
	rec["ivoid"] = base.getMetaText(res, "identifier")
	rec["shortName"] = base.getMetaText(res, "shortName")
	rec["sourceRD"] = res.rd.sourceId
	rec["resId"] = res.id
	rec["title"] = base.getMetaText(res, "title", propagate=True)
	rec["deleted"] = False
	rec["recTimestamp"] = datetime.datetime.utcnow()
	rec["description"] = base.getMetaText(res, "description")
	dateUpdated = res.getMeta("datetimeUpdated")
	if dateUpdated is None:
		rec["dateUpdated"] = datetime.datetime.utcnow()
	else:
		rec["dateUpdated"] = str(dateUpdated)
	return rec


def iterSvcRecs(service):
	"""iterates over records suitable for importing into the service list 
	for service.

	It will yield record(s) for each "publication" (i.e., renderer) and
	for each set therein.  It will then, together with the last publication,
	records for all given subjects are yielded.

	With the forceUnique hacks on the records defined in 
	services.rd#servicetables, this fills every table as desired.  However,
	the whole thing clearly shows we want something more fancy when data
	models get a bit more complex.

	WARNING: you'll get back the same dict every time.  You need to copy
	it if you can't process is between to visits in the iterator.
	"""
	if not service.publications:
		return  # don't worry about missing meta if there are no publications

	rec = makeBaseRecord(service)
	rec["owner"] = service.limitTo
	subjects = [str(item) for item in service.getMeta("subject") or (None,)]
	rec["subject"] = subjects.pop()
	for pub in service.publications:
		rec["renderer"] = pub.render
		rec["accessURL"] = service.getURL(pub.render, absolute=False)
		rec["referenceURL"] = base.getMetaText(service, "referenceURL")
		try:
			rec["browseable"] = service.isBrowseableWith(pub.render)
		except AttributeError:  # service is not a ServiceBasedPage
			rec["browseable"] = False
		for setName in pub.sets:
			rec["setName"] = setName
			yield rec
	for subject in subjects:
		rec["subject"] = subject
		yield rec


def iterResRecs(res):
	"""as iterSvcRecs, just for ResRecs rather than Services.
	"""
	rec = makeBaseRecord(res)
	# resource records only make sense if destined for the registry
	rec["setName"] = "ivo_managed"
	rec["renderer"] = "rcdisplay"
	for subject in [str(item) for item in res.getMeta("subject") or (None,)]:
		rec["subject"] = subject
		yield rec


def iterDataRecs(res):
	"""as iterSvcRecs, just for DataDescriptors rather than Services.
	"""
	rec = makeBaseRecord(res)
	for setName in res.registration.sets:
		rec["setName"] = setName
		rec["renderer"] = "rcdisplay"
		for subject in [str(item) for item in res.getMeta("subject") or (None,)]:
			rec["subject"] = subject
			yield rec


class RDRscRecIterator(grammars.RowIterator):
	"""A RowIterator yielding resource records for inclusion into the
	service list for the services defined in the source token RD.
	"""
	def _iterRows(self):
		for svc in self.sourceToken.services:
			self.curSource = svc.id
			for sr in iterSvcRecs(svc):
				yield sr.copy()
		for res in self.sourceToken.resRecs:
			self.curSource = res.id
			for sr in iterResRecs(res):
				yield sr.copy()
		for res in itertools.chain(self.sourceToken.tables, self.sourceToken.dds):
			self.curSource = res.id
			if res.registration:
				for sr in iterDataRecs(res):
					yield sr.copy()
	
	def getLocation(self):
		return "%s#%s"%(self.sourceToken.sourceId, self.curSource)


class RDRscRecGrammar(grammars.Grammar):
	"""A grammar for "parsing" raw resource records from RDs.
	"""
	rowIterator = RDRscRecIterator
_rdRscRecGrammar = base.makeStruct(RDRscRecGrammar)


def updateServiceList(rds, metaToo=False, connection=None, onlyWarn=True):
	"""updates the services defined in rds in the services table in the database.
	"""
	recordsWritten = 0
	parseOptions = rsc.getParseOptions(validateRows=True, batchSize=20)
	if connection is None:
		connection = base.getDBConnection("admin")
	dd = getServicesRD().getById("tables")
	dd.grammar = _rdRscRecGrammar
	depDD = getServicesRD().getById("deptable")
	msg = None
	for rd in rds:
		if rd.sourceId.startswith("/"):
			raise Error("Resource descriptor ID must not be absolute, but"
				" '%s' seems to be."%rd.sourceId)
		try:
			data = rsc.makeData(dd, forceSource=rd, parseOptions=parseOptions,
				connection=connection)
			recordsWritten += data.nAffected
			rsc.makeData(depDD, forceSource=rd, connection=connection)

			if metaToo:
				from gavo.protocols import tap
				tap.unpublishFromTAP(rd, connection)
				for dependentDD in rd:
					rsc.Data.create(dependentDD, connection=connection).updateMeta()
				tap.publishToTAP(rd, connection)

		except base.MetaValidationError, ex:
			msg = ("Aborting publication of rd '%s' since meta structure of"
				" %s (id='%s') is invalid:\n * %s")%(
				rd.sourceId, repr(ex.carrier), ex.carrier.id, "\n * ".join(ex.failures))
		except base.NoMetaKey, ex:
			msg = ("Aborting publication of '%s' at service '%s': Resource"
				" record generation failed: %s"%(
				rd.sourceId, ex.carrier.id, str(ex)))
		except Exception, ex:
			base.ui.notifyError("Fatal error while publishing from RD %s: %s"%(
				rd.sourceId, str(ex)))
			raise

		if msg is not None:
			if onlyWarn:
				warnings.warn(msg)
			else:
				raise base.ReportableError(msg)
		msg = None

	connection.commit()
	return recordsWritten


def _purgeFromServiceTables(rdId, conn):
	"""purges all resources coming from rdId from the registry tables.

	This is not for user code that should rely on the tables doing the
	right thing (e.g., setting the deleted flag rather than deleting rows).
	Test code that is not in contact with the actual registry might want 
	this, though (until postgres grows nested transactions).
	"""
	cursor = conn.cursor()
	for tableName in [
			"resources", "interfaces", "sets", "subjects", "res_dependencies"]:
		cursor.execute("delete from dc.%s where sourceRD=%%(rdId)s"%tableName,
			{"rdId": rdId})
	cursor.close()



################ UI stuff

def findAllRDs():
	"""returns ids of all RDs (inputs and built-in) known to the system.
	"""
	rds = []
	inputsDir = base.getConfig("inputsDir")
	for dir, dirs, files in os.walk(inputsDir):
		for file in files:
			if file.endswith(".rd"):
				rds.append(os.path.splitext(
					utils.getRelativePath(os.path.join(dir, file), inputsDir))[0])
	for name in pkg_resources.resource_listdir('gavo', 
			"resources/inputs/__system__"):
		if name.startswith("."):  # ignore VCS files (and possibly others:-)
			continue
		rds.append(os.path.splitext("__system__/%s"%name)[0])
	return rds


def getRDs(args):
	"""returns a list of RDs from a list of more-or-less RD ids.
	"""
	try:
		return [base.caches.getRD(rdPath, doQueries=False)
			for rdPath in args]
	except:
		sys.stderr.write("Error occurred in %s\n"%rdPath)
		raise


def parseCommandLine():
	import optparse
	parser = optparse.OptionParser(usage="%prog [options] {<rd-name>}")
	parser.add_option("-a", "--all", help="search everything below inputsDir"
		" for publications.", dest="all", action="store_true")
	parser.add_option("-m", "--meta-too", help="update meta information, too",
		dest="meta", action="store_true")
	parser.add_option("-f", "--fixed", help="ignored", action="store_true")
	return parser.parse_args()


def updateRegistryTimestamp():
	"""edits the dateupdated field for the registry service in servicelist.
	"""
	with base.AdhocQuerier(base.getAdminConn) as q:
		regSrv = getRegistryService()
		q.query("UPDATE services SET dateupdated=%(now)s"
			" WHERE sourcerd=%(rdId)s AND resId=%(sId)s", {
			"rdId": regSrv.rd.sourceId,
			"sId": regSrv.id,
			"now": datetime.datetime.utcnow(),
		})
	getServicesRD().touchTimestamp()


def tryServiceReload():
	"""tries to reload the services RD.

	This only works if there's [web]adminpasswd and[web]serverURL
	set, and both match what the actual server uses.
	"""
	import urllib
	pw = base.getConfig("web", "adminpasswd")
	if pw=="":
		base.ui.notifyWarning("Not reloading services RD on server since"
			" no admin password available.")
	try:
		f = utils.urlopenRemote(base.makeAbsoluteURL("/seffe/__system__/services"),
			urllib.urlencode({"__nevow_form__": "adminOps", "submit": "Reload RD"}),
			creds=("gavoadmin", pw))
	except IOError, ex:
		base.ui.notifyWarning("Could not reload services RD (%s).  This means"
			" that the registry time stamp on the server will be out of date."
			" You should reload //services manually."%ex)
	else:
		base.ui.notifyInfo("Reloaded services RD (registry timestamp up to date)")


def main():
	"""handles the user interaction for gavopublish.
	"""
	from gavo import rscdesc
	from gavo import web
	from gavo.user import plainui
	plainui.SemiStingyPlainUI(base.ui)
	opts, args = parseCommandLine()
	getServicesRD().touchTimestamp()
	if opts.all:
		args = findAllRDs()
	updateServiceList(getRDs(args), metaToo=opts.meta)
	tryServiceReload()


if __name__=="__main__":
	main()
