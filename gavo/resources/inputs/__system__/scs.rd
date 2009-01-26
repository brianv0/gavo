<?xml version="1.0" encoding="utf-8"?>
<!-- definition of the position-related interfaces (and later SCS fragments) -->

<resource resdir="__system" schema="public">
	<table id="q3cIndexDef">
		<index name="q3c_\tablename">
			<columns>\nameForUCD{pos.eq.ra;meta.main}, \nameForUCD{pos.eq.dec;meta.main}</columns>
			q3c_ang2ipix(\nameForUCD{pos.eq.ra;meta.main}, \nameForUCD{pos.eq.dec;meta.main})
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
		<index name="q3c_\tablename">
			<columns>\nameForUCD{pos.eq.ra;meta.main},\nameForUCD{pos.eq.dec;meta.main}</columns>
			q3c_ang2ipix(\nameForUCD{pos.eq.ra;meta.main}, \nameForUCD{pos.eq.dec;meta.main})
		</index>
	</table>

	<rowmaker id="procdef">
		<proc name="handleEquatorialPosition" isGlobal="True">
			<doc>
			is a macro that compute several derived quantities from 
			literal equatorial coordinates.

			Specifically, it generates alphaFloat, deltaFloat as well as
			c_x, c_y, c_z (cartesian coordinates of the intersection of the 
			direction vector with the unit sphere) and htmind (an HTM index
			for the position -- needs to be fleshed out a bit).

			TODO: Equinox handling (this will probably be handled through an
			optional arguments srcEquinox and destEquinox, both J2000.0 by default).
			
			Constructor arguments:

			* raFormat -- the literal format of Right Ascension.  By default,
				a sexagesimal time angle is expected.  Supported formats include
				mas (RA in milliarcsecs), ...
			* decFormat -- as raFormat, only the default is sexagesimal angle.
			* sepChar (optional) -- seperator for alpha, defaults to whitespace
			
			If alpha and delta use different seperators, you'll have to fix
			this using preprocessing macros.

			Arguments: 
			 
			* alpha -- sexagesimal right ascension as time angle
			* delta -- sexagesimal declination as dms

			>>> m = EquatorialPositionConverter([("alpha", "alphaRaw", ""),
			... ("delta", "deltaRaw", "")])
			>>> r = {"alphaRaw": "00 02 32", "deltaRaw": "+45 30.6"} 
			>>> m(None, r)
			>>> str(r["alphaFloat"]), str(r["deltaFloat"]), str(r["c_x"]), str(r["c_y"])
			('0.633333333333', '45.51', '0.700741955529', '0.00774614323406')
			>>> m = EquatorialPositionConverter([("alpha", "alphaRaw", ""),
			... ("delta", "deltaRaw", ""),], sepChar=":")
			>>> r = {"alphaRaw": "10:37:19.544070", "deltaRaw": "+35:34:20.45713"}
			>>> m(None, r)
			>>> str(r["alphaFloat"]), str(r["deltaFloat"]), str(r["c_z"])
			('159.331433625', '35.5723492028', '0.581730502028')
			>>> r = {"alphaRaw": "4:38:54", "deltaRaw": "-12:7.4"}; m(None, r)
			>>> str(r["alphaFloat"]), str(r["deltaFloat"])
			('69.725', '-12.1233333333')
			>>> m = EquatorialPositionConverter([("alpha", "alphaRaw", ""), 
			... ("delta", "deltaRaw", "")], alphaFormat="mas", deltaFormat="mas")
			>>> r = {"alphaRaw": "5457266", "deltaRaw": "-184213905"}; m(None, r)
			>>> str(r["alphaFloat"]), str(r["deltaFloat"])
			('1.51590722222', '-51.1705291667')
			</doc>
			<consComp>
				<arg key="alphaFormat" default="'hour'"/>
				<arg key="deltaFormat" default="'sexag'"/>
				<arg key="sepChar" default="None "/>
				coordComputer = {
					"hour": lambda hms: base.timeangleToDeg(hms, sepChar),
					"sexag": lambda dms: base.dmsToDeg(dms, sepChar),
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
			</consComp>
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
		</proc>
	</rowmaker>
</resource>
