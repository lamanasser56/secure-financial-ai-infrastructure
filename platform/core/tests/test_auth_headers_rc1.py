"""Untrusted non-ASCII authorization headers reject without escaping the authentication boundary."""
from types import SimpleNamespace
import unittest

from agent_platform.ops.server import Handler as OpsHandler
from agent_platform.programs.redactor_server import Handler as RedactorHandler


class HeaderRobustnessRC1(unittest.TestCase):
    def test_ops_header_rejects_non_ascii(self):
        handler = SimpleNamespace(headers={'Authorization': 'Bearer é'}, server=SimpleNamespace(api_key='s' * 64))
        self.assertFalse(OpsHandler.authorized(handler))
        handler.headers['Authorization'] = 'Bearer ' + 's' * 64
        self.assertTrue(OpsHandler.authorized(handler))

    def test_redactor_header_rejects_non_ascii(self):
        handler = SimpleNamespace(headers={'Authorization': 'Bearer é'}, server=SimpleNamespace(keys={'synthetic': 's' * 64}))
        self.assertIsNone(RedactorHandler.client(handler))
        handler.headers['Authorization'] = 'Bearer ' + 's' * 64
        self.assertEqual(RedactorHandler.client(handler), 'synthetic')
