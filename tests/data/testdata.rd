<resource schema="__test">
	<meta name="description">Some test data with a reasonable funny structure.
	</meta>
	<meta name="title">GAVO Test Data</meta>
	<meta name="creationDate">2008-10-15T15:01:03</meta>
	<meta name="subject">Testing</meta>


	<table id="data">
		<column name="anint" tablehead="An Integer" type="integer"/>
		<column name="afloat" tablehead="Some Real"/>
		<column name="atext" type="text"
			tablehead="A string must be in here as well"/>
		<column name="adate" tablehead="When" type="date"/>
	</table>
	
	<table id="barsobal">
		<column name="anint" type="integer"/>
		<column name="adouble" tablehead="And a Double"
			type="double precision"/>
	</table>

	<data id="twotables">
		<dictlistGrammar/>
		<make table="data" role="primary"/>
		<make table="barsobal"/>
	</data>

	<table id="nork">
		<column name="cho" type="text">
			<values><option>a</option><option>b</option></values>
		</column>
	</table>

	<data id="ronk">
		<register services="//services#overview" sets="ignore"/>
		<make table="barsobal"/>
	</data>

</resource>
