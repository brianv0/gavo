"""
Common functions and classes for gavo web interfaces.

(Much of what would belong here currently lives within querulator.
We'll move the stuff as we see fit...)
"""

def getSubmitButtons():
	"""returns HTML for submit buttons for the various formats we can do.
	"""
	return ('<p class="submitbuttons">'
		'<input type="submit" value="Table as HTML" name="submit">\n'
		'\n<input type="submit" value="Table as VOTable"'
		' name="submit-votable">\n'
		'</p>')
