from __future__ import unicode_literals

import uuid
from decimal import Decimal
import datetime as dt

import pytest
from marshmallow import fields, validate
import read_env

import environs

@pytest.fixture
def set_env(monkeypatch):
    def _set_env(envvars):
        for key, val in envvars.items():
            monkeypatch.setenv(key, val)
    return _set_env


@pytest.fixture
def env():
    return environs.Env()


class TestCasting:

    def test_call(self, set_env, env):
        set_env({'STR': 'foo', 'INT': '42'})
        assert env('STR') == 'foo'
        assert env('NOT_SET', 'mydefault') == 'mydefault'

    def test_call_with_default(self, env):
        assert env('NOT_SET', default='mydefault') == 'mydefault'
        assert env('NOT_SET', 'mydefault') == 'mydefault'

    def test_basic(self, set_env, env):
        set_env({'STR': 'foo'})
        assert env.str('STR') == 'foo'

    def test_int_cast(self, set_env, env):
        set_env({'INT': '42'})
        assert env.int('INT') == 42

    def test_invalid_int(self, set_env, env):
        set_env({'INT': 'invalid'})
        with pytest.raises(environs.EnvError) as excinfo:
            env.int('INT') == 42
        assert 'Environment variable "INT" invalid' in excinfo.value.args[0]

    def test_float_cast(self, set_env, env):
        set_env({'FLOAT': '33.3'})
        assert env.float('FLOAT') == 33.3

    def test_list_cast(self, set_env, env):
        set_env({'LIST': '1,2,3'})
        assert env.list('LIST') == ['1', '2', '3']

    def test_list_with_subcast(self, set_env, env):
        set_env({'LIST': '1,2,3'})
        assert env.list('LIST', subcast=int) == [1, 2, 3]
        assert env.list('LIST', subcast=float) == [1.0, 2.0, 3.0]

    def test_bool(self, set_env, env):
        set_env({'TRUTHY': '1', 'FALSY': '0'})
        assert env.bool('TRUTHY') is True
        assert env.bool('FALSY') is False

        set_env({'TRUTHY2': 'True', 'FALSY2': 'False'})
        assert env.bool('TRUTHY2') is True
        assert env.bool('FALSY2') is False

    def test_list_with_spaces(self, set_env, env):
        set_env({'LIST': ' 1,  2,3'})
        assert env.list('LIST', subcast=int) == [1, 2, 3]

    def test_dict(self, set_env, env):
        set_env({'DICT': 'key1=1,key2=2'})
        assert env.dict('DICT') == {'key1': '1', 'key2': '2'}

    def test_dict_with_subcast(self, set_env, env):
        set_env({'DICT': 'key1=1,key2=2'})
        assert env.dict('DICT', subcast=int) == {'key1': 1, 'key2': 2}

    def test_decimat_cast(self, set_env, env):
        set_env({'DECIMAL': '12.34'})
        assert env.decimal('DECIMAL') == Decimal('12.34')

    def test_missing_raises_error(self, env):
        with pytest.raises(environs.EnvError) as exc:
            env.str('FOO')
        assert exc.value.args[0] == 'Environment variable "FOO" not set'

    def test_default_set(self, env):
        assert env.str('FOO', missing='foo') == 'foo'
        # Passed positionally
        assert env.str('FOO', 'foo') == 'foo'

    def test_json_cast(self, set_env, env):
        set_env({'JSON': '{"foo": "bar", "baz": [1, 2, 3]}'})
        assert env.json('JSON') == {'foo': 'bar', 'baz': [1, 2, 3]}

    def test_datetime_cast(self, set_env, env):
        dtime = dt.datetime.utcnow()
        set_env({'DTIME': dtime.isoformat()})
        result = env.datetime('DTIME')
        assert type(result) is dt.datetime
        assert result.year == dtime.year
        assert result.month == dtime.month
        assert result.day == dtime.day

    def test_date_cast(self, set_env, env):
        date = dt.date.today()
        set_env({'DATE': date.isoformat()})
        assert env.date('DATE') == date

    def test_timedelta_cast(self, set_env, env):
        set_env({'TIMEDELTA': '42'})
        assert env.timedelta('TIMEDELTA') == dt.timedelta(seconds=42)

    def test_uuid_cast(self, set_env, env):
        uid = uuid.uuid1()
        set_env({'UUID': str(uid)})
        assert env.uuid('UUID') == uid


class TestProxiedVariables:

    def test_reading_proxied_variable(self, set_env, env):
        set_env({
            'MAILGUN_SMTP_LOGIN': 'sloria',
            'SMTP_LOGIN': '{{MAILGUN_SMTP_LOGIN}}',
            'SMTP_LOGIN_LPADDED': '{{ MAILGUN_SMTP_LOGIN}}',
            'SMTP_LOGIN_RPADDED': '{{MAILGUN_SMTP_LOGIN }}'
        })
        for key in ('MAILGUN_SMTP_LOGIN', 'SMTP_LOGIN', 'SMTP_LOGIN_LPADDED', 'SMTP_LOGIN_RPADDED'):
            assert env(key) == 'sloria'
            assert env.dump()[key] == 'sloria'

    def test_reading_missing_proxied_variable(self, set_env, env):
        set_env({
            'SMTP_LOGIN': '{{MAILGUN_SMTP_LOGIN}}'
        })
        with pytest.raises(environs.EnvError):
            env('SMTP_LOGIN')
        assert env('SMTP_LOGIN', 'default') == 'default'


