<resource schema="test">
	<table id="testjobs">
		<FEED source="//uws#uwsfields"/>
		<column name="magic" type="text" description="extra magic attribute
			exclusive to testjobs"/>
	</table>
	
	<data id="import">
		<make table="testjobs"/>
	</data>
</resource>
