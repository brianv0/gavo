<resource schema="dc" resdir="__system">
	<meta name="description">Helper objects for the support of the VO's
	ad-hoc "parameter query language" as used in various DAL protocols.
	</meta>

	<procDef id="coneParameter" type="phraseMaker">
		<doc>
			A parameter containing a cone search with a single position-like
			key (the first, expecting a coordinate pair fairly leniently) and
			a cone search (a float, in the second input key).

			The generated expression uses pgsphere.
		</doc>

		<setup>
			<par name="posCol" description="Name of the database column
				to be compared against the input value(s).  It must be of
				type spoint."/>
		</setup>

		<code>
			try:
				posKey = inputKeys[0].name
				sizeKey = inputKeys[1].name
			except IndexError:
				raise base.ValidationError("Operator error: the cone condition"
					" is lacking input keys.", "query")
			parsed = pql.PQLPositionPar.fromLiteral(
				inPars.get(posKey, None), posKey)
			if parsed is not None:
				yield parsed.getConeSQL(posCol, outPars, 
					float(inPars.get(sizeKey, 0.5)))
		</code>
	</procDef>

	<procDef id="dateParameter">
		<doc>
			A parameter constraining an epoch or similar. 
		</doc>

		<setup>
			<par name="consCol" description="Name of the database column
				constrained by the input value.  Must be a date or a timestamp."/>
		</setup>

		<code>
			key = inputKeys[0].name
			parsed = pql.PQLDatePar.fromLiteral(inPars.get(key, None), key)
			if parsed is not None:
				yield parsed.getSQL(consCol, outPars)
		</code>
	</procDef>

</resource>
