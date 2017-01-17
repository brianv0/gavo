"""
Tests for the formal forms code.  Most of this is taken from formal's
source tree and thus is covered by the liberal license imp/formal/LICENSE.
"""

#c Copyright 2008-2017, the GAVO project
#c
#c This program is free software, covered by the GNU GPL.  See the
#c COPYING file in the source distribution.


from datetime import date, time
import decimal
import re
import unittest

from gavo.helpers import testhelpers

from gavo.imp import formal
from gavo.imp.formal import converters, validation, types, util



class TestConverters(unittest.TestCase):
    
    def test_null(self):
        c = converters.NullConverter(None)
        self.assertEquals(c.fromType('foo'), 'foo')
        self.assertEquals(c.toType('foo'), 'foo')
        
    def test_integerToString(self):
        c = converters.IntegerToStringConverter(None)
        self.assertEquals(c.fromType(None), None)
        self.assertEquals(c.fromType(1), '1')
        self.assertEquals(c.fromType(0), '0')
        self.assertEquals(c.fromType(-1), '-1')
        self.assertEquals(c.toType(''), None)
        self.assertEquals(c.toType(' '), None)
        self.assertEquals(c.toType('1'), 1)
        self.assertEquals(c.toType('0'), 0)
        self.assertEquals(c.toType('-1'), -1)
        self.assertRaises(validation.FieldValidationError, c.toType, '1.1')
        self.assertRaises(validation.FieldValidationError, c.toType, 'foo')

    def test_floatToString(self):
        c = converters.FloatToStringConverter(None)
        self.assertEquals(c.fromType(None), None)
        self.assertEquals(c.fromType(1), '1')
        self.assertEquals(c.fromType(0), '0')
        self.assertEquals(c.fromType(-1), '-1')
        self.assertEquals(c.fromType(1.5), '1.5')
        self.assertEquals(c.toType(''), None)
        self.assertEquals(c.toType(' '), None)
        self.assertEquals(c.toType('1'), 1)
        self.assertEquals(c.toType('0'), 0)
        self.assertEquals(c.toType('-1'), -1)
        self.assertEquals(c.toType('-1.5'), -1.5)
        self.assertRaises(validation.FieldValidationError, c.toType, 'foo')
        
    def test_decimalToString(self):
        from decimal import Decimal
        c = converters.DecimalToStringConverter(None)
        self.assertEquals(c.fromType(None), None)
        self.assertEquals(c.fromType(Decimal("1")), '1')
        self.assertEquals(c.fromType(Decimal("0")), '0')
        self.assertEquals(c.fromType(Decimal("-1")), '-1')
        self.assertEquals(c.fromType(Decimal("1.5")), '1.5')
        self.assertEquals(c.toType(''), None)
        self.assertEquals(c.toType(' '), None)
        self.assertEquals(c.toType('1'), Decimal("1"))
        self.assertEquals(c.toType('0'), Decimal("0"))
        self.assertEquals(c.toType('-1'), Decimal("-1"))
        self.assertEquals(c.toType('-1.5'), Decimal("-1.5"))
        self.assertEquals(c.toType('-1.863496'), Decimal("-1.863496"))
        self.assertRaises(validation.FieldValidationError, c.toType, 'foo')
        
    def test_booleanToString(self):
        c = converters.BooleanToStringConverter(None)
        self.assertEquals(c.fromType(False), 'False')
        self.assertEquals(c.fromType(True), 'True')
        self.assertEquals(c.fromType(None), None)
        self.assertEquals(c.toType('False'), False)
        self.assertEquals(c.toType('True'), True)
        self.assertEquals(c.toType(''), None)
        self.assertEquals(c.toType('  '), None)
        self.assertRaises(validation.FieldValidationError, c.toType, 'foo')
        
    def test_dateToString(self):
        c = converters.DateToStringConverter(None)
        self.assertEquals(c.fromType(date(2005, 5, 6)), '2005-05-06')
        self.assertEquals(c.fromType(date(2005, 1, 1)), '2005-01-01')
        self.assertEquals(c.toType(''), None)
        self.assertEquals(c.toType(' '), None)
        self.assertEquals(c.toType('2005-05-06'), date(2005, 5, 6))
        self.assertEquals(c.toType('2005-01-01'), date(2005, 1, 1))
        self.assertRaises(validation.FieldValidationError, c.toType, 'foo')
        self.assertRaises(validation.FieldValidationError, c.toType, '2005')
        self.assertRaises(validation.FieldValidationError, c.toType, '01/01/2005')
        self.assertRaises(validation.FieldValidationError, c.toType, '01-01-2005')
        
    def test_timeToString(self):
        c = converters.TimeToStringConverter(None)
        self.assertEquals(c.fromType(time(12, 56)), '12:56:00')
        self.assertEquals(c.fromType(time(10, 12, 24)), '10:12:24')
        self.assertEquals(c.toType(''), None)
        self.assertEquals(c.toType(' '), None)
        self.assertEquals(c.toType('12:56'), time(12, 56))
        self.assertEquals(c.toType('12:56:00'), time(12, 56))
        self.assertEquals(c.toType('10:12:24'), time(10, 12, 24))
        self.assertRaises(validation.FieldValidationError, c.toType, 'foo')
        self.assertRaises(validation.FieldValidationError, c.toType, '10')
        self.assertRaises(validation.FieldValidationError, c.toType, '10-12')
        
    def test_dateToTuple(self):
        c = converters.DateToDateTupleConverter(None)
        self.assertEquals(c.fromType(date(2005, 5, 6)), (2005, 5, 6))
        self.assertEquals(c.fromType(date(2005, 1, 1)), (2005, 1, 1))
        self.assertEquals(c.toType((2005, 5, 6)), date(2005, 5, 6))
        self.assertEquals(c.toType((2005, 1, 1)), date(2005, 1, 1))
        self.assertRaises(validation.FieldValidationError, c.toType, ('foo'))
        self.assertRaises(validation.FieldValidationError, c.toType, (2005,))
        self.assertRaises(validation.FieldValidationError, c.toType, (2005,10))
        self.assertRaises(validation.FieldValidationError, c.toType, (1, 1, 2005))

