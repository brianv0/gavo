<resource schema="data">
	<meta name="description">Test stuff for making direct grammars</meta>
	<table id="dgt" onDisk="True" temporary="True">
		<column name="i" type="integer" required="True"/>
		<column name="b" type="bigint" required="True"/>
		<column name="f" type="real"/>
		<column name="d" type="double precision"/>
		<column name="t" type="text"/>
	</table>

	<data id="impcol">
		<directGrammar id="col" type="col" cBooster="void.c"/>
		<make table="dgt"/>
	</data>

	<data id="impbin">
		<directGrammar id="bin" type="bin" cBooster="void.c"
			recordSize="50"/>
		<make table="dgt"/>
	</data>

	<data id="impsplit">
		<directGrammar id="split" type="split" cBooster="void.c"/>
		<make table="dgt"/>
	</data>

	<data id="impfits">
		<sources>extable.fitstable</sources>
		<directGrammar id="fits" type="fits" cBooster="tmp.c"/>
		<make table="dgt"/>
	</data>

</resource>
