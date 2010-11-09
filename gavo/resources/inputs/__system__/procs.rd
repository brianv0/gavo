<resource schema="dc" resdir="__system">
<meta name="description">Predefined procedures in the GAVO DC.</meta>

<procDef type="apply" id="simpleSelect">
	<doc>
		Fill variables from a simple  database query.

		The idea is to obtain a set of values from the data base into some
		columns within vars (i.e., available for mapping) based on comparing
		a single input value against a database column.  The query should
		always return exactly one row.  If more rows are returned, the
		first one will be used (which makes the whole thing a bit of a gamble),
		if none are returned, a ValidationError is raised.
	</doc>
	<setup>
		<par key="assignments"><description><![CDATA[mapping from database 
			column names to vars column names, in the format 
			{<db colname>:<vars name>}"]]></description></par>
		<par key="table" description="name of the database table to query"/>
		<par key="column" description="the column to compare the input value
			against"/>
		<par key="errCol">'&lt;unknown&gt;'</par>
		<par key="val" late="True"/>
		<code>
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

			def parseDestWithDefault(dest, defRe=re.compile(r"(\w+)\((.*)\)")):
				"""returns name, default from dests like bla(0).

				This can be used to provide defaulted targets to assignments parsed
				with _parseAssignments.
				"""
				mat = defRe.match(dest)
				if mat:
					return mat.groups()
				else:
					return dest, None
		</code>
	</setup>
	<code><![CDATA[
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
	]]></code>
</procDef>

<procDef type="apply" id="resolveObject">
	<setup>
		<par key="ignoreUnknowns" description="Return Nones for unknown
			objects?  (if false, ValidationErrors will be raised)">True</par>
		<par key="identifier" late="True" 
			description="The identifier to be resolved."/>
		<code>
			from gavo.protocols import simbadinterface
			resolver = simbadinterface.Sesame(saveNew=True)
		</code>
	</setup>
	<doc>
		Resolve identifiers to simbad positions.

		It caches query results (positive as well as negative ones) in
		cacheDir.  To avoid flooding simbad with repetetive requests, it
		raises an error if this directory is not writable.

		It leaves J2000.0 positions as floats  in the simbadAlpha and 
		simbadDelta variables.
	</doc>
	<code>
		ra, dec = None, None
		try:
			ra, dec = resolver.getPositionFor(identifier)
		except KeyError:
			if not ignoreUnknowns:
				raise base.Error("resolveObject could not resolve object"
					" %s."%identifier)
		vars["simbadAlpha"] = ra
		vars["simbadDelta"] = dec
	</code>
</procDef>

<procDef type="apply" id="mapValue">
	<doc><![CDATA[
	is a macro that translates vaules via a utils.NameMap
	
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
	<setup>
		<par key="destination" description="name of the field the mapped 
			value should be written into"/>
		<par key="logFailures" description="Log non-resolved names?">False</par>
		<par key="failuresAreNone" description="Rather than raise an error,
			assign NULL to values not found">False</par>
		<par key="sourceName" description="An inputsDir-relative path to 
			the NameMap source file."/>
		<par key="value" late="True" description="The value to be mapped."/>
		<code>
			map = utils.NameMap(os.path.join(
				base.getConfig("inputsDir"), sourceName))
		</code>
	</setup>
	<code>
		try:
			vars[destination] = map.resolve(str(value))
		except KeyError:
			if logFailures:
				base.ui.notifyWarning("Name %s could not be mapped\n"%value)
			if failuresAreNone:
				vars[destination] = None
			else:
				raise base.LiteralParseError("Name %s could not be mapped"%value,
					destination, value)
	</code>
</procDef>

<procDef type="apply" id="fullQuery">
	<doc><![CDATA[
	runs a free query against the data base and enters the first result 
	record into vars.

	locals() will be passed as data, so you can define more bindings
	and refer to their keys in the query.
	]]></doc>
	<setup>
		<par key="query" description="an SQL query"/>
		<par key="errCol" description="a column name to use when raising a
			ValidationError on failure."
			>'&lt;unknown&gt;'</par>
	</setup>
	<code>
		q = base.SimpleQuerier()
		res = q.runIsolatedQuery(query, data=locals(), asDict=True)
		try:
			vars.update(res[0])
		except IndexError:
			raise base.ValidationError("Could not find a matching row",
				errCol)
	</code>
</procDef>

<procDef id="expandIntegers" type="rowfilter">
	<doc>
	A row processor that produces copies of rows based on integer indices.

	The idea is that sometimes rows have specifications like "Star 10
	through Star 100".  These are a pain if untreated.  A RowExpander
	could create 90 individual rows from this.
	</doc>
	<setup>
		<par key="startName" description="column containing the start value"/>
		<par key="endName" description="column containing the end value"/>
		<par key="indName" description="name the counter should appear under"/>
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
	</doc>
	<setup>
		<par key="dest" description="name of the column the time should
			appear in">'curTime'</par>
		<par key="start" description="the start date(time), as either 
			a datetime object or a column ref"/>
		<par key="end" description="the end date(time)"/>
		<par key="hrInterval" late="True" description="difference
			 between generated timestamps in hours">24</par>
		<code>
		def _parseTime(val, fieldName):
			try:
				val = val
				if isinstance(val, datetime.datetime):
					return val
				elif isinstance(val, datetime.date):
					return datetime.datetime(val.year, val.month, val.day)
				else:
					return utils.parseISODT(val)
			except Exception, msg:
				raise base.ValidationError("Bad date from %s (%s)"%(fieldName,
					unicode(msg)), dest)
		</code>
	</setup>
	<code><![CDATA[
		stampTime = _parseTime(row[start], "start")
		endTime = _parseTime(row[end], "end")
		endTime = endTime+datetime.timedelta(hours=23)

		try:
			interval = float(hrInterval)
		except ValueError:
			raise base.ValidationError("Not a time interval: '%s'"%hrInterval,
				"hrInterval")
		if interval<0.01:
			interval = 0.01
		interval = datetime.timedelta(hours=interval)

		try:
			matchLimit = 100000 #getQueryMeta()["dbLimit"]
		except ValueError:
			matchLimit = 1000000
		while stampTime<=endTime:
			matchLimit -= 1
			if matchLimit<0:
				break
			newRow = row.copy()
			newRow[dest] = stampTime
			yield newRow
			stampTime = stampTime+interval
	]]></code>
</procDef>


<procDef id="expandComma" type="rowfilter">
	<doc>
	A row generator that reads comma seperated values from a
	field and returns one row with a new field for each of them.
	</doc>
	<setup>
		<par key="srcField" description="Name of the column containing
			the full string"/>
		<par key="destField" description="Name of the column the individual
			columns are written to"/>
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
