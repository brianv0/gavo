<?xml version="1.0" encoding="utf-8"?>
<!-- definition of the position-related interfaces (and later SCS fragments) -->

<resource resdir="__system" schema="public">
	<table id="q3cIndexDef">
		<index name="q3c_\tablename" cluster="True">
			<columns>\nameForUCDs{pos.eq.ra;meta.main|POS_EQ_RA_MAIN}, \nameForUCDs{pos.eq.dec;meta.main|POS_EQ_DEC_MAIN}</columns>
			q3c_ang2ipix(\nameForUCDs{pos.eq.ra;meta.main|POS_EQ_RA_MAIN}, \nameForUCDs{pos.eq.dec;meta.main|POS_EQ_DEC_MAIN})
		</index>
	</table>

	<table id="positionsFields">
		<!-- fill these using the handleEquatorialPosition macro defined below;
		no rowmakers required. -->
		<column name="alphaFloat" unit="deg" type="double precision" 
			ucd="pos.eq.ra;meta.main" verbLevel="1"
			tablehead="RA" description="Main value of right ascension"/>
		<column name="deltaFloat" unit="deg" type="double precision" 
			ucd="pos.eq.dec;meta.main" verbLevel="1"
			tablehead="Dec" description="Main value of declination"/>
		<column name="c_x" type="real" verbLevel="30"
			tablehead="c_x" unit="" ucd="pos.cartesian.x" description=
				"x coordinate of intersection of radius vector and unit sphere"/>
		<column name="c_y" type="real" verbLevel="30"
			tablehead="c_y" unit="" ucd="pos.cartesian.y" description=
				"y coordinate of intersection of radius vector and unit sphere"/>
		<column name="c_z" type="real" verbLevel="30" tablehead="c_z" 
			unit="" ucd="pos.cartesian.z" description=
			"z coordinate of intersection of radius vector and unit sphere"/>
	</table>

	<table id="q3cPositionsFields" original="positionsFields">
		<!-- positions with q3c index -->
		<!-- XXX TODO: once we have replay or similar, get this from q3cindexdef -->
		<index name="q3c_\tablename" cluster="True">
			<columns>\nameForUCDs{pos.eq.ra;meta.main|POS_EQ_RA_MAIN},\nameForUCDs{pos.eq.dec;meta.main|POS_EQ_DEC_MAIN}</columns>
			q3c_ang2ipix(\nameForUCDs{pos.eq.ra;meta.main|POS_EQ_RA_MAIN},\nameForUCDs{pos.eq.dec;meta.main|POS_EQ_DEC_MAIN})
		</index>
	</table>

	<procDef id="handleEquatorialPosition" register="True">
		<doc>
			is a macro that compute several derived quantities from 
			literal equatorial coordinates.

			Specifically, it generates alphaFloat, deltaFloat as well as
			c_x, c_y, c_z (cartesian coordinates of the intersection of the 
			direction vector with the unit sphere).

			TODO: Equinox handling (this will probably be handled through an
			optional arguments srcEquinox and destEquinox, both J2000.0 by default).
			
			Setup pars:

			* raFormat -- the literal format of Right Ascension.  By default,
				a sexagesimal time angle is expected.  Supported formats include
				mas (RA in milliarcsecs), ...
			* decFormat -- as raFormat, only the default is sexagesimal angle.
			* sepChar (optional) -- seperator for alpha, defaults to whitespace
			* alphaKey, deltaKey -- keys to take alpha and delta from.
			
			If alpha and delta use different seperators, you'll have to fix
			this using preprocessing macros.
		</doc>
		<setup>
			<par key="alphaFormat">'hour'</par>
			<par key="deltaFormat">'sexag'</par>
			<par key="alphaKey">'alpha'</par>
			<par key="deltaKey">'delta'</par>
			<par key="sepChar">None</par>
			<code>
				coordComputer = {
					"hour": lambda hms: utils.hmsToDeg(hms, sepChar),
					"sexag": lambda dms: utils.dmsToDeg(dms, sepChar),
					"mas": lambda mas: float(mas)/3.6e6,
					"binary": lambda a: a,
				}
				def convertCoo(literalForm, literal):
					return coordComputer[literalForm](literal)
				def computeCoos(alpha, delta):
					alphaFloat = convertCoo(alphaFormat, alpha)
					deltaFloat = convertCoo(deltaFormat, delta)
					return (alphaFloat, deltaFloat)+tuple(
						coords.computeUnitSphereCoords(alphaFloat, deltaFloat))
				return locals()
			</code>
		</setup>
		<code>
			alpha, delta = vars["alphaKey"], vars["deltaKey"]
			if alpha is None or delta is None:
				alphaFloat, deltaFloat, c_x, c_y, c_z = [None]*5
			else:
				alphaFloat, deltaFloat, c_x, c_y, c_z = computeCoos(
					alpha, delta)
			result["alphaFloat"] = alphaFloat
			result["deltaFloat"] = deltaFloat
			result["c_x"] = c_x
			result["c_y"] = c_y
			result["c_z"] = c_z
		</code>
	</procDef>
</resource>
