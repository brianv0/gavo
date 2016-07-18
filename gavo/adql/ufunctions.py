"""
"User" defined functions, i.e., ADQL functions defined only on this
system.

See the userFunction docstring on how to use these.
"""

#c Copyright 2008-2016, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from gavo import utils
from gavo.adql import common
from gavo.adql import fieldinfo
from gavo.adql import morphhelpers
from gavo.adql import nodes
from gavo.adql import tree


UFUNC_REGISTRY = {}


def userFunction(name, signature, doc, returntype="double precision", 
		unit="", ucd=""):
	"""a decorator adding some metadata to python functions to make
	them suitable as ADQL user defined functions.

	name is the name the function will be visible under in ADQL; signature is a
	signature not including the name of the form '(parName1 type1, parName1
	type2) -> resulttype'; doc is preformatted ASCII documentation.  The
	indentation of the second line will be removed from all lines.

	returntype is the SQL return type, which defaults to double
	precision.  With current ADQL, you could specialize to INTEGER
	if you like, but there's little in the way of variation on top
	of that since user defined functions must be numeric.  unit and
	ucd are optional for when you actually have a good guess what's
	coming back from your ufunc.

	The python function receives an array of arguments; this will in
	general be ADQL expression trees.  It must return either a string that
	will go literally into the SQL string (so take care to quote;
	in general, you will use nodes.flatten(arg) to flatten individual
	args); or they may return None, in which case the expression tree
	remains unchanged.  This is for when the actual implementation is
	in the database.

	If you receive bad arguments or something else goes awry, raise
	a UfuncError.
	"""
	def deco(f):
		f.adqlUDF_name = name
		f.adqlUDF_signature = f.adqlUDF_name+signature.strip()
		f.adqlUDF_doc = utils.fixIndentation(doc, "", 1).strip()
		f.adqlUDF_returntype = returntype
		f.adqlUDF_unit = unit
		f.adqlUDF_ucd = ucd
		UFUNC_REGISTRY[f.adqlUDF_name.upper()] = f
		return f
	return deco


def _makeBooleanizer(funcName, booleanExpr):
	"""makes and registers a booleanizer for funcName.

	booleanExpr is the postgres expression the function should be booleanized
	to.  Refer to the two arguments as %(1)s and %(2)s
	"""
	def _booleanizeThis(node, operator, operand):
		if len(node.args)!=2:
			raise common.UfuncError("%s takes exactly two arguments"%funcName)
		return morphhelpers.addNotToBooleanized(
			booleanExpr%{
				'1': nodes.flatten(node.args[0]), 
				'2': nodes.flatten(node.args[1])},
			operator, operand)

	morphhelpers.registerBooleanizer(funcName.upper(), _booleanizeThis)



@userFunction("gavo_match",
	"(pattern TEXT, string TEXT) -> INTEGER",
	"""
	gavo_match returns 1 if the POSIX regular expression pattern
	matches anything in string, 0 otherwise.
	""",
	"integer")
def _match(args):
	if len(args)!=2:
		raise common.UfuncError("gavo_match takes exactly two arguments")
	return "(CASE WHEN %s ~ %s THEN 1 ELSE 0 END)"%(
		nodes.flatten(args[1]), nodes.flatten(args[0]))


@userFunction("ivo_hasword",
	"(haystack TEXT, needle TEXT) -> INTEGER",
	"""
	gavo_hasword returns 1 if needle shows up in haystack, 0 otherwise.  This
	is for "google-like"-searches in text-like fields.  In word, you can
	actually employ a fairly complex query language; see
	http://www.postgresql.org/docs/8.3/static/textsearch.html
	for details.
	""",
	"integer")
def _hasword(args):
	if len(args)!=2:
		raise common.UfuncError("ivo_hasword takes exactly two arguments")
	return None

_makeBooleanizer("ivo_hasword", 
	"(to_tsvector('english', %(1)s) @@ plainto_tsquery('english', %(2)s))")


