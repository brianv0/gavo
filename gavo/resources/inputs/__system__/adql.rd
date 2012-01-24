<?xml version="1.0" encoding="utf-8"?>

<!-- The ADQL service and related data -->

<resource resdir="__system" schema="dc">
	<meta name="description">An endpoint for submitting ADQL queries
		to the data center and retrieving the result in various forms.</meta>
	<meta name="subject">Virtual observatory</meta>
	<meta name="subject">Catalogs</meta>
	<meta name="creationDate">2008-09-20T12:00:00Z</meta>

	<meta name="_intro" format="rst"><![CDATA[
On this page, you can use
`ADQL <http://www.ivoa.net/Documents/latest/ADQL.html>`_ to query 
\RSTservicelink{/__system__/dc_tables/list/form}{some of our tables}.
This is mainly for dabbling; use \RSTservicelink{/tap}{TAP} for larger
jobs.

To learn what ADQL is or for further information on this implementation, see the
\RSTservicelink{/__system__/adql/query/info}{service info}.  
]]>	
	</meta>
	<meta name="_bottominfo" format="rst">
		To protect your nerves, the server inserts a TOP 2000 phrase unless you
		give a limit yourself.  Thus, if you hit the 2000 record limit and want
		to override it, you can specify your limit yourself (like ``SELECT TOP
		20000...``).

		There is a fixed limit to 100000 rows on this service.  If this
		bugs you, use \RSTservicelink{tap}{TAP}.
	</meta>
	<meta name="_longdoc" format="rst"><![CDATA[

About this service
==================

To find out what tables are available for querying, see the
\RSTservicelink{__system__/dc_tables/list/form}{ADQL table list}.

Be sure to read `Standards Compliance`_ below.

About ADQL
==========

ADQL is the Astronomical Data Query Language, an extension of a subset of
the Standard Query Language `SQL <http://en.wikipedia.org/wiki/SQL>`_.  Its purpose is to give you a formal
language to specify what data you are interested in.

To get started using ADQL, try `our ADQL course`_ first.  There are plenty
of introductions SQL itself, which are perfectly useful for learning ADQL.
Check your local bookstore.  Online, `A Gentle Introduction to SQL`_ or chapter
three of `Practical PostgreSQL`_ might be useful; for the purposes
of learning ADQL, you can skip everything talking about "DDL" in general
introductions.

Finally, if you're serious about using ADQL, you should at least
briefly skim over the `ADQL specification`_.

Also have a look at the `TAP examples`_

.. _our ADQL course: http://docs.g-vo.org/adql
.. _Practical PostgreSQL: http://www.faqs.org/docs/ppbook/book1.htm
.. _A Gentle Introduction to SQL: http://sqlzoo.net/
.. _ADQL specification: http://www.ivoa.net/Documents/latest/ADQL.html
.. _TAP examples: \internallink{tap/run/examples}

Local guide
===========

Standards Compliance
''''''''''''''''''''

If you give no TOP clause, the system will automatically restrict your
matches to \getConfig{adql}{webDefaultLimit} rows.  This is mostly for
your own protection.  If you want more rows (make sure you don't throw
them at your browser, i.e., select VOTable output), use SELECT TOP 100000
or something along those lines.

In particular, when doing set operations (e.g., UNION) in STC-S,
no conforming of coordinate systems will be performed.

The output of ADQL geometries follows the TAP standard (simplified STC-S)
rather than the ADQL standard (something similarly messy).

ADQL defines coord_sys (the first argument to the geometry functions)
to be a string_value_expression; thus, you can have column references 
or concatenations or basically anthing there.  We only allow string literals
containing one of the defined coordinate systems there (these include at least
the empty string, GALACTIC, UNKNOWN, ICRS, FK4, FK5, and RELOCATABLE), or
NULL.

SELECT and SELECT ALL are not exactly the same thing.  The latter will add
an OFFSET 0 to the resulting postgresql query.  Use this when the query
planner messes up; see the `guide star example </tap/examples#Crossmatchforaguidestar>`_.

Date literals can be specified `as for Postgresql <http://www.postgresql.org/docs/8.3/static/datatype-datetime.html#DATATYPE-DATETIME-INPUT>`_;
you always need to use strings.  So, ``'2000-12-31'`` or ``'J2416642.5'``
are both valid date specifications.  See also the
`historic plates example <http://dc.g-vo.org/tap/examples#findingplatesbytimeandplace>`_.

The ADQL (unfortunately) does not allow boolean columns.  Within the data
center, we do have boolean columns here and there, and it would be shame to
dumb them down to integers.  They show up as INTEGERs in TAP_SCHEMA, though.
When you try to compare integers to them, you get an error message to the
effect that an "operator does not exist: boolean = integer".  To query against
such columns (and have valid ADQL), use ``col='True'`` or ``col='False'``.


Usability
'''''''''

Hint: You can send off your query by typing control-return from within the
input text box.

Error messages for parse (and other) errors are not always as helpful as
we would like them to be.  Feel free to complain to us with concrete examples
of where we messed up, and we'll try to improve.

]]>
	</meta>
	<meta name="_related" title="Tables available for ADQL">/__system__/dc_tables/list/form</meta>

	<adqlCore id="qcore">
		<inputTable id="adqlInput">
			<inputKey name="query" tablehead="ADQL query" type="text"
				description="A query in the Astronomical Data Query Language"
				widgetFactory="widgetFactory(ScalingTextArea, rows=15)"
				required="True"/>
			<inputKey name="_TIMEOUT" type="integer" unit="s" 
				tablehead="Timeout after" 
				description="Seconds until the query is aborted.  If you find 
					yourself having to raise this beyond 200 or so, please contact 
					the GAVO staff for hints on how to optimize your query">
				<values default="5"/>
			</inputKey>
		</inputTable>
		<outputTable><column name="stuffer" 
			description="Just here until we figure out a good way to declare variable output fields."/>
		</outputTable>
	</adqlCore>

	<service id="query" core="qcore">
		<meta name="shortName">gavoadql</meta>
		<meta name="title">ADQL Query</meta>
		<publish render="form" sets="local,ivo_managed"/>
	</service>
</resource>
