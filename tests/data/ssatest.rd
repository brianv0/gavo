<resource schema="test" resdir=".">
	<table id="hcdtest" onDisk="True">
		<mixin instrument="DaCHS test suite" fluxCalibration="UNCALIBRATED"
			>//ssap#hcd</mixin>
	</table>

	<table id="hcdouttest">
		<FEED source="//ssap#hcd_outtable"/>
	</table>

	<data id="test_import">
		<sources pattern="data/*.ssatest"/>
		<keyValueGrammar>
			<rowfilter procDef="//products#define">
				<bind name="table">"\schema.hcdtest"</bind>
			</rowfilter>
		</keyValueGrammar>
		<make table="hcdtest" role="primary">
			<rowmaker>
				<apply procDef="//ssap#setMeta">
					<bind name="dstitle">@title</bind>
					<bind name="pubDID">"ivo://test.inv/"+@id</bind>
				</apply>
			</rowmaker>
		</make>
	</data>
</resource>
