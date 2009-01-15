<resource schema="public">
<meta name="description">Predefined procedures in the GAVO DC.</meta>

<proc name="simpleSelect" isGlobal="True">
	<consComp>
		<arg key="assignments"/>
		<arg key="table"/>
		<arg key="column"/>
		<arg key="errCol" default="'&lt;unknown&gt;'"/>
		assignments = base.parseAssignments(assignments)
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
		raise gavo.ValidationError("Internal error (%s)"%
			base.encodeDbMsg(msg), "<unknown>")
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
		map = base.NameMap(os.path.join(
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
</resource>
