# Author: Francesco Pierfederici <fpierfed@eso.org>.
# Licensed under the Academic Free License version 2.0 (see LICENSE.txt). 

import binascii
from cStringIO import StringIO
import struct
from math import ceil
import sys


N_BYTES = {'boolean': 1,
           'bit': 1. / 8.,
           'unsignedByte': 1,
           'short': 2,
           'int': 4,
           'long': 8,
           'char': 1,
           'unicodeChar': 2,
           'float': 4,
           'double': 8,
           'floatComplex': 8,
           'doubleComplex': 16}

# http://docs.python.org/lib/module-struct.html
STRUCT_CODE = {'boolean': 'c',
               'bit': 'c',
               'unsignedByte': 'B',
               'short': 'h',
               'int': 'i',
               'long': 'q',
               'char': 'c',
               'unicodeChar': 'cc',
               'float': 'f',
               'double': 'd',
               'floatComplex': 'ff',
               'doubleComplex': 'dd'}

# http://www.ivoa.net/Documents/REC/VOTable/VOTable-20040811.html#primitives
PYTHON_TYPE = {'boolean': bool,
               'bit': int,
               'unsignedByte': int,
               'short': int,
               'int': int,
               'long': int,
               'char': str,
               'unicodeChar': unicode,
               'float': float,
               'double': float,
               'floatComplex': complex,
               'doubleComplex': complex}



# Gross workaround for bug encoding NaN in struct <2.5
if sys.hexversion<=0x20404f0 and sys.byteorder=='little':
    import re
    def swap4(val, pat=re.compile("(.)(.)(.)(.)")):
        return pat.sub(r"\4\3\2\1", val)
    def swap8(val, pat=re.compile("(.)(.)(.)(.)(.)(.)(.)(.)")):
        return pat.sub(r"\8\7\6\5\4\3\2\1", val)
    def decodeFloat(voType, length, encVal):
        if voType=="float":
            encVal = swap4(encVal)
        else:
            encVal = swap8(encVal)
        return struct.unpack(STRUCT_CODE[voType]*length, encVal)
    _workAroundStructBug = True
else:
    _workAroundStructBug = False




class GenericDecoder(object):
    """
    Base class for all decoder types.
    """
    def __init__(self, fields):
        """
        Constructor.
        
        Input
            fields: a list of Field instances
        """
        self._fieldFormat = [(f.datatype, f.arraysize) for f in fields]
        self._fields = fields
        return
    
    def decode(self, dataTree):
        """
        Main method for every decoder object. This is where the 
        action is. Since this implementation simply raises a 
        NotImplementedError exception, each subclass HAS to 
        override this method.
        """
        raise(NotImplementedError('Please, write your own decoder subclassing this class.'))
        return
    
    def _parseFieldInfo(self):
        """
        Given the FIELD information in self._fieldFormat, extract useful 
        information like the number of bytes and the dimensions of each FIELD.
        """
        fieldInfo = []
        for t, s in self._fieldFormat:
            # Try and understand if we have an array or not.
            numBytes = 0
            dimensions = []
            if(s.find('*') > -1):
                # Variable length array. The binary data is preceded by a 
                # 4-byte integer equal to the number of elements in the array.
                numBytes = None
                dimensions.append(None)
            elif(s.find('x') > -1):
                # Multi dimensional array. It might also be a variable length
                # array...
                dims = s.split('x')
                for dim in dims:
                    if(dim.find('*') > -1):
                        # Indefinite array
                        numBytes = None
                        dimensions.append(None)
                    else:
                        d = int(dim.strip())
                        dimensions.append(d)
                        if(numBytes != None):
                            numBytes += d * N_BYTES[t]
            else:
                # Simple scalar or 1-d array
                d = int(s.strip())
                dimensions = [d]
                numBytes = d * N_BYTES[t]
            # <-- end if
            fieldInfo.append((t, numBytes, dimensions))
        # <-- end for
        return(fieldInfo)




