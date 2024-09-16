"""Base code shared by both server and client."""
import copy
from datetime import datetime, timezone
from importlib.resources import files
import json
import logging
import re
from types import NoneType
import urllib.parse

logger = logging.getLogger(__name__)

METHOD_TYPES = frozenset((
    'query',
    'procedure',
    'subscription',
))
LEXICON_TYPES = METHOD_TYPES | frozenset((
    'object',
    'record',
    'ref',
    'token',
))
PARAMETER_TYPES = frozenset((
    'array',
    'boolean',
    'integer',
    'number',
    'string',
))
# https://atproto.com/specs/lexicon#overview-of-types
FIELD_TYPES = {
    'null': NoneType,
    'boolean': bool,
    'integer': int,
    'string': str,
    'bytes': bytes,
    'array': list,
    'object': dict,
}

# https://atproto.com/specs/nsid
NSID_SEGMENT = '[a-zA-Z0-9-]+'
NSID_SEGMENT_RE = re.compile(f'^{NSID_SEGMENT}$')
NSID_RE = re.compile(f'^{NSID_SEGMENT}(\.{NSID_SEGMENT})*$')


# wrapper for datetime.now, lets us mock it out in tests
now = lambda tz=timezone.utc, **kwargs: datetime.now(tz=tz, **kwargs)


class XrpcError(ValueError):
    """A named error in an XRPC call.

    ``name`` is the error, eg ``RepoNotFound`` in ``com.atproto.sync.getRepo``.
    ``message`` is the human-readable string error message.
    """
    def __init__(self, message, name=None, **kwargs):
        super().__init__(message, **kwargs)
        self.name = name
        self.message = message


def load_lexicons(traversable):
    if traversable.is_file():
        lexicons = [json.loads(traversable.read_text())]
    elif traversable.is_dir():
        lexicons = sum((load_lexicons(item) for item in traversable.iterdir()),
                       start=[])

    return lexicons

_bundled_lexicons = load_lexicons(files('lexrpc').joinpath('lexicons'))
logger.info(f'{len(_bundled_lexicons)} lexicons loaded')


def fail(msg, exc=NotImplementedError):
    """Logs an error and raises an exception with the given message."""
    logger.error(msg)
    raise exc(msg)


class ValidationError(ValueError):
    """Raised when an object or XRPC input or output doesn't match its schema."""
    pass


