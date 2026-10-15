import base64
import io
from pathlib import Path
import shutil
import struct
import subprocess
import tempfile
import unittest
from unittest.mock import patch, Mock
import wave

import backend


def response(content="转录文本", finish_reason="stop", reasoning=""):
    result = Mock()
    result.json.return_value = {"choices": [{
        "finish_reason": finish_reason,
        "message": {"content": content, "reasoning_content": reasoning},
    }]}
    return result


class ModelTests(unittest.TestCase):
    def test_exact_model_aliases_and_defaults(self):
        for old, new in backend.RETIRED_MODELS.items():
            self.assertEqual(backend.normalize_model(" " + old + " "), new)
        for value in ("", "  ", None):
            self.assertEqual(backend.normalize_model(value), backend.DEFAULT_MODEL)
        for model in (backend.ASR_MODEL, "mimo-v2.5-tts", "custom-model"):
            self.assertEqual(backend.normalize_model(model), model)

    @patch("backend.requests.post")
    def test_flash_contract_keeps_prompt_endpoint_and_token_cap(self, post):
        post.return_value = response()
        self.assertEqual(backend.call_mimo_api("data:audio/wav;base64,AAAA", "mimo-v2.5", "逐字转录"), "转录文本")
        args, kwargs = post.call_args
        self.assertEqual(args, (backend.DEFAULT_API_ENDPOINT,))
        body = kwargs["json"]
        self.assertEqual(body["model"], "mimo-v2.6-flash")
        self.assertEqual(body["thinking"], {"type": "disabled"})
        self.assertEqual(body["max_completion_tokens"], 4096)
        self.assertEqual(body["messages"][1]["content"][1]["text"], "逐字转录")
        self.assertEqual(kwargs["timeout"], 120)

    @patch("backend.requests.post")
    def test_asr_uses_audio_only_contract(self, post):
        post.return_value = response()
        backend.call_mimo_api("data:audio/wav;base64,AAAA", backend.ASR_MODEL, "do not send this prompt")
        body = post.call_args.kwargs["json"]
        self.assertEqual(set(body), {"model", "messages", "asr_options"})
        self.assertEqual(body["asr_options"], {"language": "auto"})
        self.assertEqual(len(body["messages"]), 1)
        self.assertEqual(body["messages"][0]["role"], "user")
        self.assertEqual([x["type"] for x in body["messages"][0]["content"]], ["input_audio"])

    @patch("backend.requests.post")
    def test_asr_size_guard_does_not_call_api(self, post):
        with self.assertRaisesRegex(ValueError, "10 MB"):
            backend.call_mimo_api("A" * 10_000_001, backend.ASR_MODEL, "")
        post.assert_not_called()

    @patch("backend.requests.post")
    def test_custom_model_does_not_receive_mimo_only_thinking_parameter(self, post):
        post.return_value = response()
        backend.call_mimo_api("data:audio/wav;base64,AAAA", "custom-model", "prompt")
        self.assertNotIn("thinking", post.call_args.kwargs["json"])

    @patch("backend.requests.post")
    def test_reasoning_is_never_used_as_transcription(self, post):
        post.return_value = response(content="", reasoning="internal reasoning")
        with self.assertRaisesRegex(RuntimeError, "思考"):
            backend.call_mimo_api("unused", backend.DEFAULT_MODEL, "")
        post.return_value = response(content="real transcript", reasoning="internal reasoning")
        self.assertEqual(backend.call_mimo_api("unused", backend.DEFAULT_MODEL, ""), "real transcript")
        post.return_value = response(content="")
        self.assertEqual(backend.call_mimo_api("unused", backend.DEFAULT_MODEL, ""), "")

    @patch("backend.requests.post")
    def test_incomplete_response_is_not_reported_as_success(self, post):
        for reason in ("length", "content_filter", "repetition_truncation"):
            post.return_value = response(content="partial", finish_reason=reason)
            with self.assertRaisesRegex(RuntimeError, "未完整"):
                backend.call_mimo_api("unused", backend.DEFAULT_MODEL, "")

    @patch("backend.requests.post")
    def test_http_failure_propagates(self, post):
        post.return_value = response()
        post.return_value.raise_for_status.side_effect = backend.requests.HTTPError("HTTP 429")
        with self.assertRaises(backend.requests.HTTPError):
            backend.call_mimo_api("unused", backend.DEFAULT_MODEL, "")