class TableDataDecoder(GenericDecoder):
    """
    Simple decoder class that handles the XML-based TABLEDATA 
    encoding.
    """
    def decode(self, dataTree):
        """
        Parse the XML-based TABLEDATA tree and return a Python list
        with the corresponding data types.
        
        Input
            dataTree: ElementTree object corresponding ro the 
                      XML data in the VOTable TABLEDATA element.
        
        Output
            A list of Python types corresponding to the input data.
        """
        # [(VO type, # bytes, (dim1, dim2, )), ]
        # if # bytes is None => variable-length array.
        fieldInfo = self._parseFieldInfo()
        
        # Now we are ready to do the real decoding.
        decodedData = self._parse(dataTree, fieldInfo)
        return(decodedData)
    
    def _parse(self, dataTree, fieldInfo):
        decoded = []
        
        for row in dataTree:
            decodedLine = []
            # Decode the data stream, one field at a time.
            for i in xrange(len(fieldInfo)):
                (voType, nBytes, dims) = fieldInfo[i]
                token = row[i].text
                
                # Create a skeleton decodedField where we will put the real 
                # values later.
                if(len(dims) > 1 or dims[0] > 1):
                    decodedField = []
                    isScalar = False
                else:
                    decodedField = None
                    isScalar = True
                
                # Now, derive the format of the field data and unpack token. 
                # Pay attention to complex numbers and unicode strings!
                for d in dims:
                    if(not token):
                        decodedField = None
                        continue
                    if('Complex' in voType):
                        # FIXME: handle complex numbers
                        raise(NotImplementedError('Implement complex numbers!'))
                    elif('unicode' in voType):
                        # FIXME: handle unicode strings
                        raise(NotImplementedError('Implement unicode strings!'))
                    else:
                        pType = PYTHON_TYPE[voType]
                        if(voType == 'char'):
                            # Strings! Remember that we could have a unicode 
                            # string even if the FIELD is not supposed to be 
                            # unicode (e.g. in surnames).
                            decodedField = token
                            continue
                        elif(isScalar):
                            # Scalars!
                            try:
                                decodedField = pType(token)
                            except ValueError:
                                decodedField = None
                        else:
                            # Arrays!
                            t = token.split()
                            for j in xrange(len(t)):
                                decodedField.append(pType(t[j]))
                        # <-- end if scalar|string|array
                    # <-- end if complex|unicode|other
                # <-- end for d in dims
                decodedLine.append(decodedField)
                self._fields[i].data.append(decodedField)
            # <-- end for i in xrange(len(fieldInfo))
            decoded.append(decodedLine)
        # <-- end for row in dataTree
        return(decoded)


class Done(Exception):
    pass


