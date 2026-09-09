"""Regression coverage for Streamlit reruns, using the real UI and a mocked API.

Run: python -m unittest discover -s frontend/tests
"""
import sys
import unittest
from pathlib import Path
from unittest.mock import patch

import requests
from streamlit.testing.v1 import AppTest

FRONTEND = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(FRONTEND))


class ChatUITests(unittest.TestCase):
    def setUp(self):
        self.health = patch('api_client.check_backend_health', return_value={'status': 'ok'})
        self.ask = patch('api_client.ask_question', return_value={
            'answer': '## An explanation\n\nSupported **information**.',
            'sources': ['reference.pdf'], 'disclaimer': 'Educational information.',
            'guardrail': None,
        })
        self.health.start()
        self.api = self.ask.start()
        self.addCleanup(self.health.stop)
        self.addCleanup(self.ask.stop)
        self.app = AppTest.from_file(str(FRONTEND / 'app.py')).run()

    def test_same_suggestion_submits_twice_after_an_intervening_rerun(self):
        self.app.button(key='suggestion_tsh').click().run()
        self.app.run()
        self.assertEqual(self.api.call_count, 1)
        self.app.button(key='suggestion_tsh').click().run()
        self.assertEqual(self.api.call_count, 2)
        self.assertEqual(self.api.call_args_list[0], self.api.call_args_list[1])
        self.assertEqual(len(self.app.session_state.messages), 4)
        self.assertEqual(self.app.session_state.submission_sequence, 2)
        self.assertFalse(self.app.exception)

    def test_typed_question_clear_and_suggestions_remain_usable(self):
        self.app.chat_input[0].set_value('What is a goiter?').run()
        self.assertEqual(self.api.call_count, 1)
        self.app.button(key='new_chat').click().run()
        self.assertEqual(self.app.session_state.messages, [])
        self.app.button(key='suggestion_goiter').click().run()
        self.assertEqual(self.api.call_count, 2)
        self.assertEqual(len(self.app.session_state.messages), 2)

    def test_connection_error_does_not_block_retry(self):
        self.api.side_effect = requests.ConnectionError('internal address must not appear')
        self.app.button(key='suggestion_goiter').click().run()
        self.assertIsNone(self.app.session_state.pending_submission)
        self.assertTrue(self.app.session_state.messages[-1]['request_error'])
        self.assertNotIn('internal address', self.app.session_state.messages[-1]['answer'])
        self.api.side_effect = None
        self.app.button(key='suggestion_goiter').click().run()
        self.assertEqual(self.api.call_count, 2)
        self.assertFalse(self.app.exception)

    def test_guardrail_and_untrusted_text_are_rendered_safely(self):
        self.api.return_value = {'answer': 'Contact emergency services.', 'sources': [],
                                 'disclaimer': '', 'guardrail': 'emergency'}
        self.app.chat_input[0].set_value('<script>alert("test")</script>').run()
        markdown = '\n'.join(item.value for item in self.app.markdown)
        self.assertIn('&lt;script&gt;', markdown)
        self.assertIn('Please seek urgent help', markdown)
        self.assertIn('Contact emergency services.', markdown)
        self.assertFalse(self.app.exception)


if __name__ == '__main__':
    unittest.main()
