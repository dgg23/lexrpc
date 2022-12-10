"""Unit tests for client.py."""
import json
from unittest import TestCase
from unittest.mock import patch

from jsonschema import ValidationError
import requests

from .lexicons import LEXICONS
from .. import Client


def response(body=None, status=200, headers=None):
    resp = requests.Response()
    resp.status_code = 200

    if headers:
        resp.headers.update(headers)

    if body is not None:
        assert isinstance(body, (dict, list))
        body = json.dumps(body, indent=2)
        resp._text = body
        resp._content = body.encode('utf-8')
        resp.headers.setdefault('Content-Type', 'application/json')

    return resp


class ClientTest(TestCase):
    maxDiff = None

    def setUp(self):
        self.client = Client('http://ser.ver', LEXICONS)
        self.call = self.client.call

    @patch('requests.get')
    def test_call(self, mock_get):
        params = {'x': 'y'}
        output = {'foo': 'asdf', 'bar': 3}
        mock_get.return_value = response(output)

        got = self.client.io.example.query(params)
        self.assertEqual(output, got)

        mock_get.assert_called_once_with(
            'http://ser.ver/xrpc/io.example.query',
            params={'x': 'y'},
            json={},
            headers={'Content-Type': 'application/json'},
        )

    @patch('requests.get')
    def test_query(self, mock_get):
        params = {'x': 'y'}
        output = {'foo': 'asdf', 'bar': 3}
        mock_get.return_value = response(output)

        got = self.client.io.example.query(params)
        self.assertEqual(output, got)

        mock_get.assert_called_once_with(
            'http://ser.ver/xrpc/io.example.query',
            params={'x': 'y'},
            json={},
            headers={'Content-Type': 'application/json'},
        )

    @patch('requests.post')
    def test_procedure(self, mock_post):
        params = {'x': 'y'}
        input = {'foo': 'asdf', 'bar': 3}
        output = {'foo': 'baz', 'bar': 4}
        mock_post.return_value = response(output)

        got = self.client.io.example.procedure(params, input)
        self.assertEqual(output, got)

        mock_post.assert_called_once_with(
            'http://ser.ver/xrpc/io.example.procedure',
            params=params,
            json=input,
            headers={'Content-Type': 'application/json'},
        )

    @patch('requests.get')
    def test_boolean_param(self, mock_get):
        params = {'z': True}
        output = {'foo': 'asdf', 'bar': 3}
        mock_get.return_value = response(output)

        got = self.client.io.example.query(params)
        self.assertEqual(output, got)

        mock_get.assert_called_once_with(
            'http://ser.ver/xrpc/io.example.query',
            params={'z': 'true'},
            json={},
            headers={'Content-Type': 'application/json'},
        )

    @patch('requests.get')
    def test_no_output_error(self, mock_get):
        mock_get.return_value = response()

        with self.assertRaises(ValidationError):
            got = self.client.io.example.query()

        mock_get.assert_called_once_with(
            'http://ser.ver/xrpc/io.example.query',
            params={},
            json={},
            headers={'Content-Type': 'application/json'},
        )

    @patch('requests.post')
    def test_no_params_input_output(self, mock_post):
        mock_post.return_value = response()
        self.assertIsNone(self.client.io.example.no_params_input_output())

        mock_post.assert_called_once_with(
            'http://ser.ver/xrpc/io.example.no-params-input-output',
            params={},
            json={},
            headers={'Content-Type': 'application/json'},
        )

    def test_missing_params(self):
        with self.assertRaises(ValidationError):
            self.client.io.example.params()

        with self.assertRaises(ValidationError):
            self.client.io.example.params(params={'foo': 'a'})

    def test_invalid_params(self):
        with self.assertRaises(ValidationError):
            self.client.io.example.params(params={'bar': 'c'})
