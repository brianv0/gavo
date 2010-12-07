"""
Resource mixins.
"""

import warnings

from gavo import base
from gavo.base import activetags
from gavo.rscdef import procdef


class ProcessEarly(procdef.ProcApp):
	"""A code fragment run by the mixin machinery when the structure
	being worked on is being finished.

	Access the structure mixed in as "substrate".
	"""
	name_ = "processEarly"
	formalArgs = "substrate"


class ProcessLate(procdef.ProcApp):
	"""A code fragment run by the mixin machinery when the parser parsing
	everything exits.

	Access the structure mixed in as "substrate", the root structure of
	the whole parse tree as root, and the context that is just about
	finishing as context.
	"""
	name_ = "processLate"
	formalArgs = "substrate, root, context"


class MixinPar(procdef.RDParameter):
	"""A parameter definition for mixins.  
	
	The (optional) body provides a default for the parameter.
	"""
	name_ = "mixinPar"
	_expr = base.DataContent(description="The default for the parameter.",
		copyable=True, strip=True, null=None, default=base.NotGiven)

	def validate(self):
		self._validateNext(MixinPar)
		if len(self.name)<2:
			raise base.LiteralParseError("name", self.name, hint="Names of"
				" mixin parameters must have at least two characters (since"
				" they are exposed as macros")


class MixinDef(activetags.ReplayBase):
	"""A definition for a resource mixin.

	Resource mixins are resource descriptor fragments typically rooted
	in tables (though it's conceivable that other structures could
	grow mixin attributes as well).

	They are used to define and implement certain behaviours components of
	the DC software want to see:

	- products want to be added into their table, and certain fields are required
		within tables describing products
	- tables containing positions need some basic machinery to support scs.
	- siap needs quite a bunch of fields

	Mixins consist of events that are played back on the structure
	mixing in before anything else happens (much like original) and
	two procedure definitions, viz, processEarly and processLate.
	These can access the structure that has the mixin as substrate.

	processEarly is called as part of the substrate's completeElement
	method.  processLate is executed just before the parser exits.  This
	is the place to fix up anything that uses the table mixed in.  Note,
	however, that you should be as conservative as possible here -- you
	should think of DC structures as immutable as long as possible.

	Programmatically, you can check if a certain table mixes in 
	something by calling its mixesIn method.
	"""
	name_ = "mixinDef"

	_doc = base.UnicodeAttribute("doc", description="Documentation for"
		" this mixin", strip=False)
	_events = base.StructAttribute("events", 
		childFactory=activetags.EmbeddedStream,
		description="Events to be played back into the structure mixing"
		" this in", copyable=True)
	_processEarly = base.StructAttribute("processEarly", 
		default=None, 
		childFactory=ProcessEarly,
		description="Code executed at element fixup.")
	_processLate = base.StructAttribute("processLate", 
		default=None, 
		childFactory=ProcessLate,
		description="Code executed resource fixup.")
	_pars = base.StructListAttribute("pars",
		childFactory=MixinPar,
		description="Parameters available for this mixin.")

	def _defineMacros(self, fillers):
		self.macroExpansions = {}
		for p in self.pars:
			if p.name in fillers:
				self.macroExpansions[p.name] = fillers.pop(p.name)
			elif p.content_ is base.NotGiven:
				raise base.StructureError("Mixin parameter %s mandatory"%p.name)
			else:
				self.macroExpansions[p.name] = p.content_
		if fillers:
			raise base.StructureError("The attribute(s) %s is/are not allowed"
				" on this mixin"%(",".join(fillers)))

	def execMacro(self, macName, args):
		if args:
			raise base.MacroError(
				"Invalid macro arguments to \\%s: %s"%(macName, args), macName,
				hint="Mixin macros never take any arguments.  Did you forget"
				" a second backslash?")
		try:
			return self.macroExpansions[macName]
		except KeyError:
			raise base.MacroError(
				"No macro \\%s available in this mixin."%(
					macName), macName)

	def applyTo(self, destination, ctx, fillers={}):
		"""replays the stored events on destination and arranges for processEarly
		and processLate to be run.
		"""
		self._defineMacros(fillers)
		self.replay(self.events.events, destination, ctx)
		if self.processEarly is not None:
			self.processEarly.compile(destination)(destination)
		if self.processLate is not None:
			def procLate(rootStruct, parseContext):
				self.processLate.compile(destination)(
					destination, rootStruct, parseContext)
			ctx.addExitFunc(procLate)

	def applyToFinished(self, destination):
		"""applies the mixin to an object already parsed.

		Late callbacks will only be executed if destination has an rd
		attribute; if that is the case, this rd's idmap will be amended
		with anything the mixin comes up with.
		"""
		rd = None
		if hasattr(destination, "rd"):
			rd = destination.rd

		ctx = base.ParseContext()
		if rd is not None:
			ctx.idmap = destination.rd.idmap
		self.applyTo(destination, ctx)
		
		if rd is not None:
			ctx.runExitFuncs(rd)


