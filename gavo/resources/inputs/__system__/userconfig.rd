<resource schema="__system">
	<STREAM id="obscore-extraevents">
		<doc><![CDATA[
			Write extra events to mix into obscore-published tables.  This
			will almost always be just additions to the obscore clause of
			looking roughly like::
				
				<property name="obscoreClause" cumulate="True">
					,
					CAST(\\\\plutoLong AS real) AS pluto_long,
					CAST(\\\\plutoLat AS real) AS pluto_lat
				</property>

			See also `Extending Obscore`_ in the reference manual.
		]]></doc>
	</STREAM>

	<STREAM id="obscore-extracolumns">
		<doc>
			Add column definitions for obscore here.  See `Extending Obscore`_ for
			details.
		</doc>
	</STREAM>

	<script id="_test-script" lang="python" name="test instrumentation"
		type="preIndex">
		# (this space left blank intentionally)
	</script>
</resource>
