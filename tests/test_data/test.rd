<?xml version="1.0" encoding="utf-8"?>

<!-- A resource descriptor for various unit tests -->

<resource resdir=".">
	<meta name="test.inRd">from Rd</meta>
	<meta name="copyright">Everything in here is pure fantasy 
	(distributed under the GNU GPL)</meta>
	<meta name="creator.name">John C. Testwriter</meta>
	<schema>test</schema>

	<table id="bbox_siaptable" mixin="//siap#bbox" onDisk="True"/>
	<table id="pgs_siaptable" mixin="//siap#pgs" onDisk="True"/>

	<service id="pgsiapsvc">
		<publish render="siap.xml" sets="testing"/>
		<meta name="title">siap test</meta>
		<meta name="creationDate">2005-01-01T12:00:00</meta>
		<meta name="subject">testing</meta>
		<meta name="shortName">oh bother</meta>
		<meta name="description">If you are seeing this service, a unit test
			forgot to clean up.</meta>

		<meta name="sia">
			<meta name="type">pointed</meta>
			<meta name="maxImageSize">3000</meta>
			<meta name="maxImageExtent.long">10</meta>
		</meta>
		<meta>
			testQuery.pos.ra: 10
			testQuery.pos.dec: -10
			testQuery.size.ra: 0.4 
			testQuery.size.dec: 0.3 
		</meta>
		<dbCore queriedTable="pgs_siaptable">
			<condDesc original="//siap#protoInput"/>
			<condDesc original="//siap#humanInput"/>
		</dbCore>
	</service>

	<data id="siap_base" auto="False">
		<dictlistGrammar>
			<rowfilter procDef="//products#define">
				<bind key="accref">row["accref"]</bind>
				<bind key="fsize">row["accsize"]</bind>
				<bind key="table">parent.parent.getProperty("destTable")</bind>
				<bind key="path">row["accref"]</bind>
			</rowfilter>
		</dictlistGrammar>
		<rowmaker id="st_siaptable">
			<apply procDef="//siap#setMeta">
				<bind key="title">@imageTitle</bind>
				<bind key="instrument">@instId</bind>
				<bind key="dateObs">@dateObs</bind>
				<bind key="bandpassId">@bandpassId</bind>
			</apply>
		</rowmaker>
	</data>

	<data id="bbox_siaptest" original="siap_base">
		<!-- for bbox-based searching -->
		<property name="destTable">test.bbox_siaptable</property>
		<rowmaker id="make_bboxsiaptable" original="st_siaptable">
			<apply procDef="//siap#computeBbox"/>
		</rowmaker>
		<make table="bbox_siaptable" rowmaker="make_bboxsiaptable" 
			role="primary"/>
	</data>

	<data id="pgs_siaptest" original="siap_base">
		<!-- for pgsphere-based searching -->
		<property name="destTable">test.pgs_siaptable</property>
		<rowmaker id="make_pgssiaptable" original="st_siaptable">
			<apply procDef="//siap#computePGS"/>
		</rowmaker>
		<make table="pgs_siaptable" rowmaker="make_pgssiaptable"
			role="primary"/>
	</data>

	<data id="pgs_siapnulltest" original="siap_base">
		<!-- for pgsphere import with null data -->
		<property name="destTable">test.pgs_siaptable</property>
		<rowmaker id="make_pgssiaptable" original="st_siaptable">
			<apply procDef="//siap#computePGS">
				<bind name="missingIsError">False</bind>
			</apply>
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
		<meta name="description">A meaningless table</meta>
		<column name="foo"
			type="double precision" required="True"/>
	</table>

	<table id="typesTable" onDisk="True">
		<column name="anint" tablehead="An Integer" type="integer">
			<values nullLiteral="-8888"/></column>
		<column name="afloat" tablehead="Some Real"/>
		<column name="adouble" tablehead="And a Double"
			type="double precision"/>
		<column name="atext" type="text"
			tablehead="A string must be in here as well"/>
		<column name="adate" tablehead="When" type="date"/>
	</table>

	<data id="tableMaker">
		<table original="typesTable" id="m_typestable" onDisk="False"/>
		<rowsetGrammar enc="iso8859-1" fieldsFrom="m_typestable"/>
		<rowmaker id="tm_m_typestable" idmaps="anint,afloat,adouble,atext,adate"/>
		<make table="m_typestable" rowmaker="tm_m_typestable"/>
	</data>


	<table id="adql" adql="True" onDisk="True">
		<meta name="source">1635QB41.G135......</meta>
		<stc>
			Position ICRS GEOCENTER "alpha" "delta" Redshift VELOCITY "rV"
		</stc>
		<group name="weird_columns" utype="col:weird.name">
			<columnRef dest="alpha" utype="col:weird.reason"/>
			<columnRef dest="mag"/>
		</group>
		<group name="nice_columns" utype="col:nice.name">
			<columnRef dest="alpha"/>
			<columnRef dest="rV"/>
		</group>
		<column name="alpha" unit="deg" ucd="pos.eq.ra;meta.main"
			description="A sample RA" tablehead="Raw RA" verbLevel="1"/>
		<column name="delta" unit="deg" ucd="pos.eq.dec;meta.main"
			description="A sample Dec" verbLevel="1"/>
		<column name="mag" unit="mag" ucd="phot.mag"
			description="A sample magnitude" verbLevel="15"/>
		<column name="rV" unit="km/s" ucd="phys.veloc;pos.heliocentric"
			description="A sample radial velocity"
			type="double precision" verbLevel="25"/>
		<column name="tinyflag" type="bytea" verbLevel="30">
			<values nullLiteral="0"/>
		</column>
	</table>

	<data id="ADQLTest">
		<rowmaker id="AT_adql" idmaps="alpha,delta,mag,rV,tinyflag"/>
		<dictlistGrammar/>
		<make table="adql" rowmaker="AT_adql"/>
	</data>

	<data id="csTestTable">
		<sources pattern="data/cstestin.txt"/>
		<reGrammar names="alpha,delta,mag,rv"/>
		<make table="adql"/>
	</data>

	<table id="valSpec" onDisk="True">
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
		<make table="valSpec"/>
		<make table="valuesdoc" role="docrec"/>
	</data>

	<table id="misctypes" onDisk="True">
		<column name="box" type="box"/>
	</table>

	<data id="viziertest">
		<dictlistGrammar/>
		<table id="vizierstrings" onDisk="true">
			<column name="s" type="text"/>
		</table>
		<make table="vizierstrings"/>
	</data>


	<table id="abcd">
		<column name="a" type="text" verbLevel="1"/>
		<column name="b" type="integer" verbLevel="5">
			<values nullLiteral="-8888"/>
		</column>
		<column name="c" type="integer" verbLevel="15">
			<values nullLiteral="-8888"/>
		</column>
		<column name="d" type="integer" verbLevel="20" unit="km">
			<values nullLiteral="-8888"/>
		</column>
		<column name="e" type="timestamp" verbLevel="25"/>
	</table>

	<data id="expandOnIndex">
		<dictlistGrammar>
			<rowfilter procDef="//procs#expandIntegers">
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
			<map dest="e">@e</map>
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
			<map dest="e">@curTime</map>
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

	<table id="prodtest" mixin="//products#table" onDisk="True">
		<column name="object" type="text" verbLevel="1"/>
		<column name="alpha" type="real" ucd="pos.eq.ra" verbLevel="15"/>
		<column name="delta" type="real" ucd="pos.eq.dec" verbLevel="15"/>
	</table>

	<table id="stcfancy">
		<stc>Position ICRS BARYCENTER "ra" "dec" Error "e_pos" "e_pos"</stc>
		<stc>Time TT TOPOCENTER "obsDate" Error "e_date"
			Position FK5 B1975 TOPOCENTER "o_ra" "o_dec" VelocityInterval
			Velocity "pma" "pmd" Error "e_pma" "e_pmd"</stc>
		<LOOP listItems="ra dec e_pos obsDate e_date o_ra o_dec
				pma pmd e_pma e_pmd">
			<events>
				<column name="\item"/>
			</events>
		</LOOP>
	</table>

	<rowmaker id="prodrowbase">
		<map dest="object"/>
		<map dest="alpha">hmsToDeg(@alpha, ' ')</map>
		<map dest="delta">dmsToDeg(@delta, ' ')</map>
	</rowmaker>

	<data id="productimport">
		<sources><pattern>data/*.imp</pattern></sources>
		<keyValueGrammar id="pi-gram">
			<rowfilter procDef="//products#define">
        <bind key="owner">"X_test"</bind>
        <bind key="embargo">row["embargo"]</bind>
        <bind key="table">"test.prodtest"</bind>
        <bind key="mime">"text/plain"</bind>
			</rowfilter>
		</keyValueGrammar>
		<rowmaker id="pi_rmk" original="prodrowbase"/>
		<make table="prodtest" rowmaker="pi_rmk"/>
	</data>

	<data id="productimport-skip">
		<sources><pattern>data/[ab].imp</pattern></sources>
		<keyValueGrammar>
			<rowfilter procDef="//products#define">
     		<bind key="table">"test.prodskip"</bind>
     	</rowfilter>
		</keyValueGrammar>
		<make>
			<table id="prodskip" onDisk="True" mixin="//products#table">
				<column name="object" type="text"/>
			</table>
			<rowmaker id="pi_rmk" idmaps="*">
				<ignoreOn><keyIs key="object" value="michael"/></ignoreOn>
			</rowmaker>
		</make>
	</data>

	<data id="productimportdefaults">
		<table original="prodtest" onDisk="True" id="proddefaults"/>
		<sources><pattern>data/*.imp</pattern></sources>
		<keyValueGrammar>
			<rowfilter procDef="//products#define">
        <bind key="table">"test.prodtest"</bind>
			</rowfilter>
		</keyValueGrammar>
		<make table="prodtest">
			<rowmaker original="prodrowbase"/>
		</make>
	</data>

	<data id="import_fitsprod">
		<sources pattern="data/*.fits"/>
		<fitsProdGrammar>
			<rowfilter procDef="//products#define">
        <bind key="table">"test.prodtest"</bind>
			</rowfilter>
		</fitsProdGrammar>
		<make table="prodtest" role="primary">
			<rowmaker simplemaps="alpha:CRVAL1, delta:CRVAL2, object:OBJECT"
				idmaps="*"/>
		</make>
	</data>

	<table id="sqlscript" onDisk="True">
		<column name="counter" type="integer" required="True"/>
	</table>

	<data id="import_sqlscript">
		<make table="sqlscript">
			<script type="preIndex" lang="SQL">
				INSERT INTO \curtable VALUES (1);
				INSERT INTO \curtable VALUES (2);
				INSERT INTO \curtable VALUES (3)
			</script>
		</make>
	</data>

	<table id="pythonscript" onDisk="True">
		<column name="counter" type="integer" required="True"/>
	</table>

	<data id="import_pythonscript">
		<make table="pythonscript">
			<script type="preIndex" lang="python">
				table.query("INSERT INTO \curtable VALUES (123)")
			</script>
		</make>
	</data>

	<data id="recaftertest" recreateAfter="import_pythonscript"/>

	<dbCore id="prodscore" queriedTable="prodtest"/>

	<service id="basicprod" core="prodscore">
		<meta name="title">Somebody else's problem</meta>
		<meta name="creationDate">1975-01-01T12:00:00</meta>
		<meta name="subject">Problems, somebody else's</meta>
		<meta name="shortName">no looks</meta>
		<meta name="description">If you are seeing this service, a unit test
			forgot to clean up.</meta>
		<property name="indexFile">index.html</property>
		<publish render="form" sets="local"/>
	</service>

</resource>
