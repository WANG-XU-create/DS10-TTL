# Copyright 2026 wangxu
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""
Tests for the Python reference codec.

Two layers, and the distinction matters. Round-trip tests prove this module
is self-consistent -- they would pass just as happily on a codec that agreed
with nothing else in the project. The vector tests are the ones that pin the
wire format: protocol_test_vectors.json holds bytes derived by hand from the
spec, and the C++ gtest checks itself against the same file, so a divergence
between the two implementations fails on one side or the other.
"""

import json
import math
import os
import struct
import sys

import pytest

sys.path.insert(
    0, os.path.join(os.path.dirname(__file__), '..', 'scripts'))

from protocol_codec import (  # noqa: E402  (needs the sys.path line above)
    CONTROL_COMMAND_MIN_SIZE,
    SENSOR_DATA_SIZE,
    decode_control_command,
    decode_sensor_data,
    encode_control_command,
    encode_sensor_data,
)

VECTORS_PATH = os.path.join(os.path.dirname(__file__), 'protocol_test_vectors.json')

# JSON has no literal for these, so the vector file spells them as strings.
_SPECIAL_READINGS = {'inf': math.inf, '-inf': -math.inf, 'nan': math.nan}

# From protocol_constants.hpp: 4095 - station - function_code - CRC - flags - cmd_id.
MAX_CONTROL_PARAMS_SIZE = 4089


def _reading_of(value):
    """Resolve a vector's reading field, which is a number or a special name."""
    return _SPECIAL_READINGS[value] if isinstance(value, str) else value


def _load_vectors():
    with open(VECTORS_PATH) as f:
        return json.load(f)['vectors']


def _vectors_of_type(type_name):
    return [v for v in _load_vectors() if v['type'] == type_name]


def _vector_id(vector):
    return vector['name']


# --- Round trip: this module against itself -------------------------------


@pytest.mark.parametrize('params', [b'', b'\xAA', b'\x00' * 8, bytes(range(256))])
def test_control_command_round_trip(params):
    """Every params length survives encode -> decode unchanged."""
    encoded = encode_control_command(0x01, 0x05, params)
    decoded = decode_control_command(encoded)

    assert decoded == {'flags': 0x01, 'cmd_id': 0x05, 'params': params}


def test_control_command_round_trip_at_max_params():
    """The largest params a frame can hold still round-trips."""
    params = bytes(i % 256 for i in range(MAX_CONTROL_PARAMS_SIZE))
    decoded = decode_control_command(encode_control_command(0, 1, params))

    assert decoded['params'] == params
    assert len(decoded['params']) == MAX_CONTROL_PARAMS_SIZE


@pytest.mark.parametrize('seq', [0, 1, 42, 32768, 65535])
@pytest.mark.parametrize('reading', [0.0, -0.0, 1.0, -1.0, 23.5, 3.4e38, 1.2e-38])
def test_sensor_data_round_trip(seq, reading):
    """Sequence numbers and finite readings survive encode -> decode."""
    decoded = decode_sensor_data(encode_sensor_data(0x00, seq, 7, reading))

    assert decoded['seq'] == seq
    assert decoded['reading'] == pytest.approx(reading)


@pytest.mark.parametrize('reading', [math.inf, -math.inf])
def test_sensor_data_round_trip_infinities(reading):
    """Infinities are ordinary float32 bit patterns to this codec."""
    decoded = decode_sensor_data(encode_sensor_data(0, 1, 2, reading))

    assert decoded['reading'] == reading


def test_sensor_data_round_trip_nan():
    """A NaN reading survives, and needs isnan: it compares unequal to itself."""
    decoded = decode_sensor_data(encode_sensor_data(0, 1, 2, math.nan))

    assert math.isnan(decoded['reading'])


def test_sensor_data_preserves_negative_zero():
    """-0.0 is a distinct bit pattern; == would not catch it being lost."""
    decoded = decode_sensor_data(encode_sensor_data(0, 1, 2, -0.0))

    assert math.copysign(1.0, decoded['reading']) == -1.0


# --- Undersized input -----------------------------------------------------


