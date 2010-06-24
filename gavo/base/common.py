def logOldExc(exc):
	"""logs the mutation of the currently handled exception to exc.

	This just does a notifyExceptionMutation, but code in base needs
	this special crutch since base.ui does not exist when they get
	imported (it's only created by base.__init__.

	So, for errors we import gavo just like anyone else, but at
	runtime.
	"""
	from gavo.base import ui
	return ui.logOldExc(exc)