class Base():
    """Base class for both XRPC client and server."""

    defs = None  # dict mapping id to lexicon def
    _validate = None
    _truncate = None

    def __init__(self, lexicons=None, validate=True, truncate=False):
        """Constructor.

        Args:
          lexicons (sequence of dict): lexicons, optional. If not provided,
            defaults to the official, built in ``com.atproto`` and ``app.bsky``
            lexicons.
          validate (bool): whether to validate schemas, parameters, and input
            and output bodies
          truncate (bool): whether to truncate string values that are longer
            than their ``maxGraphemes`` or ``maxLength`` in their lexicon

        Raises:
          ValidationError: if any schema is invalid
        """
        self._validate = validate
        self._truncate = truncate
        self.defs = {}

        if lexicons is None:
            lexicons = _bundled_lexicons

        for i, lexicon in enumerate(copy.deepcopy(lexicons)):
            nsid = lexicon.get('id')
            if not nsid:
                raise ValidationError(f'Lexicon {i} missing id field')
            # logger.debug(f'Loading lexicon {nsid}')

            for name, defn in lexicon.get('defs', {}).items():
                id = nsid if name == 'main' else f'{nsid}#{name}'
                self.defs[id] = defn

                type = defn['type']
                if type not in LEXICON_TYPES | PARAMETER_TYPES:
                    raise ValidationError(f'Bad type for lexicon {id}: {type}')

                for field in ('input', 'output', 'message',
                              'parameters', 'record'):
                    if validate:
                        # logger.debug(f'Validating {id} {field} schema')
                        # TODO
                        pass

                self.defs[id] = defn

        if not self.defs:
            logger.error('No lexicons loaded!')

    def _get_def(self, id):
        """Returns the given lexicon def.

        Raises:
          NotImplementedError: if no def exists for the given id
        """
        lexicon = self.defs.get(id)
        if not lexicon:
            fail(f'{id} not found')

        return lexicon

    def _maybe_validate(self, nsid, type, obj):
        """If configured to do so, validates a JSON object against a given schema.

        Returns ``None`` if the object validates, otherwise raises an exception.

        Does nothing if this object was initialized with ``validate=False``.

        Args:
          nsid (str): method NSID
          type (str): ``input``, ``output``, ``parameters``, or ``record``
          obj (dict): JSON object

        Returns:
          dict: obj, either unchanged, or possible a modified copy if
            ``truncate`` is enabled and a string value was too long

        Raises:
          NotImplementedError: if no lexicon exists for the given NSID, or the
            lexicon does not define a schema for the given type
          ValidationError: if the object is invalid
        """
        assert type in ('input', 'output', 'message', 'parameters', 'record'), type

        base = self._get_def(nsid).get(type, {})
        encoding = base.get('encoding')
        if encoding and encoding != 'application/json':
            # binary or other non-JSON data, pass through
            return obj

        schema = base
        if type != 'record':
            schema = base.get('schema')

        if not schema:

            return
            # ...or should we fail if obj is non-null? maybe not, since then
            # we'd fail if a query with no params gets requested with any query
            # params at all, eg utm_* tracking params

        if self._truncate:
            for name, config in schema.get('properties', {}).items():
                # TODO: recurse into reference, union, etc properties
                if max_graphemes := config.get('maxGraphemes'):
                    val = obj.get(name)
                    if val and len(val) > max_graphemes:
                        obj = {
                            **obj,
                            name: val[:max_graphemes - 1] + '…',
                        }

        if not self._validate:
            return

        # logger.debug(f'Validating {nsid} {type}')

        for name, prop in schema.get('properties', {}).items():
            if name not in obj:
                if name in schema.get('required', []):
                    raise ValidationError(
                        f'{nsid} {type} missing required property {name}')
                continue

            val = obj[name]
            if val is None:
                if name not in schema.get('nullable', []):
                    raise ValidationError(
                        f'{nsid} {type} property {name} is not nullable')
                continue

            # TODO: datetime
            # TODO: token
            # TODO: ref
            # TODO: union
            # TODO: unknown
            # TODO: cid-link
            if not isinstance(val, FIELD_TYPES[prop['type']]):
                raise ValidationError(
                    f'{nsid} {type}: unexpected value for {prop["type"]} property '
                    f'{name}: {val!r}')

            if type == 'array':
                for item in val:
                    if not isinstance(item, FIELD_TYPES[prop['items']['type']]):
                        raise ValidationError(
                            f'{nsid} {type}: unexpected item for {prop["type"]} '
                            f'array property {name}: {item!r}')

        return obj

    def encode_params(self, params):
        """Encodes decoded parameter values.

        Based on https://atproto.com/specs/xrpc#lexicon-http-endpoints

        Args:
          params (dict): maps str names to boolean, number, str, or list values

        Returns:
          bytes: URL-encoded query parameter string
        """
        return urllib.parse.urlencode({
            name: ('true' if val is True
                   else 'false' if val is False
                   else val)
            for name, val in params.items()
        }, doseq=True)

    def decode_params(self, method_nsid, params):
        """Decodes encoded parameter values.

        Based on https://atproto.com/specs/xrpc#lexicon-http-endpoints

        Args:
          method_nsid (str):
          params (sequence of (str, str) tuple): name/value mappings

        Returns:
          dict: maps str names to decoded boolean, number, str, and array values

        Raises:
          ValueError: if a parameter value can't be decoded
          NotImplementedError: if no method lexicon is registered for the given NSID
        """
        lexicon = self._get_def(method_nsid)
        params_schema = lexicon.get('parameters', {}).get('properties', {})

        decoded = {}
        for name, val in params:
            type = params_schema.get(name, {}).get('type') or 'string'
            assert type in PARAMETER_TYPES, type

            if type == 'boolean':
                if val == 'true':
                    decoded[name] = True
                elif val == 'false':
                    decoded[name] = False
                else:
                    raise ValueError(
                        f'Got {val!r} for boolean parameter {name}, expected true or false')

            try:
                if type == 'number':
                    decoded[name] = float(val)
                elif type in ('int', 'integer'):
                    decoded[name] = int(val)
            except ValueError as e:
                e.args = [f'{e.args[0]} for {type} parameter {name}']
                raise e

            if type == 'string':
                decoded[name] = val

            if type == 'array':
                decoded.setdefault(name, []).append(val)

        return decoded