class RouteTests(unittest.TestCase):
    def tearDown(self):
        for task in backend.tasks.values():
            shutil.rmtree(task.get("upload_dir", ""), ignore_errors=True)
        backend.tasks.clear()

    @patch("backend.threading.Thread")
    def test_missing_blank_and_retired_model_form_values(self, thread):
        client = backend.app.test_client()
        for model, expected in [(None, backend.DEFAULT_MODEL), (" ", backend.DEFAULT_MODEL),
                                ("mimo-v2-omni", backend.DEFAULT_MODEL),
                                ("mimo-v2.5-pro", "mimo-v2.6-pro"),
                                (backend.ASR_MODEL, backend.ASR_MODEL)]:
            data = {"file": (io.BytesIO(b"fixture audio"), "sample.wav")}
            if model is not None:
                data["model"] = model
            result = client.post("/api/transcribe", data=data)
            self.assertEqual(result.status_code, 200)
            self.assertEqual(thread.call_args.kwargs["args"][2], expected)
            result.close()

    @patch("backend.call_mimo_api")
    @patch("backend.split_wav", return_value=[])
    @patch("backend.get_audio_duration", return_value=0)
    @patch("backend.extract_audio")
    def test_empty_audio_task_fails_without_api_call(self, extract, duration, split, call):
        backend.tasks["empty"] = {"status": "queued"}
        backend.process_task("empty", "unused", backend.DEFAULT_MODEL, "")
        self.assertEqual(backend.tasks["empty"]["status"], "error")
        call.assert_not_called()

    @patch("backend.subprocess.run")
    @patch("backend.get_audio_duration", return_value=60)
    def test_ffmpeg_failure_is_not_silently_skipped(self, duration, run):
        run.return_value = subprocess.CompletedProcess([], 1, stderr="fixture ffmpeg error")
        with self.assertRaisesRegex(RuntimeError, "segment 1 failed"):
            backend.split_wav("unused", 60, "/unused")


@unittest.skipUnless(shutil.which("ffmpeg"), "FFmpeg is required for audio regression")
class AudioFlowTests(unittest.TestCase):
    tearDown = RouteTests.tearDown

    def test_real_ffmpeg_split_transcribe_status_and_markdown(self):
        # A deterministic non-speech waveform verifies plumbing, not ASR quality.
        with tempfile.TemporaryDirectory() as tmp:
            source = Path(tmp) / "stereo.wav"
            with wave.open(str(source), "wb") as wav:
                wav.setnchannels(2)
                wav.setsampwidth(2)
                wav.setframerate(8000)
                wav.writeframes(struct.pack('<hh', 1234, 2345) * (125 * 8000))
            client = backend.app.test_client()
            segments = []

            def mocked_api(endpoint, **kwargs):
                body = kwargs["json"]
                self.assertEqual(endpoint, backend.DEFAULT_API_ENDPOINT)
                self.assertEqual(body["model"], "mimo-v2.6-flash")
                uri = body["messages"][1]["content"][0]["input_audio"]["data"]
                with wave.open(io.BytesIO(base64.b64decode(uri.split(',', 1)[1])), "rb") as wav:
                    self.assertEqual((wav.getframerate(), wav.getnchannels(), wav.getsampwidth()), (16000, 1, 2))
                    segments.append((wav.getnframes(), wav.getframerate()))
                return response("第%d段" % len(segments))

            class ImmediateThread:
                def __init__(self, target, args, **kwargs):
                    self.target, self.args = target, args

                def start(self):
                    self.target(*self.args)

            with patch("backend.requests.post", side_effect=mocked_api) as post, patch("backend.threading.Thread", ImmediateThread):
                with source.open('rb') as file:
                    result = client.post('/api/transcribe', data={"file": (file, "stereo.wav"), "model": "mimo-v2.5"})
                self.assertEqual(result.status_code, 200)
                task_id = result.get_json()["task_id"]
                result.close()
                state = client.get('/api/status/' + task_id).get_json()
                self.assertEqual(state["status"], "done", state.get("error"))
                self.assertEqual((state["progress"], state["total"]), (3, 3))
                self.assertEqual([frames / rate for frames, rate in segments], [60, 60, 5])
                self.assertEqual(sum(frames for frames, _ in segments), 125 * 16000)
                self.assertEqual(state["segments"], ["第1段", "第2段", "第3段"])
                self.assertEqual(state["result"], "第1段\n第2段\n第3段")
                self.assertEqual(post.call_count, 3)
                saved = client.post('/api/save', json={"task_id": task_id, "output_dir": tmp}).get_json()
                markdown = Path(saved["path"]).read_text(encoding='utf-8')
                self.assertIn(state["result"], markdown)
                self.assertIn("### 第 3 段", markdown)


if __name__ == '__main__':
    unittest.main()
