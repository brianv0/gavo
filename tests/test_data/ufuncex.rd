<resource schema="test" readProfiles="trustedquery,untrustedquery">
	<!-- a table to provide material for ufunctests. -->

	<table id="ufuncex" onDisk="True" adql="True">
		<column name="testgroup" type="text"/>
		<column name="dt" type="timestamp"/>
		<column name="ra"/>
		<column name="dec"/>
		<column name="p" type="spoint"/>
	</table>

	<data id="import">
		<sources items="0"/>
		<embeddedGrammar>
			<iterator><code>
				rec = {"testgroup": None, "dt": None}

				rec["testgroup"] = "jd"
				rec["dt"] = datetime.datetime(year=1984, month=8, day=5, hour=12)
				rec["ra"], rec["dec"] = 23.5, -12.25
				rec["p"] = pgsphere.SPoint.fromDegrees(230, 60)
				yield rec
			</code></iterator>
		</embeddedGrammar>
		<make table="ufuncex"/>
	</data>
</resource>
