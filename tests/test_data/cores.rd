<resource resdir="." schema="test">
	<meta name="description">Helpers for tests for cores.</meta>
	<table id="abcd">
		<column name="a" type="text" verbLevel="1"/>
		<column name="b" type="integer" verbLevel="5">
			<values nullLiteral="-1"/>
		</column>
		<column name="c" type="integer" verbLevel="15">
			<values nullLiteral="-1"/>
		</column>
		<column name="d" type="integer" verbLevel="20" unit="km">
			<values nullLiteral="-1"/>
		</column>
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

	<service id="enums">
		<dbCore queriedTable="abcd">
			<condDesc>
				<inputKey original="a" required="False">
					<values fromdb="tableName from dc.tablemeta" multiOk="True"/>
				</inputKey>
			</condDesc>
			<condDesc>
				<inputKey original="b">
					<values><option>1</option><option>2</option></values>
				</inputKey>
			</condDesc>
			<condDesc required="True">
				<inputKey original="c">
					<values default="1"><option>1</option><option>2</option></values>
				</inputKey>
			</condDesc>
		</dbCore>
	</service>

	<service id="cstest" allowed="form, scs.xml">
		<outputTable verbLevel="20"/>
		<dbCore queriedTable="data/test#adql">
			<FEED source="//scs#coreDescs"/>
			<condDesc buildFrom="mag"/>
			<condDesc>
				<inputKey original="rV" type="vexpr-float"
					>-100 .. 100<property name="cssClass">rvkey</property>
				</inputKey>
			</condDesc>
		</dbCore>
		<property name="customCSS">
			.rvkey { background:red; }
		</property>
	</service>

	<service id="grouptest">
		<dbCore queriedTable="data/test#adql">
			<condDesc>
				<inputKey original="rV"/>
			</condDesc>
			<inputTable>
				<group name="magic"
					description="Some magic parameters we took out of thin air.">
					<property name="cssClass">localstuff</property>
					<paramRef dest="mag"/>
					<paramRef dest="rV"/>
				</group>
				<inputKey original="rV">
					<values default="-4"/>
				</inputKey>
				<inputKey original="mag"/>
				<inputKey original="alpha"/>
				<inputKey original="delta"/>
			</inputTable>
		</dbCore>
	</service>

	<service id="impgrouptest" defaultRenderer="form">
		<dbCore queriedTable="data/test#adql">
			<condDesc>
				<inputKey original="rV"/>
				<inputKey original="mag"/>
				<group name="phys" description="Ah, you know.  The group with
					 the magic and the thin air">
					 <property name="label">Wonz</property>
					 <property name="style">compact</property>
				</group>
			</condDesc>
		</dbCore>
	</service>
	
</resource>
