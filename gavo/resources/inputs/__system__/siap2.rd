<!-- definitions related to supporting SIAPv2; the underlying table is 
obscore and defined using the means given there. -->

<resource resdir="__system" schema="dc">
	<STREAM id="POSpar">
		<doc>A stream defining a SIAPv2-style POS par over an obscore table.

		You can pass the name of a pgsphere geometry in the geom_name macro.
		The default is set up for ivoa.obscore.
		</doc>
		<DEFAULTS geom_name="s_region"/>
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
						yield '\geom_name &amp;&amp;%%(%s)s'%(
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


	<procDef id="intervalConstraint" type="phraseMaker">
		<doc>
			A DALI-style phrase maker that matches an input interval against a 
			a single value in the database.

			This is for using with multiplicity=mutiple inputKeys.
		</doc>
		<setup>
			<par name="colName" description="Name of the database column
				containing the value constrained."/>
		</setup>
		<code>
			name = inputKeys[0].name
			for lower, upper in inPars[name]:
				yield ("%(colName)s BETWEEN"
					" %%(%(lowerVal)s)s AND %%(%(upperVal)s)s"%{
					"upperVal": base.getSQLKey(name, upper, outPars),
					"lowerVal": base.getSQLKey(name, lower, outPars),
					"colName": colName }
		</code>
	</procDef>


	<procDef id="equalityConstraint" type="phraseMaker">
		<doc>
			A DALI-style phrase maker that matches an input literally.

			This is for using with multiplicity=mutiple inputKeys.
		</doc>
		<setup>
			<par name="colName" description="Name of the database column
				containing the value constrained."/>
		</setup>
		<code>
			name = inputKeys[0].name
			yield ("%(colName)s in %%(%(key)s)s"%{
				"key": inPars[name]}
		</code>
	</procDef>


	<STREAM id="BANDpar">
		<doc>A stream defining the SIAPv2 BAND par over an obscore-like table.

		For non-obscore use, you can the min/max column names in the 
		min_name and max_name macros.
		</doc>
		<DEFAULTS min_name="em_min" max_name="em_max"/>
		<condDesc>
			<inputKey name="BAND" type="double precision[2]" 
				multiplicity="multiple" xtype="interval"
				tablehead="Wavelength"
				description="Wavelength interval that should intersect with
					 the dataset coverage"/>
			<phraseMaker procDef="//siap2#intervalMatcher">
				<bind key="loColName">"\min_name"</bind>
				<bind key="hiColName">"\max_name"</bind>
			</phraseMaker>
		</condDesc>
	</STREAM>

	<STREAM id="TIMEpar">
		<doc>A stream defining the SIAPv2 TIME par over an obscore-like table.

		For non-obscore use, you can the min/max column names in the 
		min_name and max_name macros.
		</doc>
		<DEFAULTS min_name="t_min" _max_name="t_max"/>
		<condDesc>
			<inputKey name="TIME" type="double precision[2]" 
				multiplicity="multiple" xtype="interval"
				tablehead="Time"
				description="Time interval that should intersect with
					 the dataset coverage"/>
			<phraseMaker procDef="//siap2#intervalMatcher">
				<bind key="loColName">"\min_name"</bind>
				<bind key="hiColName">"\max_name"</bind>
			</phraseMaker>
		</condDesc>
	</STREAM>

	<STREAM id="POLpar">
		<doc>A stream defining the SIAPv2 POL par over an obscore-like table
		(i.e., one with pol_states).

		This can have multiple values, and the pol_states in obscore can have
		multiple states.  Hence, we need a somewhat tricky phrase maker.
		</doc>
		<DEFAULTS min_name="t_min" _max_name="t_max"/>
		<condDesc>
			<inputKey name="POL" type="text" 
				multiplicity="multiple" 
				tablehead="Polarisation"
				description="Polarisation states as per Obscore (i.e., from
					the set I Q U V RR LL RL LR XX YY XY YX POLI POLA"/>
			<phraseMaker>
				<code>
					name = inputKeys[0].name
					for val in inPars[name]:
						yield 'pol_states LIKE %%(%s)s'%(
							base.getSQLKey(name, "%%/%s/%%"%val, outPars))
				</code>
			</phraseMaker>
		</condDesc>
	</STREAM>


	<LOOP>
		<csvItems>
parName, colName,    tablehead,     unit, description
FOV,     s_fov,      Field of View, deg,  the field of view of the observation
SPATRES, s_resolution, Spat. Res.,  deg,  the spatial resolution of the image(s)
SPECRP,  em_res_powr,Res. Power,    ,     the spectral resolving power λ/Δλ in spectrally resolved observations
EXPTIME, t_exptime,  Exposure Time, s,    the integration times of the observation
TIMERES, t_resolution,Time res.,    s,    the (absolute) resolution on the time axis
		</csvItems>
		<events>
			<STREAM id="\parName\+par">
				<doc>A stream defining the SIAPv2 \parName parameter over an 
				obscore-like table (i.e., one with \colName).

				For non-obscore use, you can override the colName macro to use
				another column than \colName.
				</doc>
				<DEFAULTS colName="\colName"/>
				<condDesc>
					<inputKey name="\parName" type="real[2]" xtype="interval"
						unit="\unit"
						multiplicity="multiple" 
						tablehead="\tablehead"
						description="Lower and upper bound for \description"/>
					<phraseMaker procDef="//siap2#intervalConstraint">
						<bind key="colName">"\\colName"</bind>
					</phraseMaker>
				</condDesc>
			</STREAM>
		</events>
	</LOOP>


	<LOOP>
		<csvItems>
parName,    colName,           tablehead,  type, description
ID,         obs_publisher_did, DID,        text, "A dataset identifier to match.  Note that contrary to the SIAP v2 REC, we do not compare the IVOIDs case-insensitively.  This should not be an issue if you got the IVOID from this service.  For IVOIDs obtained in other ways, you may need to use ILIKE or a similar facility through ObsTAP."
COLLECTION, obs_collection,    Collection, text, A name of a data collection within the service (use ObsTAP to find out the possible values).
FACILITY,   facility_name,     Facility,   text, A name of a facility (usually a telescope) used to make the observation.
INSTRUMENT, instrument_name,   Instrument, text, A name of an instrument used to acquire the data.
DPTYPE,     dataproduct_type,  Type,       text, Select either image or cube.
CALIB,      calib_level,       Calib. Level,smallint, "Calibration level of the data (0=raw data .. 3=processed science-ready data)"
TARGET,     target_name,       Target,     text, A name  of an observation target.
FORMAT,     access_format,     Format,     text, Media type (like image/fits) or similar of the data product searched
		</csvItems>
		<events>
			<STREAM id="\parName\+par">
				<doc>A stream defining the SIAPv2 \parName parameter over an 
				obscore-like table (i.e., one with \colName).
				</doc>
				<DEFAULTS colName="\colName"/>
				<condDesc>
					<inputKey name="\parName" type="\type"
						multiplicity="multiple" 
						tablehead="\tablehead"
						description="\description"/>
						<phraseMaker procDef="//siap2#equalityConstraint">
							<bind key="colName">"\\colName"</bind>
						</phraseMaker>
				</condDesc>
			</STREAM>
		</events>
	</LOOP>
</resource>

