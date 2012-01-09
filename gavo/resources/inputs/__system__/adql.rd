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

To get started using ADQL, 
`an article by Ray Plante 
<http://www.aspbooks.org/a/volumes/article_details/?paper_id=27959>`_ 
might be a good read.  However, the ADQL specification has
moved quite a bit since then.  If you are serious about learning ADQL,
you should read an introduction to SQL, ignoring everything about DDL,
and then try to figure out the 
`ADQL specification <http://www.ivoa.net/Documents/latest/ADQL.html>`_.

As to SQL introductions, every bookstore and library has quite a few of them.
Online, `A Gentle Introduction to SQL <http://sqlzoo.net/>`_ or chapter
three of `Practical PostgreSQL <http://www.faqs.org/docs/ppbook/book1.htm>`_
might be useful.

Also have a look at the Examples_ below.

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
planner messes up; see the `Story I: Guide Star`_ below.

Date literals can be specified `as for Postgresql <http://www.postgresql.org/docs/8.3/static/datatype-datetime.html#DATATYPE-DATETIME-INPUT>`_;
you always need to use strings.  So, ``'2000-12-31'`` or ``'J2416642.5'``
are both valid date specifications.  See also `Story II: Historic Lights`_

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


Examples
========

Story I: Guide star
'''''''''''''''''''

Suppose you have developed an adaptive optics instrument that you want to use
to observe radio-loud quasars; you don't really care which one, but you're
sitting on the south pole, and you'll need a guide star, and it'd be nice if
the object were in the redshift range of 0.5 to 1.  

In the
table list, you notice `this list of QSOs <http://dc.zah.uni-heidelberg.de/__system__/dc_tables/show/tableinfo/veronqsos.data>`_, 
and you see there's a column specifying whether these quasars are detected in
radio; also, you want the thing to be far enough south, and you specify the
redshift:

::

  SELECT TOP 100 raj2000, dej2000, name, z FROM veronqsos.data 
    WHERE notRadio!='*' 
    AND z BETWEEN 0.5 AND 1
    AND dej2000<-40

In ADQL, each statement starts with a SELECT.  Actually, almost all
of ADQL is case insensitive, so you could have written "select" as well.
However, it's customary in the SQL world to write SQL keywords in uppercase
and the rest in lowercase.  Note that the column labels are case insensitive
as well.

The next tokens in the statement, "TOP 100", specify that we only want to see
100 items.  Writing this is generally a good idea when you do not know how much
to expect.  Our service will happily serve you millions of rows, and your
browser may not like that, and of course it's nice not to put unnecessary
load on our servers.

After that, you specify the columns you want to see returned.  You could
put expressions there, but here we don't need that.  This list of
columns is ended by the keyword FROM, followed by the table you want
to operate on.

This much is necessary, and if the query ended there, you'd get all (or,
with the "TOP 100", one hundered randomly selected ) rows -- "row" is
SQL slang for a data item, in this case, a QSO.

