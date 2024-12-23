# -*- coding: utf-8 -*-
import asyncio
from datetime import datetime
import sys
import os
import errno

import grpc
from django.utils import autoreload
from django.conf import settings
from django.core.management.base import BaseCommand
from django_grpc_framework.settings import grpc_settings

class Command(BaseCommand):
    help = 'Starts an asynchronous gRPC server.'

    # Validation is called explicitly each time the server is reloaded.
    requires_system_checks = []

    def add_arguments(self, parser):
        parser.add_argument(
            'address', nargs='?', default='[::]:50051',
            help='Optional address for which to open a port.'
        )
        parser.add_argument(
            '--max-workers', type=int, default=10, dest='max_workers',
            help='Number of maximum worker threads.'
        )
        parser.add_argument(
            '--dev', action='store_true', dest='development_mode',
            help=(
                'Run the server in development mode. This tells Django to use '
                'the auto-reloader and run checks.'
            )
        )

    def handle(self, *args, **options):
        self.address = options['address']
        self.development_mode = options['development_mode']
        self.max_workers = options['max_workers']
        asyncio.run(self.run(**options))

    async def run(self, **options):
        """Run the server, using the autoreloader if needed."""
        if self.development_mode:
            if hasattr(autoreload, "run_with_reloader"):
                autoreload.run_with_reloader(self.inner_run, **options)
            else:
                autoreload.main(self.inner_run, None, options)
        else:
            self.stdout.write(f"Starting gRPC server at {self.address}\n")
            await self._serve()

    async def _serve(self):
        server = grpc.aio.server(
            options=grpc_settings.SERVER_OPTIONS,
            interceptors=grpc_settings.SERVER_INTERCEPTORS
        )
        grpc_settings.ROOT_HANDLERS_HOOK(server)
        server.add_insecure_port(self.address)

        self.stdout.write("gRPC server started and listening.")
        await server.start()

        try:
            await server.wait_for_termination()
        except asyncio.CancelledError:
            self.stdout.write("Shutting down gRPC server...")
            await server.stop(grace=None)

    def inner_run(self, *args, **options):
        autoreload.raise_last_exception()

        self.stdout.write("Performing system checks...\n\n")
        self.check(display_num_errors=True)
        self.check_migrations()
        now = datetime.now().strftime('%B %d, %Y - %X')
        self.stdout.write(now)
        quit_command = 'CTRL-BREAK' if sys.platform == 'win32' else 'CONTROL-C'
        self.stdout.write((
            "Django version %(version)s, using settings %(settings)r\n"
            "Starting development gRPC server at %(address)s\n"
            "Quit the server with %(quit_command)s.\n"
        ) % {
            "version": self.get_version(),
            "settings": settings.SETTINGS_MODULE,
            "address": self.address,
            "quit_command": quit_command,
        })

        try:
            asyncio.run(self._serve())
        except OSError as e:
            ERRORS = {
                errno.EACCES: "You don't have permission to access that port.",
                errno.EADDRINUSE: "That port is already in use.",
                errno.EADDRNOTAVAIL: "That IP address can't be assigned to.",
            }
            error_text = ERRORS.get(e.errno, str(e))
            self.stderr.write(f"Error: {error_text}")
            os._exit(1)
        except KeyboardInterrupt:
            sys.exit(0)