"""
General event handling.

Basically, everything roughly classified as user interaction should go
through this module.  gavo.base, on input, creates an instance of 
EventDispatcher and installs it as base.ui.  The rest of the library
can then call methods of base.ui.

Clients can then register observers (probably derived from
base.observer.Observer) that subscribe to events and can display or 
log them in some form appropriate to the client.
"""

class DispatcherType(type):
	"""is a metaclass for dispatching of messages.

	Basically, you define methods called notify<whatever> in your class.
	For each of them, a subscribe<whatever> method is added.

	Then, when notify<whatever> is called, your defined method is called,
	and its result is then passed to all callbacks passed in through
	subscribe<whatever>.
	"""
	def __init__(cls, name, bases, dict):
		type.__init__(cls, name, bases, dict)
		cls._makeNotifiers(dict)

	def _makeNotifier(cls, name, callable):
		callbacks = []
		def notify(self, *args, **kwargs):
			res = callable(self, *args, **kwargs)
			for callback in callbacks:
				callback(res)
			return res
		def subscribe(self, callback):
			callbacks.append(callback)
		setattr(cls, "notify"+name, notify)
		setattr(cls, "subscribe"+name, subscribe)

	def _makeNotifiers(cls, dict):
		for name, val in dict.iteritems():
			if name.startswith("notify"):
				cls._makeNotifier(name[6:], val)


class EventDispatcher(object):
	__metaclass__ = DispatcherType

	def notifyException(self, exc):
		"""is called the exception object when an exception is caught.

		The exception will be propagated to the subscribers.  To make
		error messages from them, use the formatException function in this
		module.
		"""
		return exc


if __name__=="__main__":
	pass
