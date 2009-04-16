"""
User-defined cores

XXX TODO: Once we have an event recording and replaying infrastructure,
revise this to have events before module replayed.
"""

import os

from gavo import base
from gavo import utils
from gavo.svcs import core


class ModuleAttribute(base.UnicodeAttribute):
# XXX TODO: this is a bad hack since it assumes id on instance has already
# been set.  See above on improving all this using an event replay framework.
	typeDesc = "resdir-relative path to a module; no extension is allowed"

	def feed(self, ctx, instance, modName):
		modName = os.path.join(instance.rd.resdir, modName)
		userModule, _ = utils.loadPythonModule(modName)
		newCore = userModule.Core(instance.parent)
		ctx.idmap[instance.id] = newCore
		raise base.Replace(newCore)


class CustomCore(core.Core):
	"""A wrapper around a core defined in a module.

	This core lets you write your own cores in modules.

	The module must define a class Core.  When the custom core is
	encountered, this class will be instanciated and will be used
	instead of the CustomCore, so your code should probably inherit 
	core.Core.
	"""
	name_ = "customCore"

	_module = ModuleAttribute("module", default=base.Undefined,
		description="Path to the module containing the core definition.")

core.registerCore(CustomCore)
