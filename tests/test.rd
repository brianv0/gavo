<?xml version="1.0" encoding="utf-8"?>

<!-- A resource descriptor for various unit tests -->

<resource resdir=".">
	<meta name="test.inRd">from Rd</meta>
	<schema>test</schema>

	<table id="siaptable" mixin="bboxSIAP" onDisk="True"/>

	<data id="siaptest">
		<dictlistGrammar>
			<rowgen predefined="defineProduct">
				<arg key="key">row["accref"]</arg>
				<arg key="fsize">row["accsize"]</arg>
				<arg key="table">"test.siaptable"</arg>
			</rowgen>
		</dictlistGrammar>
		<rowmaker id="st_siaptable">
			<proc predefined="setSIAPMeta">
				<arg key="title">imageTitle</arg>
				<arg key="instrument">instId</arg>
				<arg key="dateObs">dateObs</arg>
				<arg key="bandpassId">bandpassId</arg>
			</proc>
			<proc predefined="computeBboxSIAP"/>
		</rowmaker>
		<make table="siaptable" rowmaker="st_siaptable"/>
	</data>

	<data id="metatest">
		<table id="noname">
			<column name="alpha"
				type="double precision" required="true"/>
			<meta name="test.inRec">from Rec</meta>
		</table>
	</data>

	<table id="privtable" onDisk="True">
		<readRoles>defaults,privtestuser</readRoles>
		<allRoles>testadmin</allRoles>
		<column name="foo"/>
	</table>

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
		<column name="alpha" unit="deg" ucd="pos.eq.ra;meta.main"
			description="A sample RA" tablehead="Raw RA"/>
		<column name="delta" unit="deg" ucd="pos.eq.dec;meta.main"
			description="A sample Dec"/>
		<column name="mag" unit="mag" ucd="phot.mag"
			description="A sample magnitude"/>
		<column name="rv" unit="km/s" ucd="phys.veloc;pos.heliocentric"
			description="A sample radial velocity"/>
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
			<rowgen predefined="expandRowOnIndex">
				<arg key="startName">"b"</arg>
				<arg key="endName">"c"</arg>
				<arg key="indName">"d"</arg>
			</rowgen>
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
			<rowgen predefined="expandDateRange">
				<arg key="dest">"e"</arg>
				<arg key="start">"start"</arg>
				<arg key="end">"end"</arg>
				<arg key="hrInterval">12</arg>
			</rowgen>
		</dictlistGrammar>
		<rowmaker id="eod_abcd">
			<map dest="a"/>
			<map dest="e">e</map>
		</rowmaker>
		<make table="abcd" rowmaker="eod_abcd"/>
	</data>

	<data id="expandOnDateDefault">
		<dictlistGrammar>
			<rowgen predefined="expandDateRange">
				<arg key="start">"start"</arg>
				<arg key="end">"end"</arg>
			</rowgen>
		</dictlistGrammar>
		<rowmaker id="eodd_abcd" idmaps="a">
			<map dest="e">curTime</map>
		</rowmaker>
		<make table="abcd" rowmaker="eodd_abcd"/>
	</data>

	<data id="expandComma">
		<dictlistGrammar>
			<rowgen predefined="expandComma">
				<arg key="srcField">"stuff"</arg>
				<arg key="destField">"a"</arg>
			</rowgen>
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
			<rowgen predefined="defineProduct">
				<arg key="key">\inputRelativePath</arg>
        <arg key="owner">"test"</arg>
        <arg key="embargo">row["embargo"]</arg>
        <arg key="path">\inputRelativePath</arg>
        <arg key="fsize">\inputSize</arg>
        <arg key="table">"test.prodtest"</arg>
			</rowgen>
		</keyValueGrammar>
		<rowmaker id="pi_rmk" original="prodrowbase"/>
		<make table="prodtest" rowmaker="pi_rmk"/>
	</data>

	<data id="productimportdefaults">
		<table ref="prodtest"/>
		<sources><pattern>data/*.imp</pattern></sources>
		<keyValueGrammar>
			<rowgen predefined="defineProduct">
        <arg key="table">"test.prodtest"</arg>
			</rowgen>
		</keyValueGrammar>
		<rowmaker id="pid_rmk" original="prodrowbase"/>
		<make table="prodtest" rowmaker="pid_rmk"/>
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
