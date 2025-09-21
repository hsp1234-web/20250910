#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Local Runner for the Wolf Project.

This script simulates the core startup process of `colabPro.py` but
operates on the local filesystem, skipping the Git clone and other
Colab-specific initializations. Its purpose is to provide a fast and
repeatable way to test the dependency installation and server startup logic.
"""

import logging
import os
import subprocess
import sys
import time
import threading
from pathlib import Path

# --- Basic Configuration ---
PROJECT_FOLDER_NAME = "."  # Use current directory as the project folder
LOG_LEVEL = logging.INFO
AUTO_EXIT_SECONDS = 120 # Seconds to wait before auto-terminating the server

# --- Logger Setup ---
logging.basicConfig(
    level=LOG_LEVEL,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    stream=sys.stdout
)
log = logging.getLogger('local_run')


def install_requirements(project_path: Path, req_files: list, log_prefix=""):
    """
    Helper function to check and install missing dependencies.
    This is a simplified version of the logic in colabPro.py.
    """
    log.info(f"[{log_prefix}] Starting dependency check and installation...")
    install_start_time = time.monotonic()

    checker_script = project_path / "scripts" / "check_deps.py"
    if not checker_script.is_file():
        log.critical(f"[{log_prefix}] Dependency checker script 'check_deps.py' not found!")
        raise FileNotFoundError("Dependency checker script not found.")

    req_file_paths = [str(p.resolve()) for p in req_files if p.is_file()]
    if not req_file_paths:
        log.info(f"[{log_prefix}] No valid requirement files found.")
        return

    log.info(f"[{log_prefix}] Checking for missing packages...")
    check_command = [sys.executable, str(checker_script.resolve())] + req_file_paths
    result = subprocess.run(check_command, capture_output=True, text=True, encoding='utf-8')

    # Always log stderr from the checker script for debugging purposes
    if result.stderr and result.stderr.strip():
        log.info(f"--- Begin check_deps.py stderr ---\n{result.stderr.strip()}\n--- End check_deps.py stderr ---")

    # If check_deps.py fails, fall back to installing all packages.
    if result.returncode != 0:
        log.warning(f"[{log_prefix}] 'check_deps.py' failed. Will attempt to install all packages from files.")
        all_packages = []
        for p in req_files:
            if p.is_file():
                for line in p.read_text(encoding='utf-8').strip().splitlines():
                    cleaned_line = line.strip()
                    if cleaned_line and not cleaned_line.startswith("#"):
                        all_packages.append(cleaned_line)
        missing_packages = all_packages
    else:
        missing_packages = result.stdout.strip().splitlines()

    if not missing_packages:
        log.info(f"✅ [{log_prefix}] All dependencies are satisfied. No installation needed.")
        return

    log.info(f"[{log_prefix}] Found {len(missing_packages)} missing packages. Attempting installation...")

    # Use pip to install the missing packages
    try:
        # We join them into a single command for efficiency
        pip_command = [sys.executable, "-m", "pip", "install"] + missing_packages
        log.info(f"[{log_prefix}] Running pip command: {' '.join(pip_command)}")

        # Use Popen to stream output in real-time
        process = subprocess.Popen(pip_command, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')

        for line in iter(process.stdout.readline, ''):
            log.info(f"[pip] {line.strip()}")

        process.wait()

        if process.returncode != 0:
            raise subprocess.CalledProcessError(process.returncode, pip_command)

        log.info(f"✅ [{log_prefix}] Dependency installation completed successfully.")
        log.info(f"--- [{log_prefix}] Installation took: {time.monotonic() - install_start_time:.2f} seconds ---")

    except subprocess.CalledProcessError as e:
        log.critical(f"[{log_prefix}] PIP INSTALLATION FAILED! Return code: {e.returncode}")
        raise
    except Exception as e:
        log.critical(f"[{log_prefix}] An unexpected error occurred during installation: {e}")
        raise


def main():
    """
    Main execution function with an auto-exit timer for testing.
    """
    log.info("--- [Local Runner Started] ---")
    project_path = Path(PROJECT_FOLDER_NAME).resolve()

    server_process = None
    try:
        # --- Stage 1: Install Dependencies ---
        log.info("--- Stage 1: Installing Core Dependencies ---")
        core_requirements = [
            project_path / "requirements" / "core.txt",
            project_path / "requirements" / "features_core.txt",
            project_path / "requirements" / "analysis.txt"
        ]
        install_requirements(project_path, core_requirements, "Core")

        # --- Stage 2: Launch Backend Orchestrator ---
        log.info("--- Stage 2: Launching Backend Orchestrator ---")
        launch_command = [sys.executable, "src/core/orchestrator.py"]

        process_env = os.environ.copy()
        src_path_str = str(project_path / "src")
        process_env['PYTHONPATH'] = f"{src_path_str}{os.pathsep}{process_env.get('PYTHONPATH', '')}".strip(os.pathsep)

        log.info(f"Starting orchestrator with command: {' '.join(launch_command)}")
        server_process = subprocess.Popen(
            launch_command,
            cwd=str(project_path),
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding='utf-8'
        )

        def stream_reader(stream):
            """Reads and logs a stream in a separate thread."""
            for line in iter(stream.readline, ''):
                log.info(f"[Orchestrator] {line.strip()}")
            log.info("[Orchestrator] Stream has ended.")

        reader_thread = threading.Thread(target=stream_reader, args=(server_process.stdout,))
        reader_thread.daemon = True
        reader_thread.start()

        log.info(f"Monitoring server for {AUTO_EXIT_SECONDS} seconds...")
        # Wait for the thread to finish, with a timeout.
        # The thread will only finish if the process terminates.
        reader_thread.join(timeout=AUTO_EXIT_SECONDS)

        if reader_thread.is_alive():
            log.info(f"✅ Server test running for {AUTO_EXIT_SECONDS} seconds. Assuming successful startup.")
        else:
            # If the thread is not alive, the process terminated before the timeout.
            if server_process.returncode != 0:
                log.error(f"❌ Server process exited prematurely with code: {server_process.returncode}")
            else:
                log.warning("Server process exited prematurely with code 0.")

    except (Exception, KeyboardInterrupt) as e:
        if isinstance(e, KeyboardInterrupt):
            log.warning("Keyboard interrupt detected. Shutting down...")
        else:
            log.critical(f"Local runner encountered a fatal error: {e}", exc_info=True)
    finally:
        if server_process and server_process.poll() is None:
            log.info("Terminating server process...")
            server_process.terminate()
            try:
                server_process.wait(timeout=10)
            except subprocess.TimeoutExpired:
                log.warning("Server process did not terminate gracefully. Killing.")
                server_process.kill()
        log.info("--- [Local Runner Finished] ---")


if __name__ == "__main__":
    main()
