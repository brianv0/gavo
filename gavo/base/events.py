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
		cls.eventTypes = []
		cls._makeNotifiers(dict)

	def _makeNotifier(cls, name, callable):
		cls.eventTypes.append(name)
		def notify(self, *args, **kwargs):
			res = callable(self, *args, **kwargs)
			for callback in self.callbacks[name]:
				callback(self, res)
			return res
		def subscribe(self, callback):
			self.callbacks[name].append(callback)
		setattr(cls, "notify"+name, notify)
		setattr(cls, "subscribe"+name, subscribe)

	def _makeNotifiers(cls, dict):
		for name, val in dict.iteritems():
			if name.startswith("notify"):
				cls._makeNotifier(name[6:], val)


class EventDispatcher(object):
	__metaclass__ = DispatcherType

	def __init__(self):
		self.callbacks = dict((name, []) for name in self.eventTypes)
		self.sourceStack = [None]
		self.curSource = None
		self.totalShippedOut = 0
		self.totalRead = 0
		self.lastRow = None

	def subscribe(self, evName, callback):
		self.callbacks[evName].append(callback)

	def notifyException(self, exc):
		"""is called the exception object when an exception is caught.

		The exception will be propagated to the subscribers.  To make
		error messages from them, use the formatException function in this
		module.
		"""
		return exc

	def notifyNewSource(self, sourceToken):
		"""is called when a new source is being operated on.

		The callbacks are passed some, hopefully useful, token string.  For
		file source, this is the file name, otherwise we try to make up
		something.

		As side effects, the curSource attribute is set to this value.
		"""
		if isinstance(sourceToken, basestring):
			sourceName = sourceToken
		else:
			sourceName = repr(sourceToken)[:40]
		self.curSource = sourceName
		self.sourceStack.append(sourceToken)
		return sourceName

	def notifySourceError(self):
		"""is called when a parse error occurred in a source.

		The callbacks are passed the name of the failing source.
		"""
		lastSource = self.sourceStack.pop()
		self.curSource = self.sourceStack[-1]
		return lastSource

	def notifySourceFinished(self):
		"""is called when a source file has been processed.

		The curSource attribute is updated, and its old value is propagated
		to the callbacks.
		"""
		lastSource = self.sourceStack.pop()
		self.curSource = self.sourceStack[-1]
		return lastSource
	
	def notifyShipout(self, numItems):
		"""is called when certain table implementations store items.

		The number of items is passed on to the callbacks.  As a side effect,
		the instance variable totalShippedOut is adjusted.

		InMemoryTables don't call this right now and probably never will.
		"""
		self.totalShippedOut += numItems
		return numItems
	
	def notifyIncomingRow(self, row):
		"""is called when certain grammars yield a row to the DC's belly.

		The callbacks receive a reference to the row.  As a side effect,
		the instance variable totalRead is bumped up, and lastRow becomes
		the row passed in.

		To support this, RowIterators have to call this method in their
		_iterRows.  Most will do, DictlistGrammars, e.g., don't.
		"""
		self.totalRead += 1
		self.lastRow = row
		return row


if __name__=="__main__":
	pass
