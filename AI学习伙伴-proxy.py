#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AI学习伙伴 · 本地中转代理（零依赖，仅用 Python 标准库）
================================================================
解决什么问题：
    智谱 open.bigmodel.cn 等厂商的网关不返回跨域头（CORS），
    浏览器里的网页无法直接调用。这个小代理替浏览器去调厂商，
    再把结果原样转回来，并补上跨域头。

怎么用：
    1. 命令行运行：  python AI学习伙伴-proxy.py
    2. 打开 AI学习伙伴 → 左下角「⚙ AI 设置」
    3. 服务商选「智谱」，填好 API Key
    4. 把「接口地址」改成：  http://localhost:8787/v1/chat/completions
    5. 点「测试连接」，通过后「保存并关闭」

想中转别家：改下面的 UPSTREAM（保持到「/chat/completions」之前的那段）。
注意：仅供本机自用，不要暴露到公网 —— 谁都能连上这个端口用你的 Key。
"""
import json
import sys
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import urllib.request
import urllib.error

PORT = 8787
UPSTREAM = "https://open.bigmodel.cn/api/paas/v4"   # 智谱；换成别家只改这里


class Handler(BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"

    # ---------- 跨域头：浏览器能否放行就看这三个 ----------
    def _cors(self):
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Headers", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")

    def do_OPTIONS(self):
        self.send_response(204)
        self._cors()
        self.send_header("Content-Length", "0")
        self.end_headers()

    def do_GET(self):
        self._proxy("GET")

    def do_POST(self):
        self._proxy("POST")

    def _proxy(self, method):
        # 页面统一用 /v1/... 路径，这里改写成厂商真实路径
        path = self.path.replace("/v1/", "/api/paas/v4/", 1) \
            if "bigmodel" in UPSTREAM else self.path
        length = int(self.headers.get("Content-Length") or 0)
        body = self.rfile.read(length) if length else None

        req = urllib.request.Request(UPSTREAM + path, data=body, method=method)
        for k in ("Authorization", "Content-Type", "Accept"):
            v = self.headers.get(k)
            if v:
                req.add_header(k, v)

        try:
            r = urllib.request.urlopen(req, timeout=300)
        except urllib.error.HTTPError as e:
            r = e                      # 4xx/5xx 也要原样转回给页面看
        except Exception as e:
            payload = json.dumps({"error": {"message": str(e)}}).encode("utf-8")
            self.send_response(502)
            self._cors()
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return

        code = getattr(r, "status", None) or getattr(r, "code", 200)
        self.send_response(code)
        self._cors()
        self.send_header("Content-Type", r.headers.get("Content-Type", "application/json"))
        self.send_header("Transfer-Encoding", "chunked")
        self.end_headers()

        # 流式转发：SSE 一段一段读、一段一段写，保证打字机效果不丢
        try:
            while True:
                chunk = r.read(1024)
                if not chunk:
                    break
                self.wfile.write(b"%x\r\n" % len(chunk) + chunk + b"\r\n")
                self.wfile.flush()
            self.wfile.write(b"0\r\n\r\n")
            self.wfile.flush()
        except (BrokenPipeError, ConnectionAbortedError):
            pass                       # 页面点了「停止」，正常

    def log_message(self, fmt, *args):
        sys.stderr.write("[proxy] " + (fmt % args) + "\n")


if __name__ == "__main__":
    print("=" * 62)
    print("  AI学习伙伴 中转代理已启动")
    print("  接口地址： http://localhost:%d/v1/chat/completions" % PORT)
    print("  上游：     %s" % UPSTREAM)
    print("  保持本窗口开着，去「⚙ AI 设置」里把接口地址改成上面那行。")
    print("  退出：按 Ctrl+C")
    print("=" * 62)
    try:
        ThreadingHTTPServer(("127.0.0.1", PORT), Handler).serve_forever()
    except KeyboardInterrupt:
        print("\n已退出")
