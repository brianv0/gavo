<resource schema="data">
	<meta name="description">Test stuff for making direct grammars</meta>
	<table id="dgt" onDisk="True" temporary="True">
		<column name="i" type="integer" required="True"/>
		<column name="b" type="bigint" required="True"/>
		<column name="f" type="real"/>
		<column name="d" type="double precision"/>
		<column name="t" type="text"/>
		<column name="l" type="smallint"/>
	</table>

	<table id="dgtplus" onDisk="True" original="dgt">
		<column name="artificial" description="artificial column"
			type="text"/>
	</table>
	
	<table id="dgtonecol" onDisk="True" temporary="True">
		<column name="b" type="bigint" required="True"/>
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
		<directGrammar id="fits" type="fits" cBooster="tmp.c">
			<mapKeys>t:text</mapKeys>
		</directGrammar>
		<make table="dgtplus"/>
	</data>

	<data id="impfits2nd">
		<sources>extable.fitstable</sources>
		<directGrammar id="fits2nd" type="fits" cBooster="tmp.c"
				extension="2">
		</directGrammar>
		<make table="dgtonecol"/>
	</data>

	<data id="impfitsplus">
		<sources>extable.fitstable</sources>
		<directGrammar id="fitsplus" type="fits" cBooster="tmp.c">
			<mapKeys>t:text</mapKeys>
		</directGrammar>
		<make table="dgtplus"/>
	</data>

</resource>
