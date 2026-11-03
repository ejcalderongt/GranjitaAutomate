import unittest

from config import farm_preflight as f


class VerdictDiagnosticTypesTests(unittest.TestCase):
    def create(self, counters, constraint='C4'):
        return f.ConstraintVerdict(constraint, 'PASS', constraint+' DATOS_ACREDITADOS | alternativa: revisar fixture', counters)

    def test_each_integer_diagnostic_accepts_only_nonnegative_integers(self):
        for constraint, keys in (('C1', f.C1_DIAGNOSTIC_KEYS), ('C2', f.C2_DIAGNOSTIC_KEYS)):
            for key in keys:
                self.create({key: 0}, constraint)
                self.create({key: 2}, constraint)
                for value in (-1, True, 0.5, 'value', [], {}, None):
                    with self.assertRaisesRegex(ValueError, '^Veredicto sintetico invalido$'):
                        self.create({key: value}, constraint)

    def test_boolean_flags_are_typed_and_mutually_exclusive(self):
        for value in (False, True):
            self.create({'proxy_verified': value, 'proxy_skipped': False}, 'C2')
            self.create({'proxy_verified': False, 'proxy_skipped': value}, 'C2')
        self.create({'data_available': False})
        for key, constraint in (('proxy_verified', 'C2'), ('proxy_skipped', 'C2'), ('data_available', 'C4')):
            for value in (0, 1, 'false', None):
                with self.assertRaises(ValueError):
                    self.create({key: value}, constraint)
        with self.assertRaises(ValueError):
            self.create({'proxy_verified': True, 'proxy_skipped': True}, 'C2')

    def test_closed_error_map_and_list_types(self):
        self.create({'errors_by_kind': dict.fromkeys(f.C4_ERROR_KINDS, 0)})
        self.create({'distinct_per_attempt': [False, True], 'latency_ms_by_attempt': [0, 1]})
        bad = [
            {'errors_by_kind': {}}, {'errors_by_kind': {'unexpected': 1}},
            {'distinct_per_attempt': [1]}, {'distinct_per_attempt': [True]*33},
            {'latency_ms_by_attempt': [True]}, {'latency_ms_by_attempt': [-1]},
            {'latency_ms_by_attempt': [0]*33}, {'latency_ms_by_attempt': (0,)},
            {'unknown': 0}, {'checked': True}, {'proxy_verified': False},
            {'errors': 'private detail'}, {1: 0}, {'total': -1},
        ]
        for counters in bad:
            with self.assertRaisesRegex(ValueError, '^Veredicto sintetico invalido$'):
                self.create(counters)
        for key in f.C4_ERROR_KINDS:
            for value in (-1, True, 'value', None):
                bad_map = dict.fromkeys(f.C4_ERROR_KINDS, 0)
                bad_map[key] = value
                with self.assertRaises(ValueError):
                    self.create({'errors_by_kind': bad_map})

    def test_available_details_require_coherent_totals(self):
        result = dict(total=2, distinct=1, errors=1, timeouts=0)
        details = [dict(code='success', new_exit=True, latency_ms=0), dict(code='auth_error', new_exit=False, latency_ms=1)]
        counters = {**result, **f.c4_diagnostics(result, details)}
        self.create(counters)
        for change in ({'errors': 2}, {'attempts': 1}, {'distinct': 0}, {'latency_ms_by_attempt': []}):
            with self.assertRaises(ValueError):
                self.create({**counters, **change})
        self.create({**result, **f.c4_diagnostics(result)})

    def test_string_values_have_no_authorized_enum(self):
        for key in ('checked', 'data_available', 'errors_by_kind', 'distinct_per_attempt'):
            with self.assertRaises(ValueError):
                self.create({key: 'unapproved'})
