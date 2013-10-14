"""
The SSAP core and supporting code.

"""

from cStringIO import StringIO

from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import svcs
from gavo import votable
from gavo.formats import votablewrite
from gavo.protocols import datalink
from gavo.protocols import sdm
from gavo.svcs import pql
from gavo.svcs import outputdef
from gavo.votable import V


RD_ID = "//ssap"

def getRD():
	return base.caches.getRD(RD_ID)


class SSADescriptor(datalink.ProductDescriptor):
	ssaRow = None

	@classmethod
	def fromSSARow(cls, ssaRow, paramDict):
		"""returns a descriptor from a row in an ssa table and
		the params of that table.
		"""
		paramDict.update(ssaRow)
		# this could come from _combineRowIntoOne if it ran
		if "collected_calibs" in ssaRow:
			ssaRow["collected_calibs"].add(ssaRow["ssa_fluxcalib"])
			ssaRow["ssa_fluxcalib"] = ssaRow["collected_calibs"]

		ssaRow = paramDict
		res = cls.fromAccref(ssaRow['accref'])
		res.ssaRow = ssaRow
		return res


def _combineRowIntoOne(ssaRows):
	"""makes a "total row" from ssaRows.

	In the resulting row, minima and maxima are representative of the
	whole result set, and enumerated columsn are set-valued.

	This is useful when generating parameter metadata.
	"""
	if not ssaRows:
		raise base.ReportableError("Datalink meta needs at least one result row")

	totalRow = ssaRows[0].copy()
	totalRow["mime"] = set([totalRow["mime"]])
	calibs = set()

	for row in ssaRows[1:]:
		if row["ssa_specstart"]<totalRow["ssa_specstart"]:
			totalRow["ssa_specstart"] = row["ssa_specstart"]
		if row["ssa_specend"]>totalRow["ssa_specend"]:
			totalRow["ssa_specend"] = row["ssa_specend"]
		totalRow["mime"].add(row["mime"])
		calibs.add(row.get("ssa_fluxcalib", None))
	
	totalRow["collect_calibs"] = set(c for c in calibs if c is not None)
	return totalRow


def getDatalinkMeta(dlSvc, ctx, ssaTable):
	"""adds the datalink resource declaration to vot.

	dlSvc is the datalink service, ctx must the the VOTableContext used
	to generate vot, ssaTable a non-empty SSA result table.
	"""
	totalRow = _combineRowIntoOne(ssaTable.rows)
	desc = SSADescriptor.fromSSARow(totalRow, ssaTable.getParamDict())
	return dlSvc.core.adaptForDescriptor(desc
		).getDatalinkDescriptionResource(ctx, dlSvc)


