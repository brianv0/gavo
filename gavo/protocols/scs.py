"""
IVOA cone search: Helper functions, a core, and misc.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo import base
from gavo import svcs
from gavo.protocols import simbadinterface  #noflake: for registration
from gavo.svcs import outputdef


def findNClosest(alpha, delta, tableDef, n, fields, searchRadius=5):
	"""returns the n objects closest around alpha, delta in table.

	n is the number of items returned, with the closest ones at the
	top, fields is a sequence of desired field names, searchRadius
	is a radius for the initial q3c search and will need to be
	lowered for dense catalogues and possibly raised for sparse ones.

	The last item of each row is the distance of the object from
	the query center in degrees.

	The query depends on postgastro extension (and should be changed to
	use pgsphere).  It also requires the q3c extension.
	"""
	with base.AdhocQuerier(base.getTableConn) as q:
		raField = tableDef.getColumnByUCDs("pos.eq.ra;meta.main", 
			"POS_EQ_RA_MAIN").name
		decField = tableDef.getColumnByUCDs("pos.eq.dec;meta.main", 
			"POS_EQ_RA_MAIN").name
		res = q.query("SELECT %s,"
				" celDistDD(%s, %s, %%(alpha)s, %%(delta)s) as dist_"
				" FROM %s WHERE"
				" q3c_radial_query(%s, %s, %%(alpha)s, %%(delta)s,"
				" %%(searchRadius)s)"
				" ORDER BY dist_ LIMIT %%(n)s"%
					(",".join(fields), raField, decField, tableDef.getQName(),
						raField, decField),
			locals()).fetchall()
		return res


def parseHumanSpoint(cooSpec, colName=None):
	"""tries to interpret cooSpec as some sort of cone center.

	Attempted interpretations include various forms of coordinate pairs
	and simbad objects; hence, this will in general cause network traffic.

	If no sense can be made, a ValidationError on colName is raised.
	"""
	try:
		cooPair = base.parseCooPair(cooSpec)
	except ValueError:
		simbadData = base.caches.getSesame("web").query(cooSpec)
		if not simbadData:
			raise base.ValidationError("%s is neither a RA,DEC"
				" pair nor a simbad resolvable object."%cooSpec, colName)
		cooPair = simbadData["RA"], simbadData["dec"]
	return cooPair


class SCSCore(svcs.DBCore):
	"""A core performing cone searches.

	This will, if it finds input parameters it can make out a position from,
	add a _r column giving the distance between the match center and 
	the columns that a cone search will match against.

	If any of the conditions for adding _r aren't met, this will silently
	degrade to a plain DBCore.

	You will almost certainly want a::

		<FEED source="//scs#coreDescs"/>
	
	in the body of this (in addition to whatever other custom conditions
	you may have).
	"""
	name_ = "scsCore"

	def onElementComplete(self):
		self._onElementCompleteNext(SCSCore)
		# raColumn and decColumn must be from the queriedTable (rather than
		# the outputTable, as it would be preferable), since we're using
		# them to build database queries.
		self.raColumn = self.queriedTable.getColumnByUCDs(
			"pos.eq.ra;meta.main", "POS_EQ_RA_MAIN")
		self.decColumn = self.queriedTable.getColumnByUCDs(
			"pos.eq.dec;meta.main", "POS_EQ_DEC_MAIN")
		try:
			self.idColumn = self.outputTable.getColumnByUCDs(
				"meta.id;meta.main", "ID_MAIN")
		except ValueError:
			base.ui.notifyWarning("SCS core at %s: Output table has no"
				" meta.id;meta.main column.  This service will be invalid."%
				self.getSourcePosition())

		self.distCol = base.resolveCrossId("//scs#distCol")
		self.outputTable = self.outputTable.change(
			columns=[self.distCol]+self.outputTable.columns)

		if not self.hasProperty("defaultSortKey"):
			self.setProperty("defaultSortKey", self.distCol.name)

	def _guessDestPos(self, inputTable):
		"""returns RA and Dec for a cone search possibly contained in inputTable.

		If no positional query is discernable, this returns None.
		"""
		pars = inputTable.getParamDict()
		if pars.get("RA") is not None and pars.get("DEC") is not None:
			return pars["RA"], pars["DEC"]
		elif pars.get("hscs_pos") is not None:
			try:
				return parseHumanSpoint(pars["hscs_pos"])
			except ValueError:
				# We do not want to fail for this fairly unimportant thing.  
				# If the core actually needs the position, it should fail itself.
				return None
		else:
			return None

	def _getDistColumn(self, destPos):
		"""returns an outputField selecting the distance of the match
		object to the cone center.
		"""
		if destPos is None:
			select = "NULL"
		else:
			select = "degrees(spoint(radians(%s), radians(%s)) <-> %s)"%(
				self.raColumn.name, self.decColumn.name,
				"spoint '(%fd,%fd)'"%destPos)

		return self.distCol.change(select=select)

	def _fixupQueryColumns(self, destPos, baseColumns):
		"""returns the output columns from baseColumns for a query
		centered at destPos.

		In particular, the _r column is primed so it yields the right result
		if destPos is given.
		"""
		res = []
		for col in baseColumns:
			if col.name=="_r":
				res.append(self._getDistColumn(destPos))
			else:
				res.append(col)
		return res

	def _makeResultTableDef(self, service, inputTable, queryMeta):
		destPos = self._guessDestPos(inputTable)

		outCols = self._fixupQueryColumns(destPos,
			self.getQueryCols(service, queryMeta))

		return base.makeStruct(outputdef.OutputTableDef,
			parent_=self.queriedTable.parent, 
			id="result",
			onDisk=False, 
			columns=outCols,
			params=self.queriedTable.params)
