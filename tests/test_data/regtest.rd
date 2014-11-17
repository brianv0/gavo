<resource schema="test" readProfiles="trustedquery,untrustedquery">
	<regSuite id="dumbsuite">
		<regTest title="Failing Test" id="failtest">
			<url testParam="10%w/o tax">foo</url>
			<code>
				self.assertHasStrings("Wittgenstein")
			</code>
		</regTest>
		<regTest title="Succeeding Test">
			<code>
				assert True
			</code>
		</regTest>
		<regTest title="failing XSD Test" id="xsdfail">
			<url testParam="10%w/o tax">foo</url>
			<code>
				self.assertValidatesXSD()
			</code>
		</regTest>
		<regTest id="xpathfail" title="not lots" url="/bar">
			<code>
				self.assertXpath("//v2:RESOURCE[1]", {
					"type": "lots"})
			</code>
		</regTest>
		<regTest id="exclusive" title="tagged test" url="/bar"
			tags="elite,prolete">
			<code>
				assert False, "You run a tagged test"
			</code>
		</regTest>
	</regSuite>
	
	<regSuite title="URL tests" id="urltests">
		<regTest title="a" id="atest">
			<url testParam="10%w/o tax">foo</url>
			<code>
				self.assertHasStrings("Kant", "Hume")
			</code>
		</regTest>
		<regTest title="b" url="/bar">
			<code>
				self.assertValidatesXSD()
			</code>
		</regTest>
		<regTest title="c"><url httpMethod="POST">
			<gobba>&amp;?</gobba>ivo://ivoa.net/std/quack</url>
			<code>
				self.assertHTTPStatus(200)
			</code>
		</regTest>
		<regTest title="d"><url>nork?urk=zoo<oo>1</oo><oo>2</oo></url>
		</regTest>
		<regTest title="xpathsuccess" url="/bar">
			<code>
				self.assertXpath("//v2:RESOURCE[1]", {
					"type": "meta", None: None})
				self.assertXpath("//v2:RESOURCE/v2:DESCRIPTION", {
					None: "give exact"})
			</code>
		</regTest>
	</regSuite>
</resource>

