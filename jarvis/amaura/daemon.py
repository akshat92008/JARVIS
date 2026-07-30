"""Autonomous execution daemon for the Amaura internal workforce."""

import signal
import sys
import time
from typing import Any

from jarvis import ui
from jarvis.amaura.control_plane import AmauraControlPlane
from jarvis.amaura.graph_supervisor import LangGraphSupervisor


class AmauraDaemon:
    """Continuously runs the graph supervisor to process tasks asynchronously."""

    def __init__(self, poll_interval: int = 5):
        self.poll_interval = poll_interval
        self.running = False
        self.control = AmauraControlPlane()
        self.supervisor = LangGraphSupervisor(self.control, worker_id="daemon")

    def start(self) -> None:
        """Start the infinite polling loop."""
        ui.print_info("Starting Amaura Workforce Daemon...")
        self.running = True

        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        ui.print_success(f"Daemon running. Polling interval: {self.poll_interval}s. Waiting for tasks...")
        
        while self.running:
            try:
                state = self.supervisor.tick()
                status = state.get("status")
                
                # 'idle' means no claimable task was found in the queue
                if status == "idle":
                    time.sleep(self.poll_interval)
                elif status == "failed":
                    error = state.get("error", "Unknown error")
                    ui.print_error(f"Task execution failed: {error}")
                    time.sleep(self.poll_interval)
                elif status == "finished":
                    ui.print_success("Task executed successfully.")
                else:
                    ui.print_info(f"Task status updated: {status}")
            except Exception as e:
                ui.print_error(f"Daemon encountered a fatal error during tick: {e}")
                time.sleep(self.poll_interval)
                
        ui.print_info("Amaura Workforce Daemon shut down successfully.")
        self.control.close()

    def stop(self, signum: Any = None, frame: Any = None) -> None:
        """Gracefully handle termination signals."""
        if not self.running:
            return
        ui.print_info("\nReceived shutdown signal. Stopping daemon gracefully... waiting for current tick to finish.")
        self.running = False


def start_daemon() -> None:
    """Entry point for the autonomous daemon."""
    daemon = AmauraDaemon()
    daemon.start()