class _MixinParser(base.Parser):
	"""A parser for structured mixin references.

	These can contain attribute definitions for any parameter of the
	mixin referenced.
	"""
	def __init__(self, parent, parentAttr):
		self.parent, self.parentAttr = parent, parentAttr
		self.fillers = {}
		self.curName = None  # this is non-None while parsing a child element
	
	def start_(self, ctx, name, value):
		if self.curName is not None:
			raise base.StructureError("%s elements cannot have %s children in"
				" mixins."%(self.curName, name))
		self.curName = name
		return self
	
	def value_(self, ctx, name, value):
		if name=="content_":
			if self.curName:
				self.fillers[self.curName] = value
			else:
				self.fillers["mixin name"] = value.strip()
		else:
			self.fillers[name] = value
		return self
	
	def end_(self, ctx, name, value):
		if self.curName:  # end parsing parameter binding
			self.curName = None
			return self
		else: # end of mixin application, run the mixin and hand control back to
		      # mixin parent
			if "mixin name" not in self.fillers:
				raise base.StructureError("Empty mixin children not allowed")
			mixinRef = self.fillers.pop("mixin name")
			self.parentAttr.feed(ctx, self.parent, mixinRef, fillers=self.fillers)
			return self.parent


class MixinAttribute(base.SetOfAtomsAttribute):
	"""An attribute defining a mixin.

	This currently is only offered on tables, though in principle we could
	have it anywhere now, though we might want some compatibility checking
	then.

	This is never copyable since this would meaning playing the same
	stuff into an object twice.

	This means trouble for magic scripts (in particular processLate); e.g.,
	if you copy a table mixing in products, the data element for that table
	will not receive the product table.  Goes to show the whole process
	mess is ugly and needs a good idea.
	"""
	def __init__(self, **kwargs):
		kwargs["itemAttD"] = base.UnicodeAttribute("mixin", strip=True)
		kwargs["description"] = kwargs.get("description", 
			"Reference to a mixin this table should contain; you can"
			" give mixin parameters as attributes or children.")
		kwargs["copyable"] = False
		base.SetOfAtomsAttribute.__init__(self, "mixin", **kwargs)

	def feed(self, ctx, instance, mixinRef, fillers={}):
		# this is called when mixin is used a plain attribute
		mixin = ctx.resolveId(mixinRef, instance=instance, forceType=MixinDef)
		mixin.applyTo(instance, ctx, fillers)
		base.SetOfAtomsAttribute.feed(self, ctx, instance, mixinRef)

	# no need to override feedObject: On copy and such, replay has already
	# happened.

	def iterParentMethods(self):
		def mixesIn(instance, mixinRef):
			return mixinRef in instance.mixins
		yield "mixesIn", mixesIn

	def makeUserDoc(self):
		return ("A mixin reference, typically to support certain protocol."
			"  See Mixins_.")
	
	def create(self, parent, ctx, name):
		# since mixins may contain parameters, we need a custom parser
		# when mixin is a child.
		return _MixinParser(parent, self)