@pytest.mark.parametrize('length', range(CONTROL_COMMAND_MIN_SIZE))
def test_control_command_too_short_is_rejected(length):
    """Anything shorter than [flags][cmd_id] decodes to None."""
    assert decode_control_command(b'\x00' * length) is None


def test_control_command_accepts_exactly_the_minimum():
    """Two bytes is a valid command with no params, not a truncated one."""
    assert decode_control_command(b'\x07\x09') == {
        'flags': 7, 'cmd_id': 9, 'params': b''}


@pytest.mark.parametrize('length', range(SENSOR_DATA_SIZE))
def test_sensor_data_too_short_is_rejected(length):
    """Anything shorter than the fixed 8 bytes decodes to None."""
    assert decode_sensor_data(b'\x00' * length) is None


def test_sensor_data_ignores_trailing_bytes():
    """A longer payload decodes its first 8 bytes, matching the C++ decoder."""
    encoded = encode_sensor_data(1, 2, 3, 4.0)
    decoded = decode_sensor_data(encoded + b'\xFF\xFF')

    assert decoded == decode_sensor_data(encoded)


# --- Vectors: this module against the spec --------------------------------


@pytest.mark.parametrize('vector', _vectors_of_type('0x12'), ids=_vector_id)
def test_control_command_matches_vector(vector):
    """Encoding a vector's fields produces exactly the bytes the spec says."""
    fields = vector['input']
    encoded = encode_control_command(
        fields['flags'], fields['cmd_id'], bytes.fromhex(fields['params']))

    assert encoded.hex().upper() == vector['expected_bytes']


@pytest.mark.parametrize('vector', _vectors_of_type('0x12'), ids=_vector_id)
def test_control_command_decodes_vector(vector):
    """Decoding a vector's bytes recovers the fields it was built from."""
    fields = vector['input']
    decoded = decode_control_command(bytes.fromhex(vector['expected_bytes']))

    assert decoded == {
        'flags': fields['flags'],
        'cmd_id': fields['cmd_id'],
        'params': bytes.fromhex(fields['params']),
    }


@pytest.mark.parametrize('vector', _vectors_of_type('0x10'), ids=_vector_id)
def test_sensor_data_matches_vector(vector):
    """Encoding a vector's fields produces exactly the bytes the spec says."""
    fields = vector['input']
    encoded = encode_sensor_data(
        fields['flags'], fields['seq'], fields['sensor_id'],
        _reading_of(fields['reading']))

    assert encoded.hex().upper() == vector['expected_bytes']


@pytest.mark.parametrize('vector', _vectors_of_type('0x10'), ids=_vector_id)
def test_sensor_data_decodes_vector(vector):
    """Decoding a vector's bytes recovers the fields it was built from."""
    fields = vector['input']
    decoded = decode_sensor_data(bytes.fromhex(vector['expected_bytes']))
    expected_reading = _reading_of(fields['reading'])

    assert decoded['flags'] == fields['flags']
    assert decoded['seq'] == fields['seq']
    assert decoded['sensor_id'] == fields['sensor_id']
    if math.isnan(expected_reading):
        assert math.isnan(decoded['reading'])
    else:
        assert decoded['reading'] == expected_reading


# --- The vector file itself -----------------------------------------------


def test_vector_file_is_not_self_fulfilling():
    """
    Recompute every expected_bytes without calling the module under test.

    A vector file generated by running the codec proves only that the codec
    agrees with itself. This recomputes each expectation from struct directly,
    so a bug shared by encoder and decoder still fails.
    """
    for vector in _load_vectors():
        fields = vector['input']
        if vector['type'] == '0x12':
            expected = bytes(
                [fields['flags'], fields['cmd_id']]) + bytes.fromhex(fields['params'])
        else:
            expected = struct.pack(
                '<BHBf', fields['flags'], fields['seq'], fields['sensor_id'],
                _reading_of(fields['reading']))

        assert expected.hex().upper() == vector['expected_bytes'], vector['name']


def test_vector_file_covers_both_message_types():
    """A silently empty parametrize list would make the vector tests vacuous."""
    assert len(_vectors_of_type('0x12')) >= 4
    assert len(_vectors_of_type('0x10')) >= 4
