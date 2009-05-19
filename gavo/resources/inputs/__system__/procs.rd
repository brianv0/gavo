<resource schema="public">
<meta name="description">Predefined procedures in the GAVO DC.</meta>

<proc name="simpleSelect" isGlobal="True">
	<consComp>
		<arg key="assignments"/>
		<arg key="table"/>
		<arg key="column"/>
		<arg key="errCol" default="'&lt;unknown&gt;'"/>
		assignments = utils.parseAssignments(assignments)
		dbNames, recNames = assignments.keys(), assignments.values()
		query = "SELECT %s FROM %s WHERE %s=%%(val)s"%(
			", ".join(dbNames), table, column)
		try:
			querier = base.SimpleQuerier()
		except (base.Error, base.DbError):
			# we probably have no db connectivity.  Don't bring down the
			# whole program without knowing we actually need it -- raise an error
			# as soon as someone tries to use the connection
			class Raiser:
				def __getattr__(self, name):
					raise base.Error("No db connectivity available.")
			querier = Raiser()
		return locals()
	</consComp>
	<arg key="val"/><![CDATA[
	try:
		res = querier.query(query, {"val": val}).fetchall()[0]
		for name, resVal in zip(recNames, res):
			name, default = parseDestWithDefault(name)
			if resVal is None:
				vars[name] = default
			else:
				vars[name] = resVal
	except IndexError:
		raise base.ValidationError("The item %s didn't match"
			" any data.  Since this data is required for further"
			" operations, I'm giving up"%val, errCol)
	except base.DBError, msg:
		querier.rollback()
		raise base.ValidationError("Internal error (%s)"%
			base.encodeDBMsg(msg), "<unknown>")
]]></proc>

<proc name="resolveObject" isGlobal="True">
	<consComp>
		<arg key="ignoreUnknowns" default="True"/>
		from gavo.protocols import simbadinterface
		return {"ignoreUnknowns": parseBooleanLiteral(ignoreUnknowns),
			"resolver": simbadinterface.Sesame(saveNew=True)}
	</consComp>
	<arg key="identifier"/>
	"""is a proc that resolves identifiers to simbad positions.

	It caches query results (positive as well as negative ones) in
	cacheDir.  To avoid flooding simbad with repetetive requests, it
	raises an error if this directory is not writable.

	It leaves J2000.0 positions as floats  in the simbadAlpha and 
	simbadDelta variables.

	If you set the consArg ignoreUnknowns to false, unknown objects will
	yield ValidationErrors.
	"""
	ra, dec = None, None
	try:
		ra, dec = resolver.getPositionFor(identifier)
	except KeyError:
		if not ignoreUnknowns:
			raise base.Error("resolveObject could not resolve object"
				" %s."%identifier)
	vars["simbadAlpha"] = ra
	vars["simbadDelta"] = dec
</proc>

