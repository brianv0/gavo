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

class Constraints:
	"""is a set of constraints that, on evaluation, are combined in a
	conjunction ("AND").
	"""
	def __init__(self):
		self.constraints = []
	
	def addConstraint(self, constraint):
		self.constraints.append(constraint)
	
	def check(self, rowdict, record):
		for constraint in self.constraints:
			if not constraint.check(rowdict, record):
				return False
		return True


class Constraint:
	"""is a (set of) condition(s) that must be satisfied if a record
	is to be accepted for inclusion in the table.

	All conditions within a constraint are interpreted as a disjunction ("OR").

	To be flexible in the conditions specified, conditions can work on
	both the rowdict and the record.  That is why the check method needs
	both of these.  Concrete conditions will usually need only one of
	them -- maybe we should separate GrammarConditions and SemanticsConditions?
	Bah, too complicated for now.
	"""
	def __init__(self, name):
		self.conditions = []
		self.name = name

	def __repr__(self):
		return "<Constraint %s>"%self.name

	def addCondition(self, condition):
		self.conditions.append(condition)
	
	def check(self, rowdict, record):
		if not self.conditions:
			return True
		for cond in self.conditions:
			if cond.check(rowdict, record):
				return True
		return False


class _Condition:
	"""is an abstract superclass for all conditions.

	A condition has to define a method check taking a rowdict (with
	preterminals) and a record (a dictionary ready for import into the
	database).
	"""
	pass


class _PreterminalNotEqualCondition(_Condition):
	"""is a condition that a certain element of rowdict does not have a 
	specified value.
	"""
	def __init__(self, name, value):
		self.name, self.value = name, value
	
	def check(self, rowdict, record):
		if rowdict.get(self.name)==self.value:
			return False
		else:
			return True


_conditionsRegistry = {
	"preterminalNotEqual": (_PreterminalNotEqualCondition, ["name", "value"]),
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
