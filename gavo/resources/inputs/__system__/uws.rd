<resource schema="uws">
	<meta name="description">Tables and helpers for the support of 
	an universial worker service.</meta>
	<!-- this must be kept in sync with protocols.uws -->

	<table id="jobs" onDisk="True" system="True" primary="jobId"
			forceUnique="True" dupePolicy="overwrite">
		<column name="jobId" type="text" description="Internal id of the job.  At the same time, uwsDir-relative name of the job directory."/>
		<column name="phase" type="text" description="The state of the job.">
			<values>
				<option>PENDING</option>
				<option>QUEUED</option>
				<option>EXECUTING</option>
				<option>COMPLETED</option>
				<option>ERROR</option>
				<option>ABORTED</option>
			</values>
		</column>
		<column name="executionDuration" type="integer" unit="s"
			description="Job time limit"/>
		<column name="quote" type="timestamp" 
			description="Predicted completion time for the job."/>
		<column name="destructionTime" type="timestamp"
			description="Time at which the job, including ancillary data, will be deleted"/>
		<column name="owner" type="text" 
			description="Submitter of the job, if verified"/>
		<column name="parameters" type="text" 
			description="Pickled representation of the parameters (except uploads)"/>
		<column name="runId" type="text" description="User-chosen run Id"/>
		<column name="actions" type="text" description=
			"Name of the Transitions class managing phase changes for this job"/>
		<column name="pid" type="integer" description=
			"A unix pid to kill to make the job stop"/>
		<column name="startTime" type="timestamp" description=
			"UTC job execution started"/>
		<column name="endTime" type="timestamp" description=
			"UTC job execution finished"/>
	</table>

	<table id="results" onDisk="True" system="True" primary="jobId,resultName"
			forceUnique="True" dupePolicy="overwrite">
		<foreignKey dest="jobId" source="jobId" table="uws.jobs"/>
		<column name="jobId" original="jobs.jobId"/>
		<column name="resultName" type="text" 
			description="File name of the job, relative to the job's WD"/>
		<column name="resultType" type="text"
			description="MIME type for this result."/>
	</table>

	<data id="make_jobs">
		<make table="jobs"/>
		<make table="results"/>
	</data>
</resource>
