import unittest
from unittest.mock import patch

import numpy as np
from fastapi.testclient import TestClient

import app


class SpeechTests(unittest.TestCase):
    def test_breaks_and_plain_text(self):
        self.assertEqual(app.parse_segments('One, <break time="0.2s" /> two. <break time="0.4s" />'),
                         ['One,', 0.2, 'two.', 0.4])
        self.assertEqual(app.parse_segments('Hello world.'), ['Hello world.'])

    def test_invalid_breaks(self):
        for text in ('<break time="0s" /> hello', 'hello <break time="11s" />',
                     'hello <break time="0.2s">', 'hello <break time="oops" />',
                     'hello <break time="0.2s"', '<break time="0.2s" />'):
            with self.subTest(text=text), self.assertRaises(ValueError):
                app.parse_segments(text)
        with self.assertRaises(ValueError):
            app.parse_segments('hello ' + '<break time="2s" />' * 31)

    def test_silence_and_speed_are_applied_before_mp3_encoding(self):
        calls = []

        def pipeline(text, *, voice, speed):
            calls.append((text, voice, speed))
            yield None, None, np.ones(100, dtype=np.float32)

        class Encoded:
            returncode = 0
            stdout = b'ID3test'
            stderr = b''

        with patch.object(app, 'get_pipeline', return_value=pipeline), \
             patch.object(app.subprocess, 'run', return_value=Encoded()) as encode:
            result = app.synthesize('Hi <break time="0.2s" /> there', 'af_heart', 1.25)
        self.assertEqual(result, b'ID3test')
        self.assertEqual(calls, [('Hi', 'af_heart', 1.25), ('there', 'af_heart', 1.25)])
        samples = np.frombuffer(encode.call_args.kwargs['input'], dtype=np.float32)
        self.assertEqual(len(samples), 100 + 4800 + 100)
        self.assertTrue(np.all(samples[100:4900] == 0))

    def test_request_validation(self):
        client = TestClient(app.app)
        for body in ({'text': 'Hello', 'speed': 2.1}, {'text': 'Hello', 'speed': 0.1},
                     {'text': 'Hello', 'speed': 'NaN'},
                     {'text': '<break time="20s" /> hello'}):
            with self.subTest(body=body):
                self.assertEqual(client.post('/api/generate', json=body).status_code, 422)


if __name__ == '__main__':
    unittest.main()
