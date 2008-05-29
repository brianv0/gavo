"""
This module contains code dealing with constraints on rowdicts and
records.

The constraints implement conditions which rowdicts or records have to
meet to be included into a table.

Conditions can either refer to rowdicts (spit out by the grammar)
or to records (spit out by the semantics) -- or both (which should be
uncommon).  You *may* pass in whatever you like for rowdict and record
(including None), but if a condition needs information from what you
left out, it will bomb out.

Only construct Conditions via the factory function makeCondition.
"""

import gavo

class SkipRecord(gavo.Error):
	"""is raised when a non-fatal constraint is violated.
	"""
	def __init__(self, msg, constraint):
		gavo.Error.__init__(self, msg)
		self.constraint = constraint


class Constraints:
	"""is a set of constraints that, on evaluation, are combined in a
	conjunction ("AND").
	"""
	def __init__(self, fatal="False"):
		self.fatal = fatal
		self.constraints = []
	
	def addConstraint(self, constraint):
		self.constraints.append(constraint)
	
	def check(self, aDict):
		for constraint in self.constraints:
			if not constraint.check(aDict):
				if self.fatal:
					raise gavo.ValidationError("Constraint violated -- %s"%
							constraint.getExpl(),
						fieldName=constraint.name, record=aDict)
				else:
					raise SkipRecord("Constraint violated -- %s"%constraint.getExpl(), 
						constraint.name)
		return True


class Constraint:
	"""is a (set of) condition(s) that must be satisfied if a dictionary
	is to be accepted for inclusion in a table.

	All conditions within a constraint are interpreted as a disjunction ("OR").
	"""
	def __init__(self, name):
		self.conditions = []
		self.name = name

	def __repr__(self):
		return "<Constraint %s>"%self.name

	def getExpl(self):
		return ", ".join(c.expl for c in self.conditions)

	def addCondition(self, condition):
		self.conditions.append(condition)
	
	def check(self, aDict):
		if not self.conditions:
			return True
		for cond in self.conditions:
			if cond.check(aDict):
				return True
		return False


class _Condition:
	"""is an abstract superclass for all conditions.

	A condition has to define a method check taking a rowdict (with
	preterminals) and a record (a dictionary ready for import into the
	database).
	"""
	pass


class _ValueNotEqualCondition(_Condition):
	"""is a condition that a certain element of rowdict does not have a 
	specified value.
	"""
	expl = "Forbidden value found"

	def __init__(self, name, value):
		self.name, self.value = name, value
	
	def check(self, aDict):
		if aDict.get(self.name)==self.value:
			return False
		else:
			return True


class _KeyPresentCondition(_Condition):
	"""is a condition that a certain value is present in a preterminal.
	"""
	expl = "Required key not present"

	def __init__(self, name):
		self.name = name

	def check(self, aDict):
		return aDict.has_key(self.name)


_conditionsRegistry = {
	"valueNotEqual": (_ValueNotEqualCondition, ["name", "value"]),
	"keyPresent": (_KeyPresentCondition, ["name"]),
}

def makeCondition(attrs):
	"""is a factory function for conditions.

	It takes a dictionary-like object containing keys for at least type
	and all items mentioned in the second element of the value for type in
	_conditionsRegistry.
	"""
	cls, args = _conditionsRegistry[attrs["type"]]
	argdict = {}
	for arg in args:
		argdict[arg] = attrs[arg]
	return cls(**argdict)


if __name__=="__main__":
	print "To be done."