Usually, you want to give some conditions, and this is done after the WHERE.
You can see that you can use the usual operators (where equality is "="
rather than C's "=="; SQL doesn't have any assignments in the C sense,
so the equality sign isn't used).  SQL has some nice additional operators
like the "BETWEEN ... AND ..." shown above.

Individual expressions can be combined with logical operators like "AND",
"OR", and "NOT".

Now, if you enter the above expression in the 
\RSTservicelink{__system__/adql/query/form}{query box} of this service,
you'll get an HTML table of the matches.  100 rows come back, so the "TOP 100" 
probably cut off a couple of matches.  In this case, it would be safe to
try without, you'd get back 422 rows, which is still convenient to display.

Now, which of these objects have a "good" guide star?  Say our device
works best of guide stars in the magnitude range of 10 to 11 in V, 
and the guide star should be no farther away than 0.3 degrees.  Consulting
the tables listing again, you come up with the 
`PPMX <http://vo.uni-hd.de/__system__/dc_tables/show/tableinfo/ppmx.data>`.  What you need is a crossmatch of PPMX with the little catalogue of
QSOs relevant to you generated from the query above.

In ADQL's lingo, a crossmatch could look like this::

  SELECT q.name, q.raj2000, q.dej2000, p.alphaFloat, p.deltaFloat FROM (
    SELECT TOP 100 raj2000, dej2000, name, z FROM veronqsos.data 
      WHERE notRadio!='*' 
      AND z BETWEEN 0.5 AND 1
      AND dej2000<-40) AS q JOIN
    ppmx.data AS p ON (1=CONTAINS(
      POINT('ICRS', q.raj2000, q.dej2000),
      CIRCLE('ICRS', p.alphaFloat, p.deltaFloat, 0.3)))

Note that most of the mess in here is the query for the QSOs we did above.
Queries can usually stand in for wherever tables can stand in ADQL.  You
always need an AS clause to give the subquery a name, though.

The main new point here is the *join*, which basically means "bring together
two tables".  Now, a table in SQL is a set of tuples.  When you have two
sets of tuples, there are various ways to bring them together -- you can
build the (flattened) cartesian product of the two (usually resulting
in a huge set), you can stick together randomly drawn tuples, etc.

Most of these operations are supported by SQL's (and hence ADQL's) JOIN.  The
pattern above, however, is what you want for crossmatches:  You write down the
two tables, giving the aliases (with AS) for convenience and then join them.
This happens by writing JOIN between the two table specifications and then
giving a condition in parentheses after an ON behind the last table.

For crossmatching, this boils down to the ADQL CONTAINS function operating on
an ADQL POINT and and ADQL CIRCLE, made up from the coordinates relevant to
you.  The radius of the circle is given in degrees; most of ADQL is leaning
towards degrees, but not the trigonometric functions, which work in radians.
CONTAINS is a numeric function, returning 1 when the point in the first
argument is within the circle in the second argument, 0 otherwise.

Points and circles are constructed with a coordinate system specification
in the first argument.  The current ADQL implementation largely ignores
this specification, so you could in principle put there whatever you like.

In the example above, we used qualified names, i.e., names of the form
<table>.<column>.  If a column name is unique, you can leave the qualification
out, i.e., you could have written

::

  SELECT name, raj200, dej2000, alphaFloat, deltaFloat...

above.

The result of the above query is a list of 3428 positions of quasars and 
possible guide stars of any magnitude.  To select only guide stars with,
you could filter the results after the selection by appending something like
``WHERE vmag BETWEEN 10 AND 11``.  Equivalently, you could add the condition
to you selection from PPMX, like this:

::

  SELECT q.name, q.raj2000, q.dej2000, p.alphaFloat, p.deltaFloat FROM (
    SELECT TOP 100 raj2000, dej2000, name, z FROM veronqsos.data 
      WHERE notRadio!='*' 
      AND z BETWEEN 0.5 AND 1
      AND dej2000<-40) AS q 
    JOIN (
    SELECT * FROM ppmx.data WHERE vmag BETWEEN 10 AND 11) AS p 
    ON (1=CONTAINS(
      POINT('ICRS', q.raj2000, q.dej2000),
      CIRCLE('ICRS', p.alphaFloat, p.deltaFloat, 0.3)))

However, both of these queries will time out on you.  Our system will kill
queries coming from the web after 15 seconds and tell you that your query timed
out.  In that case, it may be worthwhile to try and reformulate it.  Otherwise,
just contact us and we will figure out some way to get your query to execute,
possibly by adding more indices to our tables.  In particular, any query on
large-ish data sets (like the PPMX) not using at least one condition on a
column with an index is bound to time out.  Columns that are parts of indices
are highlighted in the table descriptions.

It may not be obvious why adding the WHERE clause above should hurt so badly
here, since the database would only have to check a couple of thousand
rows, and that's a breeze for a modern computer.  However, database
engines contain a component called a query planner that should
reduce all equivalent queries to the same, optimal form.  In reality, this
doesn't always work very well, which isn't surprising when you think about
the amount of information required to find the optimal sequence of
operations to a given result.  This means that the machine might completely
mess up your query, and that is what happens in this case.