class StreamDecoder(GenericDecoder):
    """
    Decode VOTable STREAM data in binary format.
    """
    def decode(self, dataTree):
        """
        Decode the binary STRAM data using the FIELD information in 
        self._fieldFormat
        
        Input
            dataTree: ElementTree object corresponding ro the 
                      binary data in the VOTable STREAM element.
        
        Output
            A list of Python types corresponding to the input data.
        """
        # Fetch the binary data from the ASCII (encoded) string.
        rawData = self._decode(encoding=dataTree.get('encoding'), 
                               data=dataTree.text)
        
        # [(VO type, # bytes, (dim1, dim2, )), ]
        # if # bytes is None => variable-length array.
        fieldInfo = self._parseFieldInfo()
        
        # Now we are ready to do the real decoding.
        decodedData = self._unpack(rawData, fieldInfo)
        return(decodedData)
    
    def _decode(self, encoding, data):
        """
        Given an ecoding method and an encoded string, decode the 
        string and return the corresponding binary object.
        """
        # FIXME: Handle additional encoding styles.
        # Decode the stream.
        if(encoding == 'base64'):
            rawData = binascii.a2b_base64(data)
        elif(encoding == 'gzip'):
            warnings.warn('Unsupported data serialization scheme (gzip).',
                      Warning)
        elif(encoding == 'dynamic'):
            warnings.warn('Unsupported data serialization scheme (dynamic).',
                      Warning)
        elif(encoding == 'none'):
            warnings.warn('Unsupported data serialization scheme (none).',
                      Warning)
        else:
            warnings.warn('Unknown data serialization scheme (%s).' %(encoding),
                      Warning)
        return(rawData)
    
    def _unpack(self, data, fieldInfo):
        """
        Do the real, low level decoding of the binary stream.
        
        Input
            data:      the encoded data stream
            fieldInfo: [(VO type, # bytes, (dim1, dim2, )), ]
                       if # bytes is None => variable-length array and the 
                       corresponding dimN = None.
        Output
            A list of Python types corresponding to the input binary data.
        """
        encoded = StringIO(data)
        decoded = []
        
        try:
            while True:
                decodedLine = []
                # Decode the data stream, one field at a time.
                for i in xrange(len(fieldInfo)):
                    (voType, nBytes, dims) = fieldInfo[i]
                    # Create a skeleton decodedField where we will put the real 
                    # values later.
                    if(len(dims) > 1 or dims[0] > 1):
                        decodedField = []
                        isScalar = False
                    else:
                        decodedField = None
                        isScalar = True
                    
                    # Do we have a variable length array?
                    if(not nBytes):
                        # The first 4 bytes tell us how many elements
                        # we should read.
                        # FIXME: make sure that this is unsigned long
                        token = encoded.read(4)
                        if(len(token) < 4):
                            if i==0:
                                raise Done()
                            else:
                                raise SyntaxError("Premature end of stream"
                                    " reading header for field %d"%i)
                        nElements = struct.unpack('!L', token)[0]
                        nBytes = int(ceil(nElements * 
                                           N_BYTES[voType]))
                        # Fix dims
                        left = nElements
                        for j in xrange(len(dims)):
                            if(left < 0):
                                raise(SyntaxError('Error in specifying array dimensions.'))
                            if(dims[j] == None):
                                dims[j] = left
                            else:
                                left -= dims[j]
                        # <-- end for
                    # <-- end if
                    token = encoded.read(nBytes)
                    if(len(token) < nBytes):
                        # Not enough data!
                        if i==0:
                            raise Done()
                        else:
                            raise SyntaxError("Premature end of stream reading"
                                " data for field %d"%i)
                    
                    # Now, derive the format of the field data and 
                    # unpack token. Pay attention to complex numbers
                    # and unicode strings!
                    for d in dims:
                        if(not token):
                            decodedLine.append(None)
                            continue
                        if('Complex' in voType):
                            # FIXME: handle complex numbers
                            raise(NotImplementedError('Implement complex numbers!'))
                        elif('unicode' in voType):
                            # FIXME: handle unicode strings
                            raise(NotImplementedError('Implement unicode strings!'))
                        else:
                            if(_workAroundStructBug and (voType=='float'
                                    or voType=='double')):
                                t = decodeFloat(voType, d, token)
                            else:
                                if(voType == 'char'):
                                    format = '%ds' % (nBytes)
                                    isScalar = True
                                else:
                                    format = STRUCT_CODE[voType] * d
                                try:
                                    t = struct.unpack("!"+format, token)
                                except Exception, msg:
                                    raise(SyntaxError('Malformed binary stream (fmt: %s, token: %s -- %s).' % (format, repr(token), msg)))
                            
                            if(isScalar):
                                # Scalars and strings!
                                decodedField = PYTHON_TYPE[voType](t[0])
                            else:
                                # Arrays!
                                for j in xrange(len(t)):
                                    decodedField.append(PYTHON_TYPE[voType](t[j]))
                            # <-- end if scalar|array
                        # <-- end if complex|unicode|other
                    # <-- end for d in dims
                    decodedLine.append(decodedField)
                    self._fields[i].data.append(decodedField)
                # <-- end for (voType, nBytes, dims) in fieldInfo
                print ">>>>>>", decodedLine
                decoded.append(decodedLine)
        except Done:
            pass
        encoded.close()
        return(decoded)












# vim:sta:sw=4:et:
