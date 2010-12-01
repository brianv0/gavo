<resource resdir="." schema="test">
	<meta name="description">Helpers for tests for cores.</meta>
	<table id="abcd">
		<column name="a" type="text" verbLevel="1"/>
		<column name="b" type="integer" verbLevel="5"/>
		<column name="c" type="integer" verbLevel="15"/>
		<column name="d" type="integer" verbLevel="20" unit="km"/>
		<column name="e" type="timestamp" verbLevel="25"/>
	</table>

	<computedCore id="abccatcore" computer="/bin/cat">
		<inputTable original="abcd"/>
		<data>
			<reGrammar recordSep="&#10;" fieldSep="\s+">
				<names>a,b,c,d,e</names>
			</reGrammar>
			<make table="abcd">
				<rowmaker idmaps="a,b,c,d,e"/>
			</make>
		</data>
	</computedCore>

	<service id="basiccat" core="abccatcore">
		<inputDD id="forceQuo">
			<make table="abcd">
				<rowmaker idmaps="*"/>
			</make>
		</inputDD>
	</service>

	<service id="convcat" core="abccatcore" allowed="form, static">
		<inputDD original="forceQuo"/>
		<outputTable namePath="abcd">
			<column original="a" verbLevel="15"/>
			<column original="b" displayHint="sf=2"/>
			<column original="d" unit="m"/>
		</outputTable>
	</service>

</resource>
