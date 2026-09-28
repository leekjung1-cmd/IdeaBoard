"""폰 앱과 아이디어 맞추기: 집 와이파이 안에서만 쓰는 작은 서버 (자막 공부 앱과 같은 방식).

- 폰이 PC를 찾을 수 있게 UDP로 "여기 있어요"에 답한다 (DISCOVERY_PORT).
- 처음 한 번 PC 화면의 6자리 코드를 폰에 입력하면 긴 열쇠(token)를 주고, 그 뒤로는 열쇠로만 받는다.
- 코드를 여러 번 틀리면 잠시 막는다.
DB는 Qt 메인 스레드에서만 다루도록, 받은 요청은 큐에 넣고 메인 스레드가 처리한 결과를 돌려준다.
"""
import ipaddress
import json
import queue
import secrets
import socket
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

SYNC_PORT = 47332
DISCOVERY_PORT = 47333
DISCOVERY_ASK = b"IDEA_BOARD_FIND"
MAX_FAILS, LOCK_SECONDS = 5, 300


def is_home_network(addr):
    """집 안(사설망)에서 온 요청인지. PC가 공인 IP로 인터넷에 바로 물려 있어도 밖에서는 못 들어오게."""
    try:
        ip = ipaddress.ip_address(addr)
    except ValueError:
        return False
    return ip.is_private or ip.is_loopback


def local_ip():
    """이 PC의 와이파이/랜 주소 (실제로 밖으로 보내지는 않는다)."""
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.connect(("10.255.255.255", 1))
        return s.getsockname()[0]
    except OSError:
        return "127.0.0.1"
    finally:
        s.close()


class SyncServer:
    HOST = "0.0.0.0"  # 집 와이파이의 폰이 들어올 수 있게 (테스트에서는 127.0.0.1)

    def __init__(self, config_path, handle):
        """handle(요청 dict) → 응답 dict. 메인 스레드에서 poll()로 실행된다."""
        self.config_path = Path(config_path)
        self.handle = handle
        self.jobs = queue.Queue()
        self.fails = 0
        self.locked_until = 0.0
        self.last = None  # 마지막 맞추기 정보 (화면 표시용)
        self.error = None
        self.servers = []
        self.config = self._load()

    # ---- 설정 (코드와 열쇠) ----
    def _load(self):
        try:
            config = json.loads(self.config_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            config = {}
        config.setdefault("code", self._new_code())
        config.setdefault("tokens", {})
        config.setdefault("name", socket.gethostname())
        self._save(config)
        return config

    def _save(self, config=None):
        self.config_path.parent.mkdir(parents=True, exist_ok=True)
        self.config_path.write_text(json.dumps(config or self.config, ensure_ascii=False, indent=1), encoding="utf-8")

    @staticmethod
    def _new_code():
        return f"{secrets.randbelow(1000000):06d}"

    @property
    def code(self):
        return self.config["code"]

    @property
    def running(self):
        return bool(self.servers)

    def devices(self):
        return list(self.config["tokens"].values())

    def reset_code(self):
        """새 코드를 만들고 기존에 연결된 폰은 모두 끊는다."""
        self.config["code"] = self._new_code()
        self.config["tokens"] = {}
        self._save()

    # ---- 서버 ----
    def start(self):
        server = self

        class Handler(BaseHTTPRequestHandler):
            def log_message(self, *args):
                pass

            def _reply(self, code, data):
                body = json.dumps(data, ensure_ascii=False).encode("utf-8")
                self.send_response(code)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

            def _body(self):
                length = int(self.headers.get("Content-Length", 0))
                return json.loads(self.rfile.read(length) or b"{}")

            def do_POST(self):
                if not is_home_network(self.client_address[0]):
                    self._reply(403, {"ok": False, "message": "집 와이파이 안에서만 연결할 수 있어요"})
                    return
                try:
                    body = self._body()
                except (ValueError, json.JSONDecodeError):
                    self._reply(400, {"ok": False})
                    return
                if self.path == "/pair":
                    self._reply(*server._pair(body))
                    return
                token = self.headers.get("X-Sync-Token", "")
                if token not in server.config["tokens"]:
                    self._reply(401, {"ok": False, "message": "연결 코드를 다시 입력해 주세요"})
                    return
                if self.path != "/sync":
                    self._reply(404, {"ok": False})
                    return
                body["device"] = server.config["tokens"][token].get("device", "폰")
                done = threading.Event()
                job = {"request": body, "done": done, "result": None}
                server.jobs.put(job)
                if done.wait(30):
                    self._reply(200, job["result"])
                else:
                    self._reply(503, {"ok": False, "message": "PC 프로그램이 응답하지 않아요"})

        try:
            http = ThreadingHTTPServer((self.HOST, SYNC_PORT), Handler)
        except OSError as e:
            self.error = f"폰 연결을 받을 수 없어요 ({e})"
            return False
        self.servers.append(http)
        threading.Thread(target=http.serve_forever, daemon=True).start()
        threading.Thread(target=self._discovery, daemon=True).start()
        return True

    def _pair(self, body):
        if time.time() < self.locked_until:
            return 429, {"ok": False, "message": "코드를 여러 번 틀려서 5분 동안 막혀 있어요"}
        if str(body.get("code", "")).strip() != self.code:
            self.fails += 1
            if self.fails >= MAX_FAILS:
                self.fails = 0
                self.locked_until = time.time() + LOCK_SECONDS
            return 403, {"ok": False, "message": "코드가 맞지 않아요"}
        self.fails = 0
        token = secrets.token_hex(24)
        self.config["tokens"][token] = {"device": str(body.get("device", "폰"))[:60],
                                        "paired": time.strftime("%Y-%m-%d %H:%M")}
        self._save()
        return 200, {"ok": True, "token": token, "name": self.config["name"]}

    def _discovery(self):
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.bind((self.HOST, DISCOVERY_PORT))
        except OSError:
            return
        while True:
            try:
                data, addr = sock.recvfrom(256)
            except OSError:
                return
            if data.strip() == DISCOVERY_ASK and is_home_network(addr[0]):
                reply = json.dumps({"app": "idea-board", "port": SYNC_PORT, "name": self.config["name"]})
                sock.sendto(reply.encode("utf-8"), addr)

    def poll(self):
        """메인 스레드에서 주기적으로 호출."""
        while True:
            try:
                job = self.jobs.get_nowait()
            except queue.Empty:
                return
            try:
                job["result"] = self.handle(job["request"])
                self.last = {"device": job["request"].get("device", "폰"), "at": time.strftime("%H:%M:%S")}
            except Exception as e:
                job["result"] = {"ok": False, "message": f"오류: {e}"}
            job["done"].set()

    def stop(self):
        for s in self.servers:
            s.shutdown()
            s.server_close()
