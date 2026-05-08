"""Entry point for the AsynapRous sample chat web application."""

import argparse
import os

from apps import create_sampleapp

PORT = 2026


if __name__ == "__main__":
    parser = argparse.ArgumentParser(prog="SampleApp", epilog="AsynapRous app")
    parser.add_argument("--server-ip", default="0.0.0.0")
    parser.add_argument("--server-port", type=int, default=PORT)
    parser.add_argument(
        "--async-mode",
        choices=["threading", "callback", "coroutine"],
        default=None,
        help="Concurrency mode. Overrides ASYNC_MODE environment variable.",
    )
    args = parser.parse_args()

    if args.async_mode:
        os.environ["ASYNC_MODE"] = args.async_mode
    create_sampleapp(args.server_ip, args.server_port)
