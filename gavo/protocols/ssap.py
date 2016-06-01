"""
The SSAP core and supporting code.

"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo import base
from gavo import rsc
from gavo import rscdef
from gavo import svcs
from gavo import votable
from gavo.formats import votablewrite
from gavo.protocols import datalink
from gavo.svcs import outputdef
from gavo.votable import V


RD_ID = "//ssap"
MS = base.makeStruct


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
		res = cls.fromAccref(ssaRow["ssa_pubDID"], ssaRow['accref'])
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


def getDatalinkCore(dlSvc, ssaTable):
	"""returns a datalink core adapted for ssaTable.

	dlSvc is the datalink service, ssaTable a non-empty SSA result table.
	"""
	allowedRendsForStealing = ["dlget"] #noflake: for stealVar downstack
	totalRow = _combineRowIntoOne(ssaTable.rows)
	desc = SSADescriptor.fromSSARow(totalRow, ssaTable.getParamDict())
	return dlSvc.core.adaptForDescriptors(svcs.getRenderer("dlget"), [desc])


class SSAPCore(svcs.DBCore):
	"""A core doing SSAP queries.

	This core knows about metadata queries, version negotiation, and 
	dispatches on REQUEST.  Thus, it may return formatted XML data
	under certain circumstances.
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
		dd.addMeta("info", "", infoName="QUERY_STATUS", infoValue="OK")
		dd.addMeta("info", "SSAP", infoName="SERVICE_PROTOCOL", infoValue="1.04")

		data = rsc.makeData(dd)
		
		return base.votableType, votablewrite.getAsVOTable(data)

	############### Implementation of the service operations

	def _run_getTargetNames(self, service, inputTable, queryMeta):
		with base.getTableConn()  as conn:
			table = rsc.TableForDef(self.queriedTable, create=False,
				connection=conn)
			destTD = base.makeStruct(outputdef.OutputTableDef, 
				parent_=self.queriedTable.parent,
				id="result", onDisk=False,
				columns=[self.queriedTable.getColumnByName("ssa_targname")])
			res = rsc.TableForDef(destTD, rows=table.iterQuery(destTD, "",
				distinct=True))
			res.noPostprocess = True
			return res
	
	def _addPreviewLinks(self, resultTable):
		try:
			col = resultTable.tableDef.getColumnByUCD(
				"meta.ref.url;datalink.preview")
		except ValueError:
			# no preview column, nothing to do
			return
		previewName = col.name

		for row in resultTable:
			row[previewName] = row["accref"]+"?preview=True"

	def getQueryCols(self, service, queryMeta):
		"""changes our spoint columns to array[2] as required by SSA.
		"""
		cols = []
		for col in svcs.DBCore.getQueryCols(self, service, queryMeta):
			if col.type=="spoint":
				cols.append(col.change(xtype=None, type="double precision(2)",
					select="array[degrees(long(%s)),degrees(lat(%s))]"%(
						col.name, col.name)))
			else:
				cols.append(col)
		return cols

	def _run_queryData(self, service, inputTable, queryMeta):
		format = inputTable.getParam("FORMAT") or ""
		if format.lower()=="metadata":
			return self._makeMetadata(service)

		limits = [q for q in 
				(inputTable.getParam("MAXREC", None), inputTable.getParam("TOP"))
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

		self._addPreviewLinks(res)

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
		pubDIDId = votCtx.getIdFor(res.tableDef.getColumnByName("ssa_pubDID"))
		resElement = vot.getChildDict()["RESOURCE"][0]
		resElement[
			V.INFO(name="SERVICE_PROTOCOL", value=self.ssapVersion)["SSAP"],
			V.INFO(name="QUERY_STATUS", value=queryStatus)[
				queryStatusBody]]
	
		datalinkId = service.getProperty("datalink", None)
		if datalinkId and res:
			dlService = self.rd.getById(datalinkId)
			dlCore = getDatalinkCore(dlService, res)

			# new and shiny datalink (keep)
			# (we're just using endpoint 0; it should a the sync service)
			dlEndpoint = dlCore.datalinkEndpoints[0]
			vot[dlEndpoint.asVOT(
				votCtx, dlService.getURL(dlEndpoint.rendName), 
				linkIdTo=pubDIDId)]

			# Also point to the dl metadata service
			vot[V.RESOURCE(type="meta", utype="adhoc:service")[
				V.PARAM(name="standardID", datatype="char", arraysize="*",
					value="ivo://ivoa.net/std/DataLink#links-1.0"),
				V.PARAM(name="accessURL", datatype="char", arraysize="*",
					value=self.rd.getById(datalinkId).getURL("dlmeta")),
				V.GROUP(name="inputParams")[
					V.PARAM(name="ID", datatype="char", arraysize="*", 
						ref=pubDIDId,
						ucd="meta.id;meta.main")[
						V.LINK(content_role="ddl:id-source", value="#"+pubDIDId)]]]]

		return "application/x-votable+xml", votable.asString(vot)

	################ the main dispatcher

	def run(self, service, inputTable, queryMeta):
		defaultRequest = service.getProperty("defaultRequest", "")
		requestType = (inputTable.getParam("REQUEST") or defaultRequest).upper()
		if requestType=="QUERYDATA":
			return self._run_queryData(service, inputTable, queryMeta)
		elif requestType=="GETTARGETNAMES":
			return self._run_getTargetNames(service, inputTable, queryMeta)
		else:
			raise base.ValidationError("Missing or invalid value for REQUEST.",
				"REQUEST")


class SSAPProcessCore(SSAPCore):
	"""Temporary Hack; delete when ccd700 is ported to a sane infrastructure.
	"""
	name_ = "ssapProcessCore"
