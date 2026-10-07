"""Independent exact integer/calendar goldens and fail-closed native parsing."""
import calendar
from datetime import datetime, timedelta
import random
import unittest

import duckdb
from equity_feature_contracts.adapters import SourceError
from equity_feature_duckdb import parse_utc_ns
from equity_feature_duckdb.reader import _create_utc_parser


class NativeTimestampTests(unittest.TestCase):
    def test_literal_and_independent_calendar_integer_goldens(self):
        fixtures = [
            ('1970-01-01T00:00:00Z', 0),
            ('1970-01-01 00:00:00.000000001+00:00', 1),
            ('1969-12-31T23:59:59.999999999Z', -1),
            ('2000-02-29T12:34:56.123456789Z', 951827696123456789),
            ('2262-04-11T23:47:16.854775807Z', 2**63-1),
            ('1677-09-21T00:12:43.145224192Z', -2**63),
        ]
        rng = random.Random(5501)
        for _ in range(250):
            date = datetime(1800, 1, 1) + timedelta(days=rng.randrange(100000), seconds=rng.randrange(86400))
            digits = rng.randrange(1, 10)
            fraction = rng.randrange(10**digits)
            text = date.isoformat() + f'.{fraction:0{digits}d}' + ('Z' if rng.randrange(2) else '+00:00')
            expected = calendar.timegm(date.timetuple()) * 10**9 + fraction * 10**(9-digits)
            fixtures.append((text, expected))
        with duckdb.connect() as con:
            _create_utc_parser(con)
            for text, expected in fixtures:
                with self.subTest(text=text):
                    self.assertEqual(con.execute('SELECT canonical_utc_ns(?::VARCHAR)', [text]).fetchone()[0], expected)
                    self.assertEqual(parse_utc_ns(text), expected)

    def test_null_non_iso_calendar_clock_fraction_and_bounds_reject(self):
        invalid = (None, '', '2026-02-29T00:00:00Z', '2000-02-30T00:00:00Z',
                   '0000-01-01T00:00:00Z', '1970-01-01T24:00:00Z',
                   '1970-01-01T00:60:00Z', '1970-01-01T00:00:60Z',
                   '1970-01-01T00:00:00.Z', '1970-01-01T00:00:00.1234567890Z',
                   '1970-01-01T00:00:00+01:00', '1970-01-01T00:00:00',
                   '1970-01-01T00:00:00Z ', '1970-01-01T٠٠:00:00Z',
                   '1970-01-01T00:00:00.١Z',
                   '2262-04-11T23:47:16.854775808Z',
                   '1677-09-21T00:12:43.145224191Z',
                   '9999-12-31T23:59:59Z', '0001-01-01T00:00:00Z')
        with duckdb.connect() as con:
            _create_utc_parser(con)
            for text in invalid:
                with self.subTest(text=text):
                    with self.assertRaises(duckdb.Error):
                        con.execute('SELECT canonical_utc_ns(?::VARCHAR)', [text]).fetchall()
                    with self.assertRaises(SourceError):
                        parse_utc_ns(text)
