"""Local AI integration via Ollama for OfficeR smart writing and assistance."""

import json
import urllib.request
import urllib.error
from typing import List, Optional, Callable
from PySide6.QtCore import QObject, Signal, QThread


class OllamaWorker(QThread):
    """Background worker for non-blocking Ollama API requests."""

    finished = Signal(str)
    failed = Signal(str)

    def __init__(self, endpoint: str, model: str, prompt: str, system_prompt: str = ""):
        super().__init__()
        self.endpoint = endpoint
        self.model = model
        self.prompt = prompt
        self.system_prompt = system_prompt

    def run(self) -> None:
        payload = {
            "model": self.model,
            "prompt": self.prompt,
            "system": self.system_prompt,
            "stream": False
        }
        url = f"{self.endpoint.rstrip('/')}/api/generate"
        req = urllib.request.Request(
            url,
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"}
        )

        try:
            with urllib.request.urlopen(req, timeout=60) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                result_text = data.get("response", "")
                self.finished.emit(result_text)
        except Exception as e:
            self.failed.emit(str(e))


class OllamaClient(QObject):
    """Client for checking Ollama server availability and triggering AI generation."""

    def __init__(self, endpoint: str = "http://localhost:11434", parent: Optional[QObject] = None):
        super().__init__(parent)
        self.endpoint = endpoint
        self._workers: List[OllamaWorker] = []

    def is_available(self) -> bool:
        """Quick ping to check if Ollama daemon is running locally."""
        try:
            req = urllib.request.Request(f"{self.endpoint.rstrip('/')}/api/tags")
            with urllib.request.urlopen(req, timeout=1.5) as resp:
                return resp.status == 200
        except Exception:
            return False

    def list_models(self) -> List[str]:
        """Fetch available models installed in Ollama."""
        try:
            req = urllib.request.Request(f"{self.endpoint.rstrip('/')}/api/tags")
            with urllib.request.urlopen(req, timeout=2.0) as resp:
                data = json.loads(resp.read().decode("utf-8"))
                return [m["name"] for m in data.get("models", [])]
        except Exception:
            return []

    def generate_async(
        self,
        prompt: str,
        system_prompt: str = "",
        model: str = "llama3:latest",
        on_success: Optional[Callable[[str], None]] = None,
        on_error: Optional[Callable[[str], None]] = None
    ) -> OllamaWorker:
        worker = OllamaWorker(self.endpoint, model, prompt, system_prompt)
        if on_success:
            worker.finished.connect(on_success)
        if on_error:
            worker.failed.connect(on_error)
        worker.finished.connect(lambda: self._cleanup_worker(worker))
        worker.failed.connect(lambda: self._cleanup_worker(worker))
        self._workers.append(worker)
        worker.start()
        return worker

    def _cleanup_worker(self, worker: OllamaWorker) -> None:
        if worker in self._workers:
            self._workers.remove(worker)
