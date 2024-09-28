"""Unit tests for base.py."""
from datetime import datetime
from unittest import skip, TestCase

from .lexicons import LEXICONS
from ..base import Base, ValidationError

# set as the base.now return value in mocks in tests
NOW = datetime(2022, 2, 3)


class BaseTest(TestCase):
    maxDiff = None

    def setUp(self):
        super().setUp()
        self.base = Base(LEXICONS, validate=True)

    def test_get_def(self):
        for nsid in 'io.exa-mple.dashedName', 'io.example.noParamsInputOutput':
            self.assertEqual({'type': 'procedure'}, self.base._get_def(nsid))

        self.assertEqual({
            'type': 'object',
            'required': ['boolean'],
            'properties': {
                'boolean': {'type': 'boolean'},
            },
        }, self.base._get_def('io.example.kitchenSink#subobject'))

    def test_validate_record_pass(self):
        self.base.validate('io.example.record', 'record', {
            'baz': 3,
            'biff': {
                'baj': 'foo',
            },
        })

    def test_validate_truncate(self):
        base = Base(LEXICONS, truncate=True)

        for input, expected in (
            ('short', 'short'),
            ('too many graphemes', 'too many …'),
            # ('🇨🇾🇬🇭🇨🇾🇬🇭🇨🇾🇬🇭', '🇨🇾🇬🇭🇨🇾🇬🇭🇨🇾🇬🇭'),
            # ('🇨🇾🇬🇭 bytes', '🇨🇾…'),  # TODO
        ):
            with self.subTest(input=input, expected=expected):
                self.assertEqual(
                    {'string': expected},
                    base.validate('io.example.stringLength', 'record',
                                  {'string': input}))

    def test_validate_record_pass_nested_optional_field_missing(self):
        self.base.validate('io.example.record', 'record', {
            'baz': 3,
            'biff': {
            },
        })

    def test_validate_record_pass_optional_field_missing(self):
        self.base.validate('io.example.record', 'record', {
            'baz': 3,
        })


    def test_validate_record_fail_integer_field_bad_type(self):
        with self.assertRaises(ValidationError):
            self.base.validate('io.example.record', 'record', {
                'baz': 'x',
                'biff': {
                    'baj': 'foo',
                },
            })

    def test_validate_record_fail_object_field_bad_type(self):
        with self.assertRaises(ValidationError):
            self.base.validate('io.example.record', 'record', {
                'baz': 3,
                'biff': 4,
            })

    def test_validate_record_fail_missing_required_field(self):
        with self.assertRaises(ValidationError):
            self.base.validate('io.example.record', 'record', {
                'biff': {
                    'baj': 'foo',
                },
            })

    def test_validate_record_kitchen_sink_pass(self):
        self.base.validate('io.example.kitchenSink', 'record', {
            'array': ['x', 'y'],
            'boolean': True,
            'integer': 3,
            'string': 'z',
            'datetime': '1985-04-12T23:20:50Z',
            'object': {
                'array': ['x', 'y'],
                'boolean': True,
                'integer': 3,
                'string': 'z',
                'subobject': {'boolean': False},
            },
        })

    def test_validate_record_object_array_pass(self):
        self.base.validate('io.example.objectArray', 'record', {'foo': []})

        self.base.validate('io.example.objectArray', 'record', {
            'foo': [
                {'bar': 3, 'baj': 'foo'},
                {'bar': 4},
            ],
        })

    def test_validate_record_object_array_fail_bad_type(self):
        with self.assertRaises(ValidationError):
            self.base.validate('io.example.objectArray', 'record', {
                'foo': [
                    {'bar': 'x'},
                ],
            })

    def test_validate_record_object_array_fail_missing_required(self):
        with self.assertRaises(ValidationError):
            self.base.validate('io.example.objectArray', 'record', {
                'foo': [
                    {'baz': 'x'},
                ],
            })

    def test_validate_record_ref_array_pass(self):
        self.base.validate('io.example.refArray', 'record', {'foo': []})

        self.base.validate('io.example.refArray', 'record', {
            'foo': [
                {'baz': 5},
                {'baz': 5, 'biff': {'baj': 'ok'}},
            ],
        })

    def test_validate_record_ref_array_fail_bad_type(self):
        with self.assertRaises(ValidationError):
            self.base.validate('io.example.refArray', 'record', {
                'foo': [{'baz': 'x'}],
            })

        with self.assertRaises(ValidationError):
            self.base.validate('io.example.refArray', 'record', {
                'foo': [{
                    'baz': 'x',
                    'biff': {'baj': 5},
                }],
            })

    def test_validate_record_ref_array_fail_item_not_nullable(self):
        with self.assertRaises(ValidationError):
            self.base.validate('io.example.refArray', 'record', {
                'foo': [
                    {'baz': None},
                ],
            })

    def test_validate_record_union_array_pass(self):
        self.base.validate('io.example.unionArray', 'record', {'foo': []})

        self.base.validate('io.example.unionArray', 'record', {
            'foo': [{
                '$type': 'io.example.kitchenSink#object',
                'subobject': {'boolean': True},
                'array': [],
                'boolean': False,
                'integer': 0,
                'string': 'ok',
            }, {
                '$type': 'io.example.kitchenSink#subobject',
                'boolean': False,
            }],
        })

    def test_validate_record_union_array_fail_bad_type(self):
        for bad in [
                123,
                {'$type': 'io.example.kitchenSink#subobject', 'boolean': 123},
                {'$type': 'io.example.record', 'baz': 123},
        ]:
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                self.base.validate('io.example.unionArray', 'record', {
                    'foo': [123],
                })

    def test_validate_record_union_array_fail_inner_array(self):
        for bad in 123, [123], ['x', 123], [{'y': 'z'}]:
            with self.subTest(bad=bad), self.assertRaises(ValidationError):
                self.base.validate('io.example.unionArray', 'record', {
                    'foo': [{
                        '$type': 'io.example.kitchenSink#object',
                        'subobject': {'boolean': True},
                        'array': bad,
                        'boolean': False,
                        'integer': 0,
                        'string': 'ok',
                    }],
                })

    def test_no_validate_or_truncate(self):
        # shouldn't raise
        base = Base(LEXICONS, validate=False, truncate=False)
        base.validate(None, None, {'x': 'y'})

