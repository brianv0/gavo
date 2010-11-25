<!-- a resource descriptor to more-or-less safely test a couple of operations
-->

<resource resdir="__tests" schema="tests">

	<data id="fileUploadTest">
		<property name="stagingDir">upload</property>
		<sources pattern="upload/[a-z]*"/>
		<keyValueGrammar/>
		
		<table id="files" primary="name" onDisk="True" allRoles="default,gavo">
			<column name="name" type="text"/>
			<column name="a"/>
			<column name="b"/>
		</table>
		
		<rowmaker id="make_files">
			<map dest="name">\srcstem</map>
			<idmaps>a,b</idmaps>
		</rowmaker>

		<make table="files" rowmaker="make_files"/>
	</data>

	<data id="boxTest">
		<dictlistGrammar/>
		
		<table id="misctypes">
			<column name="box" type="box"/>
		</table>
		<make table="misctypes"/>
	</data>

	<uploadCore id="uploadcore" destDD="fileUploadTest"/>

	<service id="upload" core="uploadcore" allowed="upload,mupload">
		<meta name="title">Upload Test</meta>
		<meta name="shortName">fileupdate_test</meta>
	</service>


	<fixedQueryCore id="resetcore" 
		query="delete from tests.files where name='c'">
		<outputTable/>
	</fixedQueryCore>

	<service id="reset" core="resetcore">
		<meta name="title">Reset Test Tables</meta>
		<meta name="shortName">testtables_reset</meta>
	</service>

	<fixedQueryCore id="timeoutcore" timeout="1" query=
		"select (select avg(asin(sqrt(x)/224.0)) from generate_series(1, whomp) as x) as q from generate_series(1, 50000) as whomp">
		<outputTable>
			<column name="foo"/>
		</outputTable>
	</fixedQueryCore>

	<service id="timeout" core="timeoutcore">
		<meta name="title">Just wait a while for a timeout</meta>
	</service>

	<service id="limited" core="timeoutcore" limitTo="notYou">
		<meta name="title">Only notYou may see this.</meta>
	</service>
</resource>