class SSAPCore(svcs.DBCore):
	"""A core doing SSAP queries.

	This core knows about metadata queries, version negotiation, and 
	dispatches on REQUEST.  Thus, it may return formatted XML data
	under certain circumstances.

	SSAPCores also know how to handle getData requests according to the 2012
	draft.  To enable getData support, add a tablesource property to the 
	embedding service and read `Supporting getData`_
	"""
	name_ = "ssapCore"

	ssapVersion = "1.04"

	outputTableXML = """
		<outputTable verbLevel="30">
			<property name="virtual">True</property>
			<FEED source="//ssap#coreOutputAdditionals"/>
		</outputTable>"""

	def wantsTableWidget(self):
		# we only return XML, and we have a custom way of doing limits.
		return False

	# The following is evaluated by the form renderer to suppress the
	# format selection widget.  We should really furnish cores with
	# some way to declare what they're actually returning.
	HACK_RETURNS_DOC = True

	################ Helper methods

	def _makeMetadata(self, service):
		metaTD = self.outputTable.change(id="results")
		for param in metaTD.params:
			param.name = "OUTPUT:"+param.name
		dd = base.makeStruct(rscdef.DataDescriptor, parent_=self.rd,
			makes=[base.makeStruct(rscdef.Make, table=metaTD,
				rowmaker=base.makeStruct(rscdef.RowmakerDef))])
		dd.setMetaParent(service)

		for inP in self.inputTable.params:
			dd.feedObject("param", inP.change(name="INPUT:"+inP.name))

		dd.setMeta("_type", "meta")
		dd.addMeta("info", base.makeMetaValue(
			"", name="info", infoName="QUERY_STATUS", infoValue="OK"))
		dd.addMeta("info", base.makeMetaValue(
			"SSAP", name="info", infoName="SERVICE_PROTOCOL", infoValue="1.04"))

		data = rsc.makeData(dd)
		
		return "application/x-votable+xml", votablewrite.getAsVOTable(data)

	def _declareGenerationParameters(self, resElement, ssaTable):
		"""adds a table declaring getData support to resElement as appropriate.

		resElement is a votable.V RESOURCE element, ssaTable is the SSA response
		table.
		"""
		if ssaTable.rows:
			specMin = min(row["ssa_specstart"] for row in ssaTable.rows)
			specMax = max(row["ssa_specend"] for row in ssaTable.rows)
		else:
			specMin = specMax = None

		# fluxcalib is a param in hcd
		try:
			calibrations = set([ssaTable.getParam("ssa_fluxcalib").lower()])
		except base.NotFoundError:
			calibrations = set((row["ssa_fluxcalib"] or "").lower()
				for row in ssaTable.rows)
		calibrations.add("relative")

		resElement[
			V.RESOURCE(name="getDataMeta")[
				V.TABLE(name="generationParameters") [
					V.PARAM(name="BAND", datatype="float", unit="m")[
						V.DESCRIPTION["The spectral range of the cutout"],
						V.VALUES[
							V.MIN(value=specMin),
							V.MAX(value=specMax)]],

					V.PARAM(name="FLUXCALIB", datatype="char", arraysize="*") [
						V.DESCRIPTION["Recalibrate the spectrum to..."],
						V.VALUES[
							[V.OPTION(value=c) for c in calibrations]]],
						
    			V.PARAM(name="FORMAT", datatype="char", arraysize="*",
			      	value="application/x-votable+xml") [
			      V.DESCRIPTION["Format to deliver the spectrum in."],
		      	V.VALUES[[
		      		V.OPTION(value=mime) for mime in sdm.GETDATA_FORMATS]]]]]]

	############### Implementation of the service operations

	def _run_getData(self, service, inputTable, queryMeta):
		"""returns mime and payload for a getData operation on the parameters
		defined in inputTable.
		"""
		tablesourceId = service.getProperty("tablesource", None)
		if tablesourceId is None:
			raise base.ValidationError("No getData support on %s"%
				service.getMeta("identifier"), "REQUEST", hint="Only SSAP"
				" services with a tablesource property support getData")
		tablesourceDD = service.rd.getById(tablesourceId)

		handledArguments = set(["REQUEST", "COMPRESS", "MAXREC", "FORMAT"])

		pubDID = inputTable.getParam("PUBDID")
		if pubDID is None:
			raise base.ValidationError("PUBDID mandatory for getData", "PUBDID")
		handledArguments.add("PUBDID")

		sdmData = sdm.makeSDMDataForPUBDID(pubDID, 
			self.queriedTable, tablesourceDD)

		calib = inputTable.getParam("FLUXCALIB")
		if calib:
			sdmData.tables[sdmData.tables.keys()[0]] = sdm.mangle_fluxcalib(
				sdmData.getPrimaryTable(),
				calib)
			handledArguments.add("FLUXCALIB")

		# XXX TODO: replacing tables like that probably is not a good idea.
		# Figure out something better (actually copy sdmData rather than
		# fiddle with it?)
		rawBand = inputTable.getParam("BAND")
		if rawBand:
			bands = pql.PQLFloatPar.fromLiteral(rawBand, "BAND")
			if len(bands.ranges)!=1:
				raise base.ValidationError("BAND must specify exactly one interval",
					"BAND")
			band = bands.ranges[0]
			sdmData.tables[sdmData.tables.keys()[0]] = sdm.mangle_cutout(
				sdmData.getPrimaryTable(),
				band.start or -1, band.stop or 1e308)
			handledArguments.add("BAND")

		# Hack alert: the renderer inserts some silly keys right now (it
		# shouldn't do that).  While it does, ignore keys with an underscore
		# in front
		unhandledArguments = set(name.upper()
			for name, value in queryMeta.ctxArgs.iteritems() if value
				and not name.startswith("_"))-handledArguments
		if unhandledArguments:
			raise base.ValidationError("The following parameter(s) are not"
				" accepted by this service: %s"%", ".join(unhandledArguments),
				"(various)")

		if not sdmData.getPrimaryTable().rows:
			raise base.EmptyData("Spectrum is empty.", "(various)")

		return sdm.formatSDMData(sdmData, inputTable.getParam("FORMAT"), 
			queryMeta)
			
	def _run_getTargetNames(self, service, inputTable, queryMeta):
		with base.getTableConn()  as conn:
			table = rsc.TableForDef(self.queriedTable, create=False,
				role="primary", connection=conn)
			destTD = base.makeStruct(outputdef.OutputTableDef, 
				parent_=self.queriedTable.parent,
				id="result", onDisk=False,
				columns=[self.queriedTable.getColumnByName("ssa_targname")])
			res = rsc.TableForDef(destTD, rows=table.iterQuery(destTD, "",
				distinct=True))
			res.noPostprocess = True
			return res

	def _run_queryData(self, service, inputTable, queryMeta):
		format = inputTable.getParam("FORMAT") or ""
		if format.lower()=="metadata":
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
			queryStatus = "OVERFLOW"
			queryStatusBody = ("Exactly %s rows were returned.  This means your"
				" query probably reached the match limit.  Increase MAXREC."%limit)
		else:
			queryStatus = "OK"
			queryStatusBody = ""

		# We wrap our result into a data instance since we need to set the
		#	result type
		data = rsc.wrapTable(res)
		data.setMeta("_type", "results")
		data.addMeta("_votableRootAttributes",
			'xmlns:ssa="http://www.ivoa.net/xml/DalSsap/v1.0"')

		# The returnRaw property is a hack, mainly for unit testing;
		# The renderer would have to add the QUERY_STATUS here.
		if service.getProperty("returnData", False):
			return data

		# we fix tablecoding to td for now since nobody seems to like
		# binary tables and we don't have huge tables here.
		votCtx = votablewrite.VOTableContext(tablecoding="td")
		vot = votablewrite.makeVOTable(data, votCtx)
		resElement = vot.makeChildDict()["RESOURCE"][0]
		resElement[
			V.INFO(name="SERVICE_PROTOCOL", value=self.ssapVersion)["SSAP"],
			V.INFO(name="QUERY_STATUS", value=queryStatus)[
				queryStatusBody]]
	
		# old and stinky getData (remove at some point)
		if service.getProperty("tablesource", None) is not None:
			self._declareGenerationParameters(vot, res)
		# new and shiny datalink
		datalinkId = service.getProperty("datalink", None)
		if datalinkId and res:
			vot[getDatalinkMeta(self.rd.getById(datalinkId), votCtx, res)]

		return "application/x-votable+xml", votable.asString(vot)

	################ the main dispatcher

	def run(self, service, inputTable, queryMeta):
		requestType = (inputTable.getParam("REQUEST") or "").upper()
		if requestType=="QUERYDATA":
			return self._run_queryData(service, inputTable, queryMeta)
		elif requestType=="GETDATA":
			return self._run_getData(service, inputTable, queryMeta)
		elif requestType=="GETTARGETNAMES":
			return self._run_getTargetNames(service, inputTable, queryMeta)
		else:
			raise base.ValidationError("Missing or invalid value for REQUEST.",
				"REQUEST")


class SSAPProcessCore(SSAPCore):
	"""Temporary Hack; delete when ccd700 is ported to a sane infrastructure.
	"""
	name_ = "ssapProcessCore"
