"""Serve the Windows launcher's built frontend and existing API directly."""

import argparse
from contextlib import ExitStack
from ipaddress import IPv4Address
from pathlib import Path
import socket

from starlette.exceptions import HTTPException
from starlette.staticfiles import StaticFiles
import uvicorn

_DIST = Path(__file__).resolve().parents[2] / "frontend" / "dist"


class BuiltCoach(StaticFiles):
    def __init__(self, directory, web_port):
        super().__init__(directory=directory, html=True)
        self.web_port = web_port

    async def get_response(self, path, scope):
        server = scope.get("server")
        request_path = scope["path"]
        if (server and server[1] != self.web_port) or request_path == "/api" or request_path.startswith("/api/"):
            raise HTTPException(status_code=404)
        response = await super().get_response(path, scope)
        if path in (".", "index.html", "service-worker.js", "manifest.webmanifest"):
            response.headers["Cache-Control"] = "no-cache"
        return response


def create_listener(stack, host, port):
    listener = stack.enter_context(socket.socket(socket.AF_INET, socket.SOCK_STREAM))
    if hasattr(socket, "SO_EXCLUSIVEADDRUSE"):
        listener.setsockopt(socket.SOL_SOCKET, socket.SO_EXCLUSIVEADDRUSE, 1)
    listener.bind((host, port))
    return listener


def main():
    from main import app

    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--api-port", type=int, required=True)
    parser.add_argument("--web-port", type=int, required=True)
    parser.add_argument("--lan", type=IPv4Address)
    args = parser.parse_args()
    if not 1 <= args.api_port <= 65535 or not 1 <= args.web_port <= 65535 or args.api_port == args.web_port:
        parser.error("the two ports must be distinct and between 1 and 65535")
    if args.lan and (args.lan.is_loopback or args.lan.is_unspecified or args.lan.is_multicast):
        parser.error("the LAN listener requires an assigned IPv4 interface address")
    app.mount("/", BuiltCoach(_DIST, args.web_port))
    config = uvicorn.Config(app, proxy_headers=False)
    with ExitStack() as stack:
        sockets = [
            create_listener(stack, "127.0.0.1", args.api_port),
            create_listener(stack, "127.0.0.1", args.web_port),
        ]
        if args.lan:
            sockets.append(create_listener(stack, str(args.lan), args.web_port))
        uvicorn.Server(config).run(sockets=sockets)


if __name__ == "__main__":
    main()
