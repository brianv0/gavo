# Author: Francesco Pierfederici <fpierfed@eso.org>.
# Licensed under the Academic Free License version 2.0 (see LICENSE.txt). 
__version__ = '1.0a1'
__all__ = ['Parser', 'Writer', 'parse', 'write']

from Parser import Parser
from Writer import Writer

# Define the convenience functions parse and write
def parse(fileName):
    return(Parser(fileName).votable)

def write(votable, fileName):
    return(Writer().write(votable, fileName))
