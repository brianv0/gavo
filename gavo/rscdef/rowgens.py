""" 
Row generators and their helpers.

These actually belong to grammars, but since this stuff is bound pretty
closely to rmkdef ProcDef and it's more convenient to keep this out
of grammar.Common, it's defined here.
"""

import datetime

from gavo import base
from gavo.rscdef import common
from gavo.rscdef import rmkdef
from gavo.rscdef import rmkfuncs


class RowGenDef(rmkdef.RDFunction):
	"""is a rowmaker row generator.

	Row generators receive a dictionary (raw row) and return a generator
	spewing out new rows.

	Rowgens see the incoming row as row.
	"""
	name_ = "rowgen"

	def registerPredefined(self):
		registerRowGen(self.name, self)
	
	def getPredefined(self, name):
		return getRowGen(name)
	
	def _getFormalArgs(self):
		return "row, rowIter"

	def _getDefaultingCode(self):
		code = []
		for arg in self.args:
			if arg.content_:
				code.append("  %s = %s"%(arg.key, arg.content_))
			else:
				code.append("  %s = %s"%(arg.key, arg.default))
		return "\n".join(code)

	def _completeCall(self, actualArgs):
		return '%s(row, rowIter)'%(self.name)


def registerRowGen(name, function):
	global getRowGen
	function.rowGenName = name
	globals()[name] = function
	getRowGen = _buildResolver()
	

def _buildResolver():
	res = {}
	for ob in globals().values():
		if hasattr(ob, "rowGenName"):
			res[ob.rowGenName] = ob
	return lambda n: res[n]

getRowGen = _buildResolver()


base.parseFromString(RowGenDef, """
	<rowgen name="expandRowOnIndex" isGlobal="True">
	<arg key="startName"/>
	<arg key="endName"/>
	<arg key="indName"/>
	'''is a row processor that produces copies of rows based on integer indices.

	The idea is that sometimes rows have specifications like "Star 10
	through Star 100".  These are a pain if untreated.  A RowExpander
	could create 90 individual rows from this.

	A RowExpander has three arguments: The names of the nonterminals
	giving the beginning and the end of the range (both must be int-able
	strings), and the name of the nonterminal that the new index should 
	be assigned to.
	'''
	try:
		lowerInd = int(row[startName])
		upperInd = int(row[endName])
	except (ValueError, TypeError): # either one not given
		yield row
		return
	for ind in range(lowerInd, upperInd+1):
		newRow = row.copy()
		newRow[indName] = ind
		yield newRow
	</rowgen>
""")


base.parseFromString(RowGenDef, """
<rowgen name="expandDateRange" isGlobal="True">
	<arg key="dest">'curTime'</arg>
	<arg key="start"/>
	<arg key="end"/>
	<arg key="hrInterval">24</arg>
	'''is a row generator to expand time ranges.

	The finished dates are left in destination as datetime.datetime
	instances

	* dest -- name of the field we're writing into.
	* start -- the start date, as either a datetime object or a column ref.
	* end -- the end date
	* hrInterval -- a float literal specifying how many hours should be between
	  the generated timestamps
	'''
	def _parseTime(name, fieldName):
		try:
			val = row[name]
			if isinstance(val, datetime.datetime):
				return val
			elif isinstance(val, datetime.date):
				return datetime.datetime(val.year, val.month, val.day)
			else:
				return datetime.datetime(*time.strptime(val, "%Y-%m-%d")[:3])
		except Exception, msg:
			raise base.ValidationError("Bad date from %s (%s)"%(name,
				unicode(msg)), fieldName)

	stampTime = _parseTime(start, "start")
	endTime = _parseTime(end, "end")
	endTime = endTime+datetime.timedelta(hours=23)
	try:
		interval = datetime.timedelta(hours=float(hrInterval))
	except ValueError:
		raise base.ValidationError("Not a time interval: '%s'"%hrInterval,
			"hrInterval")
	while stampTime&lt;=endTime:
		newRow = row.copy()
		newRow[dest] = stampTime
		yield newRow
		stampTime = stampTime+interval
</rowgen>""")


base.parseFromString(RowGenDef, """
<rowgen name="expandComma" isGlobal="True">
	<arg key="srcField"/>
	<arg key="destField"/>
	'''is a row generator that reads comma seperated values from a
	field and returns one row with a new field for each of them.
	'''
	src = row[srcField]
	if src is not None and src.strip():
		for item in src.split(","):
			item = item.strip()
			if not item:
				continue
			newRow = row.copy()
			newRow[destField] = item
			yield newRow
</rowgen>""")
