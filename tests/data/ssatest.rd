<resource schema="test" resdir=".">
	<table id="hcdtest" onDisk="True" primary="ssa_pubDID">
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
			<rowmaker idmaps="*">
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
			<FEED source="//ssap#hcd_condDescs"/>
			<condDesc buildFrom="excellence"/>
		</ssapCore>
		<publish render="ssap.xml" sets="local"/>
		<meta name="ssap.dataSource">artificial</meta>
		<meta name="ssap.creationType">archival</meta>
		<meta name="ssap.testQuery">MAXREC=1</meta>
	</service>
</resource>
