<resource schema="dc" resdir="__system">
	<meta name="description">Helper objects for the support of the VO's
	ad-hoc "parameter query language" as used in various DAL protocols.
	</meta>

	<procDef id="posParameter" type="phraseMaker">
		<doc>
			A parameter containing "positions", i.e., pairs of decimal floats.
			SSAP's POS attribute is an example for these.

			Only one input key is supported.  The generated expression 
			matches again the
		</doc>

		<setup>
			<par name="posCol" description="Name of the database column
				to be compared against the input value(s).  It must be of
				type spoint.</par>
		</setup>

		<code>
			key = inputKeys[0].name
			parsed = psql.parsePQL(inPars.get(key, None))
			if parsed is not None:
				return parsed.iterClauses(outPars, posCol)
		</code>
	</procDef>
</resource>