class TestForm(unittest.TestCase):

    def test_fieldName(self):
        form = formal.Form()
        form.addField('foo', formal.String())
        self.assertRaises(ValueError, form.addField, 'spaceAtTheEnd ', formal.String())
        self.assertRaises(ValueError, form.addField, 'got a space in it', formal.String())


class TestValidators(unittest.TestCase):

    def testHasValidator(self):
        t = formal.String(validators=[validation.LengthValidator(max=10)])
        self.assertEquals(t.hasValidator(validation.LengthValidator), True)

    def testRequired(self):
        t = formal.String(required=True)
        self.assertEquals(t.hasValidator(validation.RequiredValidator), True)
        self.assertEquals(t.required, True)


class TestCreation(unittest.TestCase):

    def test_immutablility(self):
        self.assertEquals(formal.String().immutable, False)
        self.assertEquals(formal.String(immutable=False).immutable, False)
        self.assertEquals(formal.String(immutable=True).immutable, True)

    def test_immutablilityOverride(self):
        class String(formal.String):
            immutable = True
        self.assertEquals(String().immutable, True)
        self.assertEquals(String(immutable=False).immutable, False)
        self.assertEquals(String(immutable=True).immutable, True)


class TestValidate(unittest.TestCase):

    def testString(self):
        self.assertEquals(formal.String().validate(None), None)
        self.assertEquals(formal.String().validate(''), None)
        self.assertEquals(formal.String().validate(' '), ' ')
        self.assertEquals(formal.String().validate('foo'), 'foo')
        self.assertEquals(formal.String().validate(u'foo'), u'foo')
        self.assertEquals(formal.String(strip=True).validate(' '), None)
        self.assertEquals(formal.String(strip=True).validate(' foo '), 'foo')
        self.assertEquals(formal.String(missing='bar').validate('foo'), 'foo')
        self.assertEquals(formal.String(missing='bar').validate(''), 'bar')
        self.assertEquals(formal.String(strip=True, missing='').validate(' '), '')
        self.assertEquals(formal.String(missing='foo').validate('bar'), 'bar')
        self.assertRaises(formal.FieldValidationError, formal.String(required=True).validate, '')
        self.assertRaises(formal.FieldValidationError, formal.String(required=True).validate, None)

    def testInteger(self):
        self.assertEquals(formal.Integer().validate(None), None)
        self.assertEquals(formal.Integer().validate(0), 0)
        self.assertEquals(formal.Integer().validate(1), 1)
        self.assertEquals(formal.Integer().validate(-1), -1)
        self.assertEquals(formal.Integer(missing=1).validate(None), 1)
        self.assertEquals(formal.Integer(missing=1).validate(2), 2)
        self.assertRaises(formal.FieldValidationError, formal.Integer(required=True).validate, None)

    def testFloat(self):
        self.assertEquals(formal.Float().validate(None), None)
        self.assertEquals(formal.Float().validate(0), 0.0)
        self.assertEquals(formal.Float().validate(0.0), 0.0)
        self.assertEquals(formal.Float().validate(.1), 0.1)
        self.assertEquals(formal.Float().validate(1), 1.0)
        self.assertEquals(formal.Float().validate(-1), -1.0)
        self.assertEquals(formal.Float().validate(-1.86), -1.86)
        self.assertEquals(formal.Float(missing=1.0).validate(None), 1.0)
        self.assertEquals(formal.Float(missing=1.0).validate(2.0), 2.0)
        self.assertRaises(formal.FieldValidationError, formal.Float(required=True).validate, None)

    def testDecimal(self):
        from decimal import Decimal
        self.assertEquals(formal.Decimal().validate(None), None)
        self.assertEquals(formal.Decimal().validate(Decimal('0')), Decimal('0'))
        self.assertEquals(formal.Decimal().validate(Decimal('0.0')), Decimal('0.0'))
        self.assertEquals(formal.Decimal().validate(Decimal('.1')), Decimal('0.1'))
        self.assertEquals(formal.Decimal().validate(Decimal('1')), Decimal('1'))
        self.assertEquals(formal.Decimal().validate(Decimal('-1')), Decimal('-1'))
        self.assertEquals(formal.Decimal().validate(Decimal('-1.86')),
                Decimal('-1.86'))
        self.assertEquals(formal.Decimal(missing=Decimal("1.0")).validate(None),
                Decimal("1.0"))
        self.assertEquals(formal.Decimal(missing=Decimal("1.0")).validate(Decimal("2.0")),
                Decimal("2.0"))
        self.assertRaises(formal.FieldValidationError, formal.Decimal(required=True).validate, None)

    def testBoolean(self):
        self.assertEquals(formal.Boolean().validate(None), None)
        self.assertEquals(formal.Boolean().validate(True), True)
        self.assertEquals(formal.Boolean().validate(False), False)
        self.assertEquals(formal.Boolean(missing=True).validate(None), True)
        self.assertEquals(formal.Boolean(missing=True).validate(False), False)

    def testDate(self):
        self.assertEquals(formal.Date().validate(None), None)
        self.assertEquals(formal.Date().validate(date(2005,1,1)), date(2005,1,1))
        self.assertEquals(formal.Date(missing=date(2005,1,2)).validate(None), date(2005,1,2))
        self.assertEquals(formal.Date(missing=date(2005,1,2)).validate(date(2005,1,1)), date(2005,1,1))
        self.assertRaises(formal.FieldValidationError, formal.Date(required=True).validate, None)

    def testTime(self):
        self.assertEquals(formal.Time().validate(None), None)
        self.assertEquals(formal.Time().validate(time(12,30,30)), time(12,30,30))
        self.assertEquals(formal.Time(missing=time(12,30,30)).validate(None), time(12,30,30))
        self.assertEquals(formal.Time(missing=time(12,30,30)).validate(time(12,30,31)), time(12,30,31))
        self.assertRaises(formal.FieldValidationError, formal.Time(required=True).validate, None)

    def test_sequence(self):
        self.assertEquals(formal.Sequence(formal.String()).validate(None), None)
        self.assertEquals(formal.Sequence(formal.String()).validate(['foo']), ['foo'])
        self.assertEquals(formal.Sequence(formal.String(), missing=['foo']).validate(None), ['foo'])
        self.assertEquals(formal.Sequence(formal.String(), missing=['foo']).validate(['bar']), ['bar'])
        self.assertRaises(formal.FieldValidationError, formal.Sequence(formal.String(), required=True).validate, None)
        self.assertRaises(formal.FieldValidationError, formal.Sequence(formal.String(), required=True).validate, [])

    def test_file(self):
        pass
    test_file.skip = "write tests"