@userFunction("ivo_nocasematch",
	"(value TEXT, pattern TEXT) -> INTEGER",
	"""
	ivo_nocasematch returns 1 if pattern matches value, 0 otherwise.
	pattern is defined as for the SQL LIKE operator, but the
	match is performed case-insensitively.  This function in effect
	provides a surrogate for the ILIKE SQL operator that is missing from
	ADQL.
	""",
	"integer")
def _nocasematch(args):
	if len(args)!=2:
		raise common.UfuncError("ivo_nocasematch takes exactly two arguments")
	return None

_makeBooleanizer("ivo_nocasematch", "(%(1)s ilike %(2)s)")


@userFunction("ivo_hashlist_has",
	"(hashlist TEXT, item TEXT) -> INTEGER",
	"""
	The function takes two strings; the first is a list of words not
	containing the hash sign (#), concatenated by hash signs, the second is
	a word not containing the hash sign.  It returns 1 if, compared
	case-insensitively, the second argument is in the list of words coded in
	the first argument.  The behaviour in case the the second
	argument contains a hash sign is unspecified.
	""",
	"integer")
def _hashlist_has(args):
	if len(args)!=2:
		raise common.UfuncError("ivo_haslist_has takes exactly two arguments")
	return None

_makeBooleanizer("ivo_hashlist_has", 
	"lower(%(2)s) = ANY(string_to_array(%(1)s, '#'))")


@userFunction("gavo_to_mjd",
	"(d TIMESTAMP) -> DOUBLE PRECISION",
	"""
	The function converts a postgres timestamp to modified julian date.
	This is naive; no corrections for timezones, let alone time
	scales or the like are done; you can thus not expect this to be
	good to second-precision unless you are careful in the construction
	of the timestamp.
	""")
def _to_mjd(args):
	if len(args)!=1:
		raise common.UfuncError("gavo_to_mjd takes exactly one timestamp argument")
	return "ts_to_mjd(%s)"%nodes.flatten(args[0])


@userFunction("gavo_to_jd",
	"(d TIMESTAMP) -> DOUBLE PRECISION",
	"""
	The function converts a postgres timestamp to julian date.
	This is naive; no corrections for timezones, let alone time
	scales or the like are done; you can thus not expect this to be
	good to second-precision unless you are careful in the construction
	of the timestamp.
	""")
def _to_jd(args):
	if len(args)!=1:
		raise common.UfuncError("gavo_to_jd takes exactly one timestamp argument")
	return "ts_to_jd(%s)"%nodes.flatten(args[0])


@userFunction("ivo_string_agg",
	"(expression TEXT, delimiter TEXT) -> TEXT",
	"""
	An aggregate function returning all values of
	expression within a GROUP contcatenated with delimiter
	""",
	"text")
def _string_agg(args):
	if len(args)!=2:
		raise common.UfuncError("ivo_string_agg takes exactly two arguments")
	return "string_agg(%s, %s)"%(
		nodes.flatten(args[0]), nodes.flatten(args[1]))


@userFunction("ivo_apply_pm",
	"(ra DOUBLE PRECISION, dec DOUBLE PRECISION, pmra DOUBLE PRECISION, pmde DOUBLE PRECISON, epdist DOUBLE PRECISION) -> POINT",
	"""Returns a POINT (in the UNDEFINED reference frame) for the position
	an object at ra/dec with proper motion pmra/pmde has after epdist years.

	positions must be in degrees, PMs in should be in julian years (i.e., proper
	motions are expected in degrees/year).  pmra is assumed to contain 
	cos(delta).

	NOTE: This currently is a crappy approximation that does *not* go
	through the tangential plane.  If you use it, let the operators know
	so we replace it with something real.
	""",
	returntype="spoint")
