<!-- a resource descriptor to more-or-less safely test a couple of operations
-->

<resource resdir="__tests" schema="tests">

	<data id="fileUploadTest">
		<property name="stagingDir">upload</property>
		<sources pattern="upload/[a-z]*"/>
		<keyValueGrammar/>
		
		<table id="files" primary="name" onDisk="True"
				allProfiles="defaults,trustedquery">
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

	<uploadCore id="uploadcore" destDD="fileUploadTest"/>

	<service id="upload" core="uploadcore" allowed="upload,mupload">
		<meta name="title">Upload Test</meta>
		<meta name="shortName">fileupdate_test</meta>
	</service>

	<fixedQueryCore id="resetcore" writable="True"
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

	<service id="dyntemplate" allowed="fixed,form">
		<meta name="title">Dynamic Template Test</meta>
		<fixedQueryCore query="select table_name from tap_schema.tables limit 1">
			<outputTable>
				<param name="aFloat">1.25</param>
				<column name="table_name" type="text"/>
			</outputTable>
		</fixedQueryCore>
		<template key="fixed">//tpltest.html</template>
		<template key="form">//tpltest.html</template>
	</service>

	<service id="errors" allowed="form">
		<pythonCore>
			<inputTable>
				<inputKey name="what" type="text"/>
			</inputTable>
			<coreProc>
				<setup>
					<code>
						from gavo import svcs
					</code>
				</setup>
				<code>
					excName = inputTable.getParam("what")
					if excName=="DataError":
						raise base.DataError("test error")
					raise svcs.__dict__[excName]("test error",
						hint="This is for testing")
				</code>
			</coreProc>
		</pythonCore>
	</service>

	<regSuite id="dachs">
		<regTest title="Auth required for protected form.">
			<url>limited/form</url>
			<code>
				self.assertHTTPStatus(401)
			</code>
		</regTest>

		<regTest title="DB timeout yields a nice response">
			<url>timeout/form</url>
			<code>
				self.assertHasStrings("Just wait a while", 
					"Query timed out (took too")
			</code>
		</regTest>

		<regTest title="Admin requries login">
			<url>/seffe/__system__/adql</url>
			<code>
				self.assertHTTPStatus(401)
			</code>
		</regTest>

		<regTest title="No admin link to bother regular users">
			<url>/__system__/adql/query/form</url>
			<code>
				self.assertLacksStrings("Admin me")
			</code>
		</regTest>

		<regTest title="ADQL docs appear to be in shape">
			<url>/__system__/adql/query/info</url>
			<code><![CDATA[
				self.assertHasStrings("Service Documentation", "About ADQL", 
					'">TAP examples</a>')
			]]></code>
		</regTest>

		<regTest title="Vanity redirect works">
			<url>/adql</url>
			<code>
				self.assertHTTPStatus(301)
				self.assertHasStrings('__system__/adql/query/form"',
					"Moved Permanently")
			</code>
		</regTest>

		<regTest title="Table info on non-existing table yields useful error">
			<url>/tableinfo/thistable.doesnotexist</url>
			<code>
				self.assertHasStrings("table 'thistable.doesnotexist' could not be"
					" located in data center table listing.")
			</code>
		</regTest>

		<regTest title="OAI error response validates">
			<url verb="do_a_hiccup">/oai.xml</url>
			<code>
				self.assertValidatesXSD()
			</code>
		</regTest>

		<regTest title="OAI Identify validates">
			<url verb="Identify">/oai.xml</url>
			<code>
				self.assertHasStrings("&lt;oai:Identify")
				self.assertValidatesXSD()
			</code>
		</regTest>

		<regTest title="Help page is sanely delivered">
			<url>/static/help.shtml</url>
			<code>
				self.assertHasStrings("Service discovery", 
					"Search forms", "VOTable", "sidebar")
			</code>
		</regTest>

		<regTest title="ADQL Parse errors are reported in-form">
			<url parSet="form" query="foobar">/__system__/adql/query/form</url>
			<code>
				self.assertHasStrings("Service info", "Could not parse", 
					'Expected "SELECT"')
			</code>
		</regTest>

		<regTest title="Users table is not accessible through ADQL">
			<url parSet="form" query="select * from dc.users"
				>/__system__/adql/query/form</url>
			<code>
				self.assertHasStrings("Could not locate table", "Result link")
			</code>
		</regTest>

		<regTest title="TAP error message looks like it's according to standard.">
			<url>/__system__/tap/run/tap/sync</url>
			<code><![CDATA[
				self.assertHasStrings('<RESOURCE type="results">',
					'<INFO name="QUERY_STATUS" value="ERROR">',
					'Missing mandatory parameter')
			]]></code>
		</regTest>

	</regSuite>

	<regSuite title="Caching and compression" sequential="True">
		<regTest title="Root page is well-formed HTML">
			<url>/</url>
			<code>
				from gavo.utils import ElementTree
				tree = ElementTree.fromstring(self.data)
				self.assertEqual(tree[1].tag,
					'{http://www.w3.org/1999/xhtml}body')
			</code>
		</regTest>

		<regTest title="Transparent compression of static resource works">
			<url>
				<value key="Accept-Encoding">gzip</value>/</url>
			<code>
				import gzip
				from cStringIO import StringIO
				stuff = gzip.GzipFile(fileobj=StringIO(self.data)).read()
				self.assertTrue('src="/static/img/logo_medium.png"' in stuff,
				 	"decompressed response looks about right")
			</code>
		</regTest>

		<regTest title="Uncompressed root page served from cache">
			<url>/</url>
			<code>
				self.assertHasStrings('src="/static/img/logo_medium.png"')
				for key, value in self.headers:
					if key=="x-cache-creation":
						self.assertFalse(value is None)
						break
				else:
					raise AssertionError("No x-cache-creation header")
			</code>
		</regTest>
	</regSuite>

	<regSuite id="upload" sequential="True">
		<regTest title="Upload service shows a form">
			<url>upload/upload</url>
			<code>
				self.assertHasStrings("Insert", "Update", 'type="file"')
			</code>
		</regTest>

		<regTest
				title="Update of non-existing data is a no-op (may fail on state)">
			<url parSet="form" Mode="u" httpMethod="POST">
				<httpUpload name="File" fileName="c.foo"
					>a: 15&#10;b:10
				</httpUpload>upload/upload</url>
			<code>
				self.assertHasStrings("0 record(s) modified.")
			</code>
		</regTest>

		<regTest
				title="Insert of non-existing data touches one record.">
			<url parSet="form" Mode="i" httpMethod="POST">
				<httpUpload name="File" fileName="c.foo"
					>a: 15&#10;b:10
				</httpUpload>upload/upload</url>
			<code>
				self.assertHasStrings("1 record(s) modified.")
			</code>
		</regTest>

		<regTest
				title="Duplicate insertion of data yields error">
			<url parSet="form" Mode="i" httpMethod="POST">
				<httpUpload name="File" fileName="c.foo"
					>a: 15&#10;b:10
				</httpUpload>upload/upload</url>
			<code>
				self.assertHasStrings("Cannot enter c.foo in database: duplicate key",
					"violates unique constraint")
			</code>
		</regTest>

		<regTest
				title="Updates of existing data modify db">
			<url parSet="form" Mode="u" httpMethod="POST">
				<httpUpload name="File" fileName="c.foo"
					>a: 15&#10;b:10
				</httpUpload>upload/upload</url>
			<code>
				self.assertHasStrings("1 record(s) modified.")
			</code>
		</regTest>
	
		<regTest title="Reset of uploads table seems to work">
			<url>reset/form</url>
			<code>
				self.assertHasStrings("Matched: 0")
			</code>
		</regTest>
	</regSuite>

	<regSuite title="error documents">
		<LOOP>
			<csvItems>
				excName, expStatus, id, extraText
				UnknownURI,     404, cur-a,   within the data center
				ForbiddenURI,   403, cur-b,   complain fiercely
				WebRedirect,    301, cur-c,   different URL
				SeeOther,       303, cur-d,   Please turn
				Authenticate,   401, cur-e,   access is protected
				BadMethod,      405, cur-f,   HTTP method
				DataError,      406, cur-g,   server cannot generate
				test error,     500, cur-h,   KeyError
			</csvItems>
			<events>
				<regTest title="\excName renders" id="\id">
					<url parSet="form" what="\excName">errors</url>
					<code>
						self.assertHTTPStatus(\expStatus)
						self.assertHasStrings("test error", "\extraText")
					</code>
				</regTest>
			</events>
		</LOOP>
	</regSuite>

</resource>