class TestEnvFileReading:

    def test_read_env_integration(self, env):
        assert env('STRING', 'default') == 'default'  # sanity check
        read_env.read_env()
        assert env('STRING') == 'foo'
        assert env.list('LIST') == ['wat', 'wer', 'wen']

def always_fail(value):
    raise environs.EnvError('something went wrong')

class TestValidation:

    def test_can_add_validator(self, set_env, env):
        set_env({'NUM': 3})

        with pytest.raises(environs.EnvError) as excinfo:
            env.int('NUM', validate=lambda n: n > 3)
        assert 'Invalid value.' in excinfo.value.args[0]

    def test_can_add_marshmallow_validator(self, set_env, env):
        set_env({'NODE_ENV': 'invalid'})
        with pytest.raises(environs.EnvError) as excinfo:
            env('NODE_ENV', validate=validate.OneOf(['development', 'production']))
        assert 'Not a valid choice.' in excinfo.value.args[0]

    def test_validator_can_raise_enverror(self, set_env, env):
        with pytest.raises(environs.EnvError) as excinfo:
            env('NODE_ENV', 'development', validate=always_fail)
        assert 'something went wrong' in excinfo.value.args[0]

    def test_failed_vars_are_not_serialized(self, set_env, env):
        set_env({'FOO': '42'})
        try:
            env('FOO', validate=always_fail)
        except environs.EnvError:
            pass
        assert 'FOO' not in env.dump()


class TestCustomTypes:

    def test_add_parser(self, set_env, env):
        set_env({'URL': 'test.test/'})

        def url(value):
            return 'https://' + value

        env.add_parser('url', url)
        assert env.url('URL') == 'https://test.test/'
        with pytest.raises(environs.EnvError) as excinfo:
            env.url('NOT_SET')
        assert excinfo.value.args[0] == 'Environment variable "NOT_SET" not set'

        assert env.url('NOT_SET', 'default.test/') == 'https://default.test/'

    def test_parser_for(self, set_env, env):
        set_env({'URL': 'test.test/'})

        @env.parser_for('url')
        def url(value):
            return 'https://' + value
        assert env.url('URL') == 'https://test.test/'

        with pytest.raises(environs.EnvError) as excinfo:
            env.url('NOT_SET')
        assert excinfo.value.args[0] == 'Environment variable "NOT_SET" not set'

        assert env.url('NOT_SET', 'default.test/') == 'https://default.test/'

    def test_parser_function_can_take_extra_arguments(self, set_env, env):
        set_env({'ENV': 'dev'})

        @env.parser_for('enum')
        def enum_parser(value, choices):
            if value not in choices:
                raise environs.EnvError('Invalid!')
            return value

        assert env.enum('ENV', choices=['dev', 'prod']) == 'dev'

        set_env({'ENV': 'invalid'})
        with pytest.raises(environs.EnvError):
            env.enum('ENV', choices=['dev', 'prod'])

    def test_add_parser_from_field(self, set_env, env):
        class MyURL(fields.Field):
            def _deserialize(self, value, *args, **kwargs):
                return 'https://' + value

        env.add_parser_from_field('url', MyURL)

        set_env({'URL': 'test.test/'})
        assert env.url('URL') == 'https://test.test/'

        with pytest.raises(environs.EnvError) as excinfo:
            env.url('NOT_SET')
        assert excinfo.value.args[0] == 'Environment variable "NOT_SET" not set'

class TestDumping:
    def test_dump(self, set_env, env):
        dtime = dt.datetime.utcnow()
        set_env({'STR': 'foo', 'INT': '42', 'DTIME': dtime.isoformat()})

        env.str('STR')
        env.int('INT')
        env.datetime('DTIME')

        result = env.dump()
        assert result['STR'] == 'foo'
        assert result['INT'] == 42
        assert 'DTIME' in result
        assert type(result['DTIME']) is str

    def test_env_with_custom_parser(self, set_env, env):
        @env.parser_for('url')
        def url(value):
            return 'https://' + value

        set_env({'URL': 'test.test'})

        env.url('URL')

        assert env.dump() == {'URL': 'https://test.test'}

def test_repr(set_env, env):
    set_env({'FOO': 'foo', 'BAR': 42})
    env.str('FOO')
    assert repr(env) == '<Env {}>'.format({'FOO': 'foo'})

def test_str(set_env, env):
    set_env({'FOO': 'foo', 'BAR': 42})
    env.str('FOO')
    assert repr(env) == '<Env {}>'.format({'FOO': 'foo'})

class TestPrefix:

    @pytest.fixture(autouse=True)
    def default_environ(self, set_env):
        set_env({'APP_STR': 'foo', 'APP_INT': '42'})

    def test_prefixed(self, env):
        with env.prefixed('APP_'):
            assert env.str('STR') == 'foo'
            assert env.int('INT') == 42
            assert env('NOT_FOUND', 'mydefault') == 'mydefault'

    def test_dump_with_prefixed(self, env):
        with env.prefixed('APP_'):
            env.str('STR') == 'foo'
            env.int('INT') == 42
            env('NOT_FOUND', 'mydefault') == 'mydefault'
        assert env.dump() == {'APP_STR': 'foo', 'APP_INT': 42, 'APP_NOT_FOUND': 'mydefault'}