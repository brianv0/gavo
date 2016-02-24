<!-- definitions related to supporting SIAPv2; the underlying table is 
obscore and defined using the means given there. -->

<resource resdir="__system" schema="dc">
	<STREAM id="POSpar">
		<doc>A stream defining a SIAPv2-style POS par over an obscore table.
		</doc>
		<condDesc>
			<inputKey name="POS" type="text" multiplicity="multiple"
				tablehead="Position"
				description="A spatial constraint using SIAPv2 CIRCLE, RANGE, or
					POLYGON shapes and respective values in decimal degrees.">
			</inputKey>
			<phraseMaker>
				<setup>
					<code>
						from gavo.protocols import siap
					</code>
				</setup>
				<code>
					for inStr in inPars["POS"]:
						yield "s_region &amp;&amp;%%(%s)s"%(
							base.getSQLKey("pos", siap.parseSIAP2Geometry(inStr), outPars))
				</code>
			</phraseMaker>
		</condDesc>
	</STREAM>

	<procDef id="intervalMatcher" type="phraseMaker">
		<doc>
			A DALI-style phrase maker that matches an interval against a pair 
			of lower/upper bound columns.

			This is for using with multiplicity=mutiple inputKeys.
		</doc>
		<setup>
			<par name="loColName" description="Name of the database column
				containing the lower bound"/>
			<par name="hiColName" description="Name of the database column
				containing the upper bound"/>
		</setup>
		<code>
			name = inputKeys[0].name
			for lower, upper in inPars[name]:
				yield ("%%(%(lowerVal)s)s &lt; %(upperCol)s" 
					" AND %%(%(upperVal)s)s > %(lowerCol)s")%{
					"upperVal": base.getSQLKey(name, upper, outPars),
					"lowerVal": base.getSQLKey(name, lower, outPars),
					"upperCol": hiColName,
					"lowerCol": loColName,}
		</code>
	</procDef>

	<STREAM id="BANDpar">
		<doc>A stream defining the SIAPv2 BAND par over an obscore table.
		</doc>
		<condDesc>
			<inputKey name="BAND" type="double precision[2]" 
				multiplicity="multiple" xtype="interval"
				tablehead="Wavelength"
				description="Wavelength interval that should intersect with
					 what the dataset coverage"/>
			<phraseMaker procDef="//siap2#intervalMatcher">
				<bind key="loColName">"em_min"</bind>
				<bind key="hiColName">"em_max"</bind>
			</phraseMaker>
		</condDesc>
	</STREAM>
</resource>

