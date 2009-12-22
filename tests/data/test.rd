<?xml version="1.0" encoding="utf-8"?>

<!-- A resource descriptor for various unit tests -->

<resource resdir=".">
	<meta name="test.inRd">from Rd</meta>
	<schema>test</schema>

	<table id="bbox_siaptable" mixin="bboxSIAP" onDisk="True"/>
	<table id="pgs_siaptable" mixin="pgsSIAP" onDisk="True"/>

	<data id="siap_base" auto="False">
		<dictlistGrammar>
			<rowfilter predefined="defineProduct">
				<bind key="key">row["accref"]</bind>
				<bind key="fsize">row["accsize"]</bind>
				<bind key="table">parent.parent.getProperty("destTable")</bind>
				<bind key="path">row["accref"]</bind>
			</rowfilter>
		</dictlistGrammar>
		<rowmaker id="st_siaptable">
			<apply predefined="setSIAPMeta">
				<bind key="title">vars["imageTitle"]</bind>
				<bind key="instrument">vars["instId"]</bind>
				<bind key="dateObs">vars["dateObs"]</bind>
				<bind key="bandpassId">vars["bandpassId"]</bind>
			</apply>
		</rowmaker>
	</data>

	<data id="bbox_siaptest" original="siap_base">
		<!-- for bbox-based searching -->
		<property name="destTable">test.bbox_siaptable</property>
		<rowmaker id="make_bboxsiaptable" original="st_siaptable">
			<apply predefined="computeBboxSIAP"/>
		</rowmaker>
		<make table="bbox_siaptable" rowmaker="make_bboxsiaptable" 
			role="primary"/>
	</data>

	<data id="pgs_siaptest" original="siap_base">
		<!-- for pgsphere-based searching -->
		<property name="destTable">test.pgs_siaptable</property>
		<rowmaker id="make_pgssiaptable" original="st_siaptable">
			<apply predefined="computePGSSIAP"/>
		</rowmaker>
		<make table="pgs_siaptable" rowmaker="make_pgssiaptable"
			role="primary"/>
	</data>

	<data id="metatest">
		<table id="noname">
			<column name="alpha"
				type="double precision" required="true"/>
			<meta name="test.inRec">from Rec</meta>
		</table>
	</data>

	<table id="adqltable" onDisk="True" adql="True">
		<column name="foo"
			type="double precision" required="True"/>
	</table>

	<table id="typestable" onDisk="True">
		<column name="anint" tablehead="An Integer" type="integer"/>
		<column name="afloat" tablehead="Some Real"/>
		<column name="adouble" tablehead="And a Double"
			type="double precision"/>
		<column name="atext" type="text"
			tablehead="A string must be in here as well"/>
		<column name="adate" tablehead="When" type="date"/>
	</table>

	<data id="tableMaker">
		<table original="typestable" id="m_typestable" onDisk="False"/>
		<rowsetGrammar enc="iso8859-1" fieldsFrom="m_typestable"/>
		<rowmaker id="tm_m_typestable" idmaps="anint,afloat,adouble,atext,adate"/>
		<make table="m_typestable" rowmaker="tm_m_typestable"/>
	</data>


	<table id="adql" adql="True" onDisk="True">
		<stc>
			Position ICRS GEOCENTER "alpha" "delta" Redshift VELOCITY "rv"
		</stc>
		<column name="alpha" unit="deg" ucd="pos.eq.ra;meta.main"
			description="A sample RA" tablehead="Raw RA"/>
		<column name="delta" unit="deg" ucd="pos.eq.dec;meta.main"
			description="A sample Dec"/>
		<column name="mag" unit="mag" ucd="phot.mag"
			description="A sample magnitude"/>
		<column name="rv" unit="km/s" ucd="phys.veloc;pos.heliocentric"
			description="A sample radial velocity"
			type="double precision"/>
	</table>

	<data id="ADQLTest">
		<rowmaker id="AT_adql" idmaps="alpha,delta,mag,rv"/>
		<dictlistGrammar/>
		<make table="adql" rowmaker="AT_adql"/>
	</data>

	<table id="valspec" onDisk="True">
		<column name="numeric" required="True">
			<values min="10" max="15"/>
		</column>
		<column name="enum" type="text">
			<values>
				<option>abysimal</option>
				<option>horrific</option>
				<option>gruesome</option>
				<option>bad</option>
				<option>acceptable</option>
			</values>
		</column>
	</table>


	<data id="valuestest">
		<table id="valuesdoc">
			<column name="docLowBound">
				<values min="-10"/>
			</column>
			<column name="docHiBound">
				<values max="-10"/>
			</column>
			<column name="docReq" required="True" type="text"/>
		</table>
		<make table="valspec"/>
		<make table="valuesdoc" role="docrec"/>
	</data>

	<table id="misctypes" onDisk="True">
		<column name="box" type="box"/>
	</table>

	<data id="boxTest">
	 	<dictlistGrammar/>
		<rowmaker id="bT_misctypes">
			<map dest="box">box</map>
		</rowmaker>
		<make table="misctypes" rowmaker="bT_misctypes"/>
	</data>


	<data id="viziertest">
		<dictlistGrammar/>
		<table id="vizierstrings" onDisk="true">
			<column name="s" type="text"/>
		</table>
		<make table="vizierstrings"/>
	</data>


	<table id="abcd">
		<column name="a" type="text" verbLevel="1"/>
		<column name="b" type="integer" verbLevel="5"/>
		<column name="c" type="integer" verbLevel="15"/>
		<column name="d" type="integer" verbLevel="20" unit="km"/>
		<column name="e" type="timestamp" verbLevel="25"/>
	</table>

	<data id="expandOnIndex">
		<dictlistGrammar>
			<rowfilter predefined="expandIntegers">
				<bind key="startName">"b"</bind>
				<bind key="endName">"c"</bind>
				<bind key="indName">"d"</bind>
			</rowfilter>
		</dictlistGrammar>
		<rowmaker id="eoi_abcd">
			<map dest="a"/>
			<map dest="b"/>
			<map dest="c"/>
			<map dest="d"/>
		</rowmaker>
		<make table="abcd" rowmaker="eoi_abcd"/>
	</data> 

	<data id="expandOnDate">
		<dictlistGrammar>
			<rowfilter procDef="__system__/procs#expandDates">
				<bind key="dest">"e"</bind>
				<bind key="start">"start"</bind>
				<bind key="end">"end"</bind>
				<bind key="hrInterval">12</bind>
			</rowfilter>
		</dictlistGrammar>
		<rowmaker id="eod_abcd">
			<map dest="a"/>
			<map dest="e">e</map>
		</rowmaker>
		<make table="abcd" rowmaker="eod_abcd"/>
	</data>

	<data id="expandOnDateDefault">
		<dictlistGrammar>
			<rowfilter procDef="__system__/procs#expandDates">
				<bind key="start">"start"</bind>
				<bind key="end">"end"</bind>
			</rowfilter>
		</dictlistGrammar>
		<rowmaker id="eodd_abcd" idmaps="a">
			<map dest="e">curTime</map>
		</rowmaker>
		<make table="abcd" rowmaker="eodd_abcd"/>
	</data>

	<data id="expandComma">
		<dictlistGrammar>
			<rowfilter procDef="__system__/procs#expandComma">
				<bind key="srcField">"stuff"</bind>
				<bind key="destField">"a"</bind>
			</rowfilter>
		</dictlistGrammar>
		<rowmaker id="ec_abcd">
			<map dest="a"/>
			<map dest="b"/>
		</rowmaker>
		<make table="abcd" rowmaker="ec_abcd"/>
	</data>

	<table id="prodtest" mixin="products" onDisk="True">
		<column name="object" type="text" verbLevel="1"/>
		<column name="alpha" type="real" ucd="pos.eq.ra" verbLevel="15"/>
		<column name="delta" type="real" ucd="pos.eq.dec" verbLevel="15"/>
	</table>

	<table id="stcfancy">
		<stc>Position ICRS BARYCENTER "ra" "dec" Error "e_pos" "e_pos"</stc>
		<stc>Time TT TOPOCENTER "obsDate" Error "e_date"
			Position FK5 B1975 TOPOCENTER "o_ra" "o_dec" VelocityInterval
			Velocity "pma" "pmd" Error "e_pma" "e_pmd"</stc>
		<GENERATOR>
		for name in ["ra", "dec", "e_pos", "obsDate", "e_date", "o_ra", 
				"o_dec", "pma", "pmd", "e_pma", "e_pmd"]:
			yield ("element", "column", ("name", name))
		</GENERATOR>
	</table>

	<rowmaker id="prodrowbase">
		<map dest="object"/>
		<map dest="alpha" src="hmsToDeg(alpha, ' ')"/>
		<map dest="delta" src="dmsToDeg(delta, ' ')"/>
	</rowmaker>

	<data id="productimport">
		<!-- Sources are in tests/data, so you need to fix inputsDir to
		./tests to import this -->
		<sources><pattern>data/*.imp</pattern></sources>
		<keyValueGrammar>
			<rowfilter predefined="defineProduct">
        <bind key="owner">"test"</bind>
        <bind key="embargo">row["embargo"]</bind>
        <bind key="table">"test.prodtest"</bind>
			</rowfilter>
		</keyValueGrammar>
		<rowmaker id="pi_rmk" original="prodrowbase"/>
		<make table="prodtest" rowmaker="pi_rmk"/>
	</data>

	<data id="productimportdefaults">
		<table ref="prodtest"/>
		<sources><pattern>data/*.imp</pattern></sources>
		<keyValueGrammar>
			<rowfilter predefined="defineProduct">
        <bind key="table">"test.prodtest"</bind>
			</rowfilter>
		</keyValueGrammar>
		<rowmaker id="pid_rmk" original="prodrowbase"/>
		<make table="prodtest" rowmaker="pid_rmk"/>
	</data>

	<table id="sqlscript" onDisk="True">
		<column name="counter" type="integer"/>
		<script type="preIndexSQL">
			INSERT INTO \curtable VALUES (1)
			INSERT INTO \curtable VALUES (2)
			INSERT INTO \curtable VALUES (3)
		</script>
	</table>

	<data id="import_sqlscript">
		<make table="sqlscript"/>
	</data>

	<table id="pythonscript" onDisk="True">
		<column name="counter" type="integer"/>
		<script type="preIndex">
			tw.query("INSERT INTO \curtable VALUES (123)")
		</script>
	</table>

	<data id="import_pythonscript">
		<make table="pythonscript"/>
	</data>

	<dbCore id="prodscore" queriedTable="prodtest"/>

	<service id="basicprod" core="prodscore"/>

	<computedCore id="abccatcore" computer="/bin/cat">
		<inputDD>
			<table id="abc_cmd"/>
			<rowmaker id="mapthrough" idmaps="*"/>
			<make table="abc_cmd" role="parameters"/>
			<make table="abcd" role="inputLine" rowmaker="mapthrough"/>
		</inputDD>
		<outputTable id="abcdOut" original="abcd"/>
		<data>
			<reGrammar recordSep="&#10;" fieldSep="\s+">
				<names>a,b,c,d,e</names>
			</reGrammar>
			<rowmaker id="acc_abcd">
				<idmaps>a,b,c,d,e</idmaps>
			</rowmaker>
			<make table="abcd" rowmaker="acc_abcd"/>
		</data>
	</computedCore>

	<service id="basiccat" core="abccatcore"/>

	<service id="convcat" core="abccatcore">
		<outputTable namePath="abcd">
			<column original="a" verbLevel="15"/>
			<column original="b" displayHint="sf=2"/>
			<column original="d" unit="m"/>
		</outputTable>
	</service>
</resource>