def _ivo_apply_pm(args):
	if len(args)!=5:
		raise common.UfuncError(
			"ivo_apply_pm requires exactly ra, dec, pmra, pmdec, epdist.")
	
	ra, dec, pmra, pmdec, epdist = [nodes.flatten(a) for a in args]
	return ("spoint(RADIANS({ra}+{pmra}/cos(RADIANS({dec})*{epdist})),"
		" RADIANS({dec}+{pmdec}*{epdist}))").format(**locals())


# the healpix functions for now use a temporary extension of pgsphere;
# this is available from ARI's Debian repository.  No good plan
# on where healpix support will finally be going is made yet.
#
# You'll most likely have to define the underlying functions yourself.
# Here's how:
#
#CREATE FUNCTION healpix_nest(integer, spoint)
#RETURNS bigint
#AS '/usr/lib/postgresql/9.4/lib/pg_sphere.so'
#LANGUAGE C IMMUTABLE STRICT;
#COMMENT ON FUNCTION healpix_nest(integer, spoint) IS
#'nested healpix index of a spherical point for the specified integer level
#(first argument)';
#
#CREATE FUNCTION center_of_healpix_nest(integer, bigint)
#RETURNS spoint
#AS '/usr/lib/postgresql/9.4/lib/pg_sphere.so', 'inv_healpix_nest'
#LANGUAGE C IMMUTABLE STRICT;
#COMMENT ON FUNCTION healpix_nest(integer, spoint) IS
#'spherical point designating the centre of a nested healpix element for the
#specified integer level (first argument)';

@userFunction("ivo_healpix_index",
	"(order INTEGER, ra DOUBLE PRECISION, dec DOUBLE PRECISION) -> BIGINT",
	"""Returns the index of the (nest) healpix with order containing the 
	spherical point (ra, dec).

	An alternative, 2-argument form 
	
	ivo_healpix_index(order INTEGER, p POINT) -> BIGINT

	is also available.
	""",
	returntype="bigint")
def _ivo_healpix_index(args):
	if len(args)==2:
		return "healpix_nest(%s, %s)"%(
			nodes.flatten(args[0]), nodes.flatten(args[1]))
	elif len(args)==3:
		return "healpix_nest(%s, spoint(RADIANS(%s), RADIANS(%s)))"%(
			nodes.flatten(args[0]), nodes.flatten(args[1]), nodes.flatten(args[2]))
	else:
		raise common.UfuncError("ivo_healpix_index takes either (ra, dec, order)"
			" or (point, order) arguments")


@userFunction("ivo_healpix_center",
	"(hpxOrder INTEGER, hpxIndex BIGINT) -> POINT",
	"""returns a POINT corresponding to the center of the healpix with
	the given index at the given order.
	""",
	returntype="spoint")
def _ivo_healpix_center(args):
	if len(args)!=2:
		raise common.UfuncError("ivo_healpix_center only takes (index, order)"
			" arguments")
	return "center_of_healpix_nest(%s, %s)"%(
		nodes.flatten(args[0]), nodes.flatten(args[1]))


class UserFunction(nodes.FunctionNode):
	"""A node processing user defined functions.

	See the userFunction docstring for how ADQL user defined functions
	are defined.
	"""
	type = "userDefinedFunction"

	def _getFunc(self):
		try:
			return UFUNC_REGISTRY[self.funName.upper()]
		except:
			raise common.UfuncError("No such function: %s"%self.funName)

	def _polish(self):
		self.processedExpression = self._getFunc()(self.args)

	def flatten(self):
		if self.processedExpression is None:
			return nodes.FunctionNode.flatten(self)
		else:
			return self.processedExpression

	def addFieldInfo(self, context):
		ufunc = self._getFunc()
		self.fieldInfo = fieldinfo.FieldInfo(ufunc.adqlUDF_returntype, 
			ufunc.adqlUDF_unit, ufunc.adqlUDF_ucd)


tree.registerNode(UserFunction)