<proc name="mapValue" isGlobal="True">
	<doc><![CDATA[
	is a macro that translates vaules via a utils.NameMap
	
	Construction arguments:

	* sourceName -- an inputsDir-relative path to the NameMap source file,
	* logFailures (optional) -- if somehow true, non-resolved names will 
	  be logged
	* destination -- the field the mapped value should be written into.

	Argument:

	* value -- the value to be mapped.

	If an object cannot be resolved, a null value is entered (i.e., you
	shouldn't get an exception out of this macro but can weed out "bad"
	records through notnull-conditions later if you wish).

	Destination may of course be the source field (though that messes
	up idempotency of macro expansion, which shouldn't usually hurt).

	The format of the mapping file is

	<target key><tab><source keys>

	where source keys is a whitespace-seperated list of values that should
	be mapped to target key (sorry the sequence's a bit unusual).

	A source key must be encoded quoted-printable.  This usually doesn't
	matter except when it contains whitespace (a blank becomes =20) or equal
	signs (which become =3D).
]]></doc>
	<consComp>
		<arg key="destination"/>
		<arg key="logFailures" default="False"/>
		<arg key="failuresAreNone" default="False"/>
		<arg key="sourceName"/>
		map = utils.NameMap(os.path.join(
			base.getConfig("inputsDir"), sourceName))
		return locals()
	</consComp>
	<arg key="value"/>
	try:
		vars[destination] = map.resolve(str(value))
	except KeyError:
		if logFailures:
			sys.stderr.write("Name %s could not be mapped\n"%value)
		if failuresAreNone:
			vars[destination] = None
		else:
			raise base.LiteralParseError("Name %s could not be mapped"%value,
				destination, value)
</proc>

<proc name="fullQuery" isGlobal="True">
	<doc><![CDATA[
	runs a free query against the data base and enters the first result 
	record into vars.

	Argument:

	* query -- an SQL query

	The locals() will be passed as data, so you can define more arguments
	and refer to their keys in the query.
	]]></doc>

	q = base.SimpleQuerier()
	res = q.runIsolatedQuery(query, data=locals(), asDict=True)
	vars.update(res[0])
</proc>

<procDef id="expandIntegers" type="rowfilter">
	<doc>
	A row processor that produces copies of rows based on integer indices.

	The idea is that sometimes rows have specifications like "Star 10
	through Star 100".  These are a pain if untreated.  A RowExpander
	could create 90 individual rows from this.

	A RowExpander has three arguments: The names of the nonterminals
	giving the beginning and the end of the range (both must be int-able
	strings), and the name of the nonterminal that the new index should 
	be assigned to.
	</doc>
	<setup>
		<par key="startName"/>
		<par key="endName"/>
		<par key="indName"/>
	</setup>
	<code>
		try:
			lowerInd = int(row[startName])
			upperInd = int(row[endName])
		except (ValueError, TypeError): # either one not given
			yield row
			return
		for ind in range(lowerInd, upperInd+1):
			newRow = row.copy()
			newRow[indName] = ind
			yield newRow
	</code>
</procDef>


<procDef id="expandDates" type="rowfilter">
	<doc>
	is a row generator to expand time ranges.

	The finished dates are left in destination as datetime.datetime
	instances

	* dest -- name of the field we're writing into.
	* start -- the start date, as either a datetime object or a column ref.
	* end -- the end date
	* hrInterval -- a float literal specifying how many hours should be between
	  the generated timestamps
	</doc>
	<setup>
		<par key="dest">'curTime'</par>
		<par key="start"/>
		<par key="end"/>
		<par key="hrInterval" late="True">24</par>
		<code>
		def _parseTime(val, fieldName):
			try:
				val = val
				if isinstance(val, datetime.datetime):
					return val
				elif isinstance(val, datetime.date):
					return datetime.datetime(val.year, val.month, val.day)
				else:
					return datetime.datetime(*time.strptime(val, "%Y-%m-%d")[:3])
			except Exception, msg:
				raise base.ValidationError("Bad date from %s (%s)"%(name,
					unicode(msg)), dest)
		</code>
	</setup>
	<code>
		stampTime = _parseTime(row[start], "start")
		endTime = _parseTime(row[end], "end")
		endTime = endTime+datetime.timedelta(hours=23)
		try:
			interval = datetime.timedelta(hours=float(hrInterval))
		except ValueError:
			raise base.ValidationError("Not a time interval: '%s'"%hrInterval,
				"hrInterval")
		while stampTime&lt;=endTime:
			newRow = row.copy()
			newRow[dest] = stampTime
			yield newRow
			stampTime = stampTime+interval
	</code>
</procDef>


<procDef id="expandComma" type="rowfilter">
	<doc>
	is a row generator that reads comma seperated values from a
	field and returns one row with a new field for each of them.
	</doc>
	<setup>
		<par key="srcField"/>
		<par key="destField"/>
	</setup>
	<code>
		src = row[srcField]
		if src is not None and src.strip():
			for item in src.split(","):
				item = item.strip()
				if not item:
					continue
				newRow = row.copy()
				newRow[destField] = item
				yield newRow
	</code>
</procDef>
</resource>