There is a common workaround in SQL, known as the "OFFSET 0" trick; this is
not possible in ADQL since its syntax doesn't allow this.  As a workaround,
you can say SELECT ALL, which internally does the same thing (of course, it's
not nice to overload a no-op with an almost-no-op).  The downside is that you 
need one more query level:

::

  SELECT * FROM (
    SELECT ALL q.name, q.raj2000, q.dej2000, p.alphaFloat, p.deltaFloat, p.vmag FROM (
      SELECT TOP 100 raj2000, dej2000, name, z FROM veronqsos.data 
        WHERE notRadio!='*' 
        AND z BETWEEN 0.5 AND 1
        AND dej2000<-40) AS q JOIN
      ppmx.data AS p ON (1=CONTAINS(
        POINT('ICRS', q.raj2000, q.dej2000),
        CIRCLE('ICRS', p.alphaFloat, p.deltaFloat, 0.3)))) AS f 
  WHERE vmag BETWEEN 10 and 11

This may look daunting, but built up from simple queries, it's not really
hard to come up with expressions like these.

Story II: Historic Lights
'''''''''''''''''''''''''

Suppose you read in an old amateur observer's log there was an unexpected
object on the night sky in the cold winter nights of the week between January 
12th and 18th, 1903.
The \RSTservicelink{/__system__/dc_tables/show/tableinfo/lsw.plates}{table with plate scans from Heidelberg} 
could contain plates of that age.  Let's try it:

::

  SELECT centerAlpha, centerDelta, dateObs FROM lsw.plates 
    WHERE dateObs BETWEEN '1903-01-12' AND '1903-01-19'


As you can see, dates are entered in quotes, just like any string.  The
engine understand more than just the ISO format (yyyy-mm-dd).  See 
`Standards Compliance`_ above for details.  Also note that we wanted the 18th
to be included and therefore passed 1903-01-19 as the upper limit.  Dates
without times always count as 00:00 hours of the day, so anything with
a time *on* this day is not included.

Try it.  You will notice that the dates are JDs on output.  We will soon
add a function allowing you to specify output units, but for now, this is 
what you get.  You can feed these JDs back into the search engine by writing
'J<something>', like this:

::

  SELECT centerAlpha, centerDelta, dateObs FROM lsw.plates 
    WHERE dateObs BETWEEN 'J2416128.5' AND 'J2416133.5'

So, with a lot of luck, the people back then might have caught the light
or at least an afterglow.

You start looking for hints as to where the object might have been.
Eventually, you figure out it was "near the Aldebaran".  You could use
simbad to get its position and then query like this:

::

  SELECT accref, exposure, tmEnd FROM lsw.plates
    WHERE 
      dateObs BETWEEN 'J2416128.5' AND 'J2416133.5' AND
      1=CONTAINS(POINT('ICRS', centerAlpha, centerDelta),
        CIRCLE('ICRS', 69, 16, 15))

to see if any plate center is 15 degrees around Aldebaran's (rough ICRS) 
position.  And indeed, we have two of them.  

There is also a shortcut via REGIONs.  A REGION stands for
some kind of "geometry", i.e., point at or part of the sky, and site
operators are free to define what the arguments mean.  At the GAVO DC,
one way of specifying a region is via Simbad, like this:

::

	SELECT accref, exposure FROM lsw.plates
		WHERE
		 dateObs BETWEEN 'J2416128.5' AND 'J2416133.5' AND
		 1=CONTAINS(REGION('simbad Aldebaran'),
			 CIRCLE('ICRS', centerAlpha, centerDelta, 15))


Note how we needed to switch around the roles of Aldebaran's position
and the positions we got from the database.  There currently is no
way to say "get a circle around a Simbad position".  If you need
this at some point, let us know.  Also note that you cannot pull
a name from the database and try to resolve it via Simbad.  For many
reasons we would be very reluctant to add such a functionality.

*to be continued*
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
