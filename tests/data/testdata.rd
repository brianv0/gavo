<resource schema="__test">
	<meta name="description">Some test data with a reasonable funny structure.
	</meta>

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
</resource>
