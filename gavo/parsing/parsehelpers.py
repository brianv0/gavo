"""
This module contains utility classes for resource parsing.
"""

class RowFunction:
	"""is something that operates on table rows.

	Examples for this are Macros and RowProcessors.

	The addArgument(name, src, val)
	method adds a named argument.  If src is given, the value of
	the argument is that taken from the corresponding field in the
	record, otherwise the argument is constant val.

	When given a record, _buildArgDict fills out a dictionary of the
	required arguments.  Actually doing something with it is left to
	the derived classes.
	"""

	def __init__(self, fieldComputer, argTuples=[]):
		self.fieldComputer = fieldComputer
		self.colArguments = []
		self.constants = []
		self.addArguments(argTuples)

	@staticmethod
	def getName():
		return "Uncallable abstract row function"

	def addArgument(self, argName, srcName=None, value=None):
		"""adds an argument that is filled from a field of current record.

		There are two calling conventions here for historical reasons:
		Either you give the name of the argument, the name of the source
		field and a constant value separately (with None for the source
		field to use value), or you pass one tuple with the complete information.
		"""
		if isinstance(argName, tuple):
			argName, srcName, value = argName
		if srcName:
			self.colArguments.append((argName.encode("ascii"), srcName))
		else:
			self.constants.append((argName.encode("ascii"), value))

	def addArguments(self, argTuples):
		"""adds arguments from the sequence argTuples.

		An element of argTriples has to be valid as arguments for the
		addArgument method.
		"""
		for args in argTuples:
			self.addArgument(*args)
	
	def _buildArgDict(self, rowdict):
		args = {}
		for name, src in self.colArguments:
			args[name] = rowdict.get(atExpand(src, 
				rowdict, self.fieldComputer))
		for name, val in self.constants:
			args[name] = atExpand(val, rowdict, self.fieldComputer)
		return args


def atExpand(val, rowdict, fieldComputer):
	"""expands computed fields.

	If val is a string and starts with an @, the rest is
	interpreted as a field computer function, the value of
	which is returned, unless val starts with two @ signs,
	in which case the first of these ats is stripped (poor
	man's escaping).  Other values are returned unchanged.
	"""
	if not isinstance(val, basestring):
		return val
	if val.startswith("@@"):
		return val[1:]
	if val.startswith("@"):
		desc = val[1:].split(",")
		if not desc[-1].strip():
			del desc[-1]
		return fieldComputer.compute(desc[0], rowdict, *desc[1:])
	return val

