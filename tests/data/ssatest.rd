<resource schema="test" resdir=".">
	<table id="hcdtest" onDisk="True">
		<meta name="description">A boring and pointless test table</meta>
		<mixin instrument="DaCHS test suite" fluxCalibration="UNCALIBRATED"
			>//ssap#hcd</mixin>
		<column name="excellence" type="integer" description="random number"/>
	</table>

	<data id="test_import">
		<sources pattern="data/*.ssatest"/>
		<keyValueGrammar>
			<rowfilter procDef="//products#define">
				<bind name="table">"\schema.hcdtest"</bind>
				<bind name="mime">@mime</bind>
			</rowfilter>
		</keyValueGrammar>
		<make table="hcdtest" role="primary">
			<rowmaker idmaps="excellence">
				<apply procDef="//ssap#setMeta">
					<bind name="pubDID">"ivo://test.inv/"+@id</bind>
					<LOOP listItems="dstitle specstart specend bandpass alpha delta
							dateObs">
						<events>
							<bind name="\item">@\item</bind>
						</events>
					</LOOP>
					<bind name="targname">@targetName</bind>
				</apply>
			</rowmaker>
		</make>
	</data>

	<service id="s">
		<ssapCore queriedTable="hcdtest" id="foocore">
			<condDesc buildFrom="excellence"/>
		</ssapCore>
	</service>
</resource>
