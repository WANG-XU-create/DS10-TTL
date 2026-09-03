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
import re
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

# Mirrors MAX_CONTROL_PARAMS_SIZE in protocol_constants.hpp. Duplicated
# rather than imported -- Python cannot read a C++ constexpr -- so
# test_max_params_matches_the_cpp_constant re-derives it from the header and
# fails if the two drift apart.
MAX_CONTROL_PARAMS_SIZE = 4089

CONSTANTS_HEADER = os.path.join(
    os.path.dirname(__file__), '..', 'include', 'ds10_protocol',
    'protocol_constants.hpp')


def _reading_of(value):
    """Resolve a vector's reading field, which is a number or a special name."""
    return _SPECIAL_READINGS[value] if isinstance(value, str) else value


def _float32_bits(value):
    """
    Compute an IEEE-754 single-precision bit pattern arithmetically.

    Deliberately avoids struct: this exists to check the vector file, and
    struct.pack('<BHBf', ...) is the exact expression encode_sensor_data
    uses, so recomputing with it would only prove that line agrees with
    itself. Doing the exponent and mantissa by hand means a misreading of
    the layout in the codec cannot be reproduced identically here.
    """
    if math.isnan(value):
        return 0x7FC00000  # the quiet NaN struct produces

    sign = 0x80000000 if math.copysign(1.0, value) < 0 else 0
    magnitude = abs(value)

    if math.isinf(magnitude):
        return sign | 0x7F800000
    if magnitude == 0.0:
        return sign

    # frexp gives magnitude == fraction * 2**exp with 0.5 <= fraction < 1;
    # IEEE-754 wants 1.f * 2**e, so double the fraction and drop the exponent.
    fraction, exponent = math.frexp(magnitude)
    fraction *= 2.0
    exponent -= 1
    biased_exponent = exponent + 127

    if biased_exponent >= 255:
        # struct.pack('<f', 1e39) raises rather than saturating to infinity.
        # The oracle must not be more permissive than the thing it checks:
        # silently returning inf here would let a vector claiming 1e39 encodes
        # to 0x7F800000 pass, when no conformant encoder produces that.
        raise OverflowError(f'{value!r} is outside float32 range')
    if biased_exponent <= 0:
        subnormal = int(round(magnitude / (2.0 ** -149)))
        return sign | subnormal

    mantissa = int(round((fraction - 1.0) * (1 << 23)))
    if mantissa == (1 << 23):  # rounding carried up into the exponent
        mantissa = 0
        biased_exponent += 1

    return sign | (biased_exponent << 23) | mantissa


def _little_endian(value, width):
    """Serialize an unsigned integer least-significant byte first."""
    return bytes((value >> (8 * i)) & 0xFF for i in range(width))


def _expected_bytes_from_layout(vector):
    """
    Build a vector's bytes from the spec's field layout, by hand.

    The independent oracle behind test_vector_file_is_not_self_fulfilling.
    Every byte here comes from application_protocol_v1.md §功能码 0x10 /
    §功能码 0x12 read as prose, not from any codec.
    """
    fields = vector['input']
    if vector['type'] == '0x12':
        # [flags 1B][cmd_id 1B][params ...]
        return (bytes([fields['flags'], fields['cmd_id']])
                + bytes.fromhex(fields['params']))

    # [flags 1B][seq u16 LE][sensor_id 1B][reading f32 LE]
    return (bytes([fields['flags']])
            + _little_endian(fields['seq'], 2)
            + bytes([fields['sensor_id']])
            + _little_endian(_float32_bits(_reading_of(fields['reading'])), 4))


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
    Rebuild every expected_bytes from the layout, using no codec at all.

    A vector file generated by running a codec proves only that the codec
    agrees with itself. _expected_bytes_from_layout assembles each field by
    hand -- including the IEEE-754 exponent and mantissa -- so a misreading
    of the spec shared by encoder and decoder still fails here.
    """
    for vector in _load_vectors():
        expected = _expected_bytes_from_layout(vector)

        assert expected.hex().upper() == vector['expected_bytes'], vector['name']


@pytest.mark.parametrize('value', [
    0.0, -0.0, 1.0, -1.0, 23.5, 0.1, -0.1, 3.4e38, -3.4e38, 1.5e-38,
    math.inf, -math.inf, 1e-45, 2.0, 65536.0,
])
def test_the_oracle_agrees_with_struct(value):
    """
    The hand-rolled float32 encoder matches struct on ordinary values.

    An independent oracle is only useful if it is correct. This pins it
    against struct across the range -- the one place the two are compared,
    and deliberately not inside the vector check itself, so the vector
    check keeps its independence.
    """
    assert _little_endian(_float32_bits(value), 4) == struct.pack('<f', value)


def test_the_oracle_encodes_nan():
    """A NaN needs its own case: it compares unequal to itself."""
    packed = struct.unpack('<I', struct.pack('<f', math.nan))[0]

    assert _float32_bits(math.nan) == packed


def test_the_oracle_raises_on_out_of_range():
    """Values outside float32 range must raise, not silently saturate."""
    for value in [1e39, -1e39, 1e50, 3.5e38]:
        with pytest.raises(OverflowError, match='outside float32 range'):
            _float32_bits(value)


def test_vector_file_covers_both_message_types():
    """A silently empty parametrize list would make the vector tests vacuous."""
    assert len(_vectors_of_type('0x12')) >= 4
    assert len(_vectors_of_type('0x10')) >= 4


def test_max_params_matches_the_cpp_constant():
    """
    The frame-size constant duplicated above still matches the C++ header.

    Python cannot read a constexpr, so the value is copied. Re-deriving it
    from MAX_FRAME_SIZE here means changing the frame limit on the C++ side
    breaks this test rather than silently leaving the Python suite exercising
    a stale ceiling.
    """
    with open(CONSTANTS_HEADER) as f:
        header = f.read()

    match = re.search(r'MAX_FRAME_SIZE\s*=\s*(\d+)', header)
    assert match, 'MAX_FRAME_SIZE not found in protocol_constants.hpp'

    max_frame = int(match.group(1))
    # data = frame - station - function_code - CRC; params = data - flags - cmd_id.
    derived = max_frame - 1 - 1 - 2 - 1 - 1

    assert derived == MAX_CONTROL_PARAMS_SIZE, (
        f'protocol_constants.hpp implies {derived}, this file says '
        f'{MAX_CONTROL_PARAMS_SIZE}')
