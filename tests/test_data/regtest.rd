<resource schema="test">
	<regSuite>
		<regTest title="Failing Test">
			<code>
				assert False
			</code>
		</regTest>
		<regTest title="Succeeding Test">
			<code>
				assert True
			</code>
		</regTest>
	</regSuite>
	
	<regSuite description="URL tests" id="urltests">
		<regTest title="a" id="atest">
			<url testParam="10%w/o tax">foo</url></regTest>
		<regTest title="b"><url>/bar</url></regTest>
		<regTest title="c"><url httpMethod="POST">
			<gobba>&amp;?</gobba>ivo://ivoa.net/std/quack</url>
		</regTest>
		<regTest title="d"><url>nork?urk=zoo<oo>1</oo><oo>2</oo></url>
		</regTest>
	</regSuite>
</resource>

