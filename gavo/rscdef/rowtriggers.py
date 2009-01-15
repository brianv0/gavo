"""
Framework for ignoring dictionaries based on various conditions.
"""

from gavo import base


class TriggerPulled(base.Error):
	def __init__(self, msg, triggerName):
		base.Error.__init__(self, msg)
		self.triggerName = triggerName


_triggerRegistry = {}
def registerTrigger(trigger):
	_triggerRegistry[trigger.name_] = trigger
	return trigger

def getTrigger(name):
	return _triggerRegistry[name]


class TriggerBase(base.Structure):
	"""is an abstract base class for triggers.

	Basically, a trigger can be called and has to return True when it fires,
	false otherwise.  So, you generally want to override its __call__ method.
	All __call__ methods have the constant signature __call__(dict) -> bool.
	"""
	name_ = "trigger"

	_name = base.UnicodeAttribute("name", default="unnamed",
		description="A name that should help the user figure out what trigger"
			" caused some condition to fire.", copyable=True)


class KeyedCondition(TriggerBase):
	"""is an abstract base class for triggers firing on a single key.
	"""
	_key = base.UnicodeAttribute("key", default=base.Undefined,
		description="Key to check", copyable=True)


class KeyPresent(KeyedCondition):
	"""is a trigger firing if a certain key is present in the dict.
	"""
	name_ = "keyPresent"

	def __call__(self, dict):
		return self.key in dict

registerTrigger(KeyPresent)


class KeyMissing(KeyedCondition):
	"""is a trigger firing if a certain key is missing in the dict.
	"""
	name_ = "keyMissing"

	def __call__(self, dict):
		return self.key not in dict

registerTrigger(KeyMissing)


class KeyIs(KeyedCondition):
	"""is a trigger firing when key is value.

	Only strings can be checked in this way.  Missing keys are ok.
	"""
	name_ = "keyIs"

	_value = base.UnicodeAttribute("value", default=base.Undefined,
		description="The string value to fire on", copyable=True)

	def __call__(self, dict):
		return self.key in dict and dict[self.key]==self.value

registerTrigger(KeyIs)


class TriggerAttribute(base.StructListAttribute):
	"""is an attribute containing a list triggers.
	"""
	def __init__(self, name, description, **kwargs):
		base.StructListAttribute.__init__(self, name, childFactory=TriggerBase,
			description=description, **kwargs)

	def create(self, structure, name):
		return getTrigger(name)(structure)


class ConditionBase(TriggerBase):
	"""is an abstract base for anything that can incorporate the
	basic triggers.

	If you don't override __call__, the basic operation is or-ing together
	all embedded conditions.
	"""
	_triggers = TriggerAttribute("triggers",
		description="A placeholder for concrete triggers.", copyable=True)

	def getDynamicAttribute(self, name):
		try:
			triggerClass = getTrigger(name)
		except KeyError:
			return
		self.managedAttrs[name] = self._triggers
		return self._triggers
	
	def __call__(self, dict):
		for t in self.triggers:
			if t(dict):
				return True
		return False


class Not(ConditionBase):
	"""is a condition inverting its truth value.

	The embedded triggers are still or-ed together.
	"""
	name_ = "not"

	def __call__(self, dict):
		return not ConditionBase.__call__(self, dict)

registerTrigger(Not)


class And(ConditionBase):
	name_ = "and"

	def __call__(self, dict):
		for t in self.triggers:
			if not t(dict):
				return False
		return True

registerTrigger(And)


class IgnoreOn(ConditionBase):
	"""is a condition that is true when one of the embedded conditions is
	true.

	In addition to ConditionBase, there's an attribute bail.  If it's
	true, ignored rows aren't ignored but will raise a TriggerPulled
	error.
	"""
	name_ = "ignoreOn"
	_bail = base.BooleanAttribute("bail", default=False, description=
		"Bail out when the condition is met?")

	def __call__(self, row):
		conditionMet = ConditionBase.__call__(self, row)
		if self.bail and conditionMet:
			raise TriggerPulled("Trigger %s satisfied and set to bail"%self.name,
				self.name)
		return conditionMet