class TestUtil(unittest.TestCase):

    def test_validIdentifier(self):
        self.assertEquals(util.validIdentifier('foo'), True)
        self.assertEquals(util.validIdentifier('_foo'), True)
        self.assertEquals(util.validIdentifier('_foo_'), True)
        self.assertEquals(util.validIdentifier('foo2'), True)
        self.assertEquals(util.validIdentifier('Foo'), True)
        self.assertEquals(util.validIdentifier(' foo'), False)
        self.assertEquals(util.validIdentifier('foo '), False)
        self.assertEquals(util.validIdentifier('9'), False)


class TestRequired(unittest.TestCase):
    
    def test_required(self):
        v = validation.RequiredValidator()
        v.validate(types.String(), 'bar')
        self.assertRaises(validation.FieldRequiredError, v.validate, types.String(), None)
        
        
class TestRange(unittest.TestCase):
    
    def test_range(self):
        self.assertRaises(AssertionError, validation.RangeValidator)
        v = validation.RangeValidator(min=5, max=10)
        v.validate(types.Integer(), None)
        v.validate(types.Integer(), 5)
        v.validate(types.Integer(), 7.5)
        v.validate(types.Integer(), 10)
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), 0)
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), 4)
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), -5)
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), 11)
        
    def test_rangeMin(self):
        v = validation.RangeValidator(min=5)
        v.validate(types.Integer(), None)
        v.validate(types.Integer(), 5)
        v.validate(types.Integer(), 10)
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), 0)
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), 4)
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), -5)
        
    def test_rangeMax(self):
        v = validation.RangeValidator(max=5)
        v.validate(types.Integer(), None)
        v.validate(types.Integer(), -5)
        v.validate(types.Integer(), 0)
        v.validate(types.Integer(), 5)
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), 6)
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), 10)
        
        
class TestLength(unittest.TestCase):
    
    def test_length(self):
        self.assertRaises(AssertionError, validation.LengthValidator)
        v = validation.LengthValidator(min=5, max=10)
        v.validate(types.String(), None)
        v.validate(types.String(), '12345')
        v.validate(types.String(), '1234567')
        v.validate(types.String(), '1234567890')
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), '')
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), '1234')
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), '12345678901')
        
    def test_lengthMin(self):
        v = validation.LengthValidator(min=5)
        v.validate(types.String(), None)
        v.validate(types.String(), '12345')
        v.validate(types.String(), '1234567890')
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), '')
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), '1234')
        
    def test_lengthMax(self):
        v = validation.LengthValidator(max=5)
        v.validate(types.String(), None)
        v.validate(types.String(), '1')
        v.validate(types.String(), '12345')
        v.validate(types.String(), '123')
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), '123456')
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), '1234567890')
        
        
class TestPattern(unittest.TestCase):
    
    def test_pattern(self):
        v = validation.PatternValidator('^[0-9]{3,5}$')
        v.validate(types.String(), None)
        v.validate(types.String(), '123')
        v.validate(types.String(), '12345')
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), ' 123')
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), '1')
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), 'foo')
        
    def test_regex(self):
        v = validation.PatternValidator(re.compile('^[0-9]{3,5}$'))
        v.validate(types.String(), None)
        v.validate(types.String(), '123')
        v.validate(types.String(), '12345')
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), ' 123')
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), '1')
        self.assertRaises(validation.FieldValidationError, v.validate, types.String(), 'foo')

if __name__=="__main__":
	testhelpers.main(TestConverters)
