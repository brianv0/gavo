<resource resdir="." schema="test">
	<macDef name="magCols">
		band, bandU, valR,     errR 
		j,    J,     140-145,  151-155
		h,    H,     161-166,  172-176
		k,    K,     182-187,  193-197
	</macDef>

	<table id="mags">
		<LOOP csvItems="\magCols">
			<events>
				<column name="\band\+mag" tablehead="Mag(\bandU)"
					unit="mag" ucd="phot.mag;em.IR.\bandU"
					description="Magnitude in the \bandU band"/>
				<column name="err\band\+mag" tablehead="Err. Mag(\bandU)"
					unit="mag" ucd="stat.error;phot.mag;em.IR.\bandU"
					description="Error in magnitude in the \bandU band"/>
			</events>
		</LOOP>
	</table>

	<data id="import">
		<columnGrammar topIgnoredLines="3">
			<LOOP csvItems="\magCols">
				<events>
					<col key="\band{}mag">\valR</col>
					<col key="err\band{}mag">\errR</col>
				</events>
			</LOOP>
		</columnGrammar>
		<make table="mags"/>
	</data>
</resource>
