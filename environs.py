# -*- coding: utf-8 -*-
import contextlib
import functools
import json as pyjson
import os
import re

import marshmallow as ma

__version__ = '1.0.0.dev0'
__all__ = ['EnvError', 'Env']

class EnvError(Exception):
    pass

_proxied_pattern = re.compile(r'\s*{{\s*(\S*)\s*}}\s*')
def _get_from_environ(key, default):
    """Access a value from os.environ. Handles proxed variables, e.g. SMTP_LOGIN={{MAILGUN_LOGIN}}.
    Returns a tuple (envvar_key, envvar_value). The ``envvar_key`` will be different from
    the passed key for proxied variables.
    """
    value = os.environ.get(key, default)
    if hasattr(value, 'strip'):
        match = _proxied_pattern.match(value)
        if match:  # Proxied variable
            proxied_key = match.groups()[0]
            return proxied_key, _get_from_environ(proxied_key, default)[1]
    return key, value

def _field2method(field_or_factory, method_name, preprocess=None):
    def method(self, name, default=ma.missing, subcast=None, **kwargs):
        name = self._prefix + name if self._prefix else name
        missing = kwargs.pop('missing', None) or default
        if isinstance(field_or_factory, type) and issubclass(field_or_factory, ma.fields.Field):
            field = field_or_factory(missing=missing, **kwargs)
        else:
            field = field_or_factory(subcast=subcast, missing=missing, **kwargs)
        self._fields[name] = field
        parsed_key, raw_value = _get_from_environ(name, ma.missing)
        if raw_value is ma.missing and field.missing is ma.missing:
            raise EnvError('Environment variable "{}" not set'.format(parsed_key))
        value = raw_value or field.missing
        if preprocess:
            value = preprocess(value, subcast=subcast, **kwargs)
        try:
            value = field.deserialize(value)
        except ma.ValidationError as err:
            raise EnvError('Environment variable "{}" invalid: {}'.format(name, err.args[0]))
        else:
            self._values[name] = value
            return value
    method.__name__ = str(method_name)  # cast to str for Py2 compat
    return method

def _func2method(func, method_name):
    def method(self, name, default=ma.missing, subcast=None, **kwargs):
        name = self._prefix + name if self._prefix else name
        parsed_key, raw_value = _get_from_environ(name, default)
        if raw_value is ma.missing:
            raise EnvError('Environment variable "{}" not set'.format(parsed_key))
        value = func(raw_value, **kwargs)
        self._fields[name] = ma.fields.Field(**kwargs)
        self._values[name] = value
        return value
    method.__name__ = str(method_name)  # cast to str for Py2 compat
    return method

def _dict2schema(argmap, instance=False, **kwargs):
    """Generate a `marshmallow.Schema` class given a dictionary of fields.
    """
    class Meta(object):
        strict = True
    attrs = dict(argmap, Meta=Meta)
    cls = type(str(''), (ma.Schema,), attrs)
    return cls if not instance else cls(**kwargs)

def _make_list_field(**kwargs):
    subcast = kwargs.pop('subcast', None)
    inner_field = ma.Schema.TYPE_MAPPING[subcast] if subcast else ma.fields.Field
    return ma.fields.List(inner_field, **kwargs)

def _preprocess_list(value, **kwargs):
    return value if ma.utils.is_iterable_but_not_string(value) else value.split(',')

def _preprocess_dict(value, **kwargs):
    subcast = kwargs.get('subcast')
    return {key.strip(): subcast(val.strip()) if subcast else val.strip()
            for key, val in (item.split('=')
            for item in value.split(',') if value)}

def _preprocess_json(value, **kwargs):
    return pyjson.loads(value)

class Env(object):
    """An environment variable reader."""
    __parser_map__ = dict(
        bool=_field2method(ma.fields.Bool, 'bool'),
        str=_field2method(ma.fields.Str, 'str'),
        int=_field2method(ma.fields.Int, 'int'),
        float=_field2method(ma.fields.Float, 'float'),
        decimal=_field2method(ma.fields.Decimal, 'decimal'),
        list=_field2method(_make_list_field, 'list', preprocess=_preprocess_list),
        dict=_field2method(ma.fields.Dict, 'dict', preprocess=_preprocess_dict),
        json=_field2method(ma.fields.Field, 'json', preprocess=_preprocess_json),
        datetime=_field2method(ma.fields.DateTime, 'datetime'),
        date=_field2method(ma.fields.Date, 'date'),
        timedelta=_field2method(ma.fields.TimeDelta, 'timedelta'),
        uuid=_field2method(ma.fields.UUID, 'uuid'),
    )
    __call__ = _field2method(ma.fields.Field, '__call__')

    def __init__(self):
        self._fields = {}
        self._values = {}
        self._prefix = None

    def __repr__(self):
        return '<{} {}>'.format(self.__class__.__name__, self._values)

    __str__ = __repr__

    @contextlib.contextmanager
    def prefixed(self, prefix):
        """Context manager for parsing envvars with a common prefix."""
        self._prefix = prefix
        yield self
        self._prefix = None

    def __getattr__(self, name, **kwargs):
        try:
            return functools.partial(self.__parser_map__[name], self)
        except KeyError:
            raise AttributeError('{} has not attribute {}'.format(self, name))

    def add_parser(self, name, func):
        """Register a new parser method with the name ``name``. ``func`` must
        receive the input value for an environment variable.
        """
        self.__parser_map__[name] = _func2method(func, method_name=name)
        return None

    def parser_for(self, name):
        """Decorator that registers a new parser method with the name ``name``.
        The decorated function must receive the input value for an environment variable.
        """
        def decorator(func):
            self.add_parser(name, func)
            return func
        return decorator

    def add_parser_from_field(self, name, field_cls):
        """Register a new parser method with name ``name``, given a marshmallow ``Field``."""
        self.__parser_map__[name] = _field2method(field_cls, method_name=name)

    def dump(self):
        """Dump parsed environment variables to a dictionary of simple data types (numbers
        and strings).
        """
        schema = _dict2schema(self._fields, instance=True)
        return schema.dump(self._values).data
