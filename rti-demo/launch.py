#!/usr/bin/env python3
"""Unified RTI Demo Launch Script.

This script provides a single, consistent entry point for launching all RTI demo components.
It replaces fragmented startup paths and standardizes service management.

Usage:
    # Launch all demo services
    python launch.py all
    
    # Launch specific services
    python launch.py bff
    python launch.py fsp
    python launch.py so
    python launch.py acsi-client
    python launch.py acsi-server
    python launch.py frontend
    
    # Launch with custom port
    python launch.py bff --port 5005
    
    # Get help
    python launch.py --help
    python launch.py bff --help

Services:
    bff:        Backend for Frontend Server (default: port 5000)
    fsp:        RTI-FSP (default: port 5001)
    so:         RTI-SO (default: port 5002)
    frontend:   Web-based HMI (default: port 8080)
    all:        Launch all services
"""

import argparse
import asyncio
import json
import logging
import os
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from enum import Enum


# Configure logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ServiceType(Enum):
    """Available RTI demo service types."""
    BFF = "bff"
    FSP = "fsp"
    SO = "so"
    FRONTEND = "frontend"
    ALL = "all"


@dataclass
class ServiceConfig:
    """Configuration for a single RTI demo service."""
    name: str
    service_type: ServiceType
    module: str
    entry_point: str
    default_port: int
    description: str
    env_vars: Dict[str, str] = field(default_factory=dict)
    working_dir: Optional[str] = None
    docker_image: Optional[str] = None
    health_check_path: str = "/api/health"
    labels: Dict[str, str] = field(default_factory=dict)


# Service configurations
SERVICES: Dict[ServiceType, ServiceConfig] = {
    ServiceType.BFF: ServiceConfig(
        name="BFF Server",
        service_type=ServiceType.BFF,
        module="bff.bff_server",
        entry_point="bff/bff_server.py",
        default_port=5000,
        description="Backend for Frontend - REST API gateway",
        env_vars={"RTI_DOCKER_ENABLED": "true", "PORT": "5000"},
        docker_image="rti-demo-bff",
        health_check_path="/api/health",
        labels={
            "rti.service": "bff-server",
            "rti.type": "RTI-BFF",
            "rti.host": "bff-server",
            "rti.port": "5000"
        }
    ),
    ServiceType.FSP: ServiceConfig(
        name="FSP ACSI-Server_WebsocketActive",
        service_type=ServiceType.FSP,
        module="fsp.bff_endpoint",
        entry_point="fsp/bff_endpoint.py",
        default_port=5001,
        description="RTI-FSP",
        env_vars={"PORT": "5001"},
        docker_image="rti-demo-fsp",
        health_check_path="/api/status",
        labels={
            "rti.service": "rti-server",
            "rti.type": "RTI-FSP",
            "rti.host": "rti-server",
            "rti.port": "5001"
        }
    ),
    ServiceType.SO: ServiceConfig(
        name="SO ACSI-Client_WebsocketPassive",
        service_type=ServiceType.SO,
        module="so.bff_endpoint",
        entry_point="so/bff_endpoint.py",
        default_port=5002,
        description="RTI-SO",
        env_vars={"PORT": "5002"},
        docker_image="rti-demo-so",
        health_check_path="/api/status",
        labels={
            "rti.service": "rti-client",
            "rti.type": "RTI-SO",
            "rti.host": "rti-client",
            "rti.port": "5002"
        }
    ),
    ServiceType.FRONTEND: ServiceConfig(
        name="Frontend",
        service_type=ServiceType.FRONTEND,
        module="",
        entry_point="front-end/index.html",
        default_port=8080,
        description="Web-based Human Machine Interface",
        docker_image="rti-demo-frontend",
        health_check_path="/",
        working_dir="front-end"
    ),
}


class RTILauncher:
    """Main launcher class for RTI demo services."""
    
    def __init__(self):
        self.base_dir = Path(__file__).parent.resolve()
        self.running_services: Dict[ServiceType, subprocess.Popen] = {}
        self.service_ports: Dict[ServiceType, int] = {}
        self.verbose = False
    
    def parse_args(self, args: Optional[List[str]] = None) -> Tuple[List[ServiceType], Dict[str, str]]:
        """Parse command line arguments.
        
        Returns:
            Tuple of (services to launch, options dict)
        """
        parser = argparse.ArgumentParser(
            description="RTI Demo Launcher - Unified entry point for all RTI demo services",
            formatter_class=argparse.RawDescriptionHelpFormatter,
            epilog=self._get_epilog()
        )
        
        parser.add_argument(
            'service',
            nargs='*',
            default=[],
            help='Service(s) to launch (bff, fsp, so, acsi-client, acsi-server, frontend, all, list, help)'
        )
        parser.add_argument(
            '--port',
            type=int,
            help='Override default port for the service'
        )
        parser.add_argument(
            '--docker',
            action='store_true',
            help='Run services in Docker containers'
        )
        parser.add_argument(
            '--background',
            action='store_true',
            help='Run services in background (non-blocking)'
        )
        parser.add_argument(
            '--verbose', '-v',
            action='store_true',
            help='Show detailed logging'
        )
        parser.add_argument(
            '--stop',
            action='store_true',
            help='Stop running services'
        )
        parser.add_argument(
            '--status',
            action='store_true',
            help='Show status of running services'
        )
        parser.add_argument(
            '--config',
            type=str,
            default='launch_config.json',
            help='Configuration file for custom service settings'
        )
        
        # Parse known args
        args, unknown = parser.parse_known_args(args)
        
        # Handle special commands
        if 'list' in args.service or 'help' in args.service:
            self._print_service_info()
            sys.exit(0)
        
        # Convert service strings to ServiceType enums
        services = []
        for svc in args.service:
            if svc == 'all':
                services = list(ServiceType)
                break
            else:
                services.append(ServiceType(svc))
        
        # Only default to ALL if no services specified and no management flags
        if not services and not any([args.stop, args.status]):
            services = [ServiceType.ALL]
        
        # Build options dict
        options = {
            'port': args.port,
            'docker': args.docker,
            'background': args.background,
            'verbose': args.verbose or args.verbose,
            'stop': args.stop,
            'status': args.status,
            'config': args.config
        }
        
        return services, options
    
    def _get_epilog(self) -> str:
        """Get epilog text for help message."""
        lines = [
            "",
            "Available Services:",
            "-" * 60
        ]
        
        for svc_type, config in SERVICES.items():
            if svc_type == ServiceType.ALL:
                continue
            lines.append(
                f"  {svc_type.value:15} (port {config.default_port:5d}) - {config.description}"
            )
        
        lines.extend([
            "",
            "Examples:",
            "-" * 60,
            "  # Launch all services",
            "  python launch.py all",
            "",
            "  # Launch BFF server on port 5000",
            "  python launch.py bff",
            "",
            "  # Launch FSP ACSI-Server_WebsocketActive on custom port",
            "  python launch.py fsp --port 5010",
            "",
            "  # Launch with verbose logging",
            "  python launch.py bff so -v",
            "",
            "  # List available services",
            "  python launch.py list",
            "",
            "  # Show this help",
            "  python launch.py --help"
        ])
        
        return "\n".join(lines)
    
    def _print_service_info(self):
        """Print information about all available services."""
        print("\nRTI Demo Services:")
        print("=" * 80)
        
        for svc_type, config in SERVICES.items():
            if svc_type == ServiceType.ALL:
                continue
            
            print(f"\n{config.name} ({svc_type.value})")
            print("-" * 40)
            print(f"  Description: {config.description}")
            print(f"  Default Port: {config.default_port}")
            print(f"  Entry Point: {config.entry_point}")
            print(f"  Module: {config.module or 'N/A'}")
            print(f"  Docker Image: {config.docker_image or 'N/A'}")
            
            if config.labels:
                print(f"  Labels:")
                for k, v in config.labels.items():
                    print(f"    {k}={v}")
        
        print("\n" + "=" * 80)
    
    def _get_service_config(self, svc_type: ServiceType, port: Optional[int] = None) -> ServiceConfig:
        """Get configuration for a service with optional port override."""
        config = SERVICES[svc_type]
        
        if port is not None:
            config = ServiceConfig(
                name=config.name,
                service_type=config.service_type,
                module=config.module,
                entry_point=config.entry_point,
                default_port=port,
                description=config.description,
                env_vars={**config.env_vars, "PORT": str(port)},
                working_dir=config.working_dir,
                docker_image=config.docker_image,
                health_check_path=config.health_check_path,
                labels={**config.labels, "rti.port": str(port)} if config.labels else {}
            )
        
        return config
    
    def _launch_python_service(self, svc_type: ServiceType, config: ServiceConfig, 
                               background: bool = False) -> subprocess.Popen:
        """Launch a Python-based service."""
        entry_path = self.base_dir / config.entry_point
        
        if not entry_path.exists():
            logger.error(f"Entry point not found: {entry_path}")
            raise FileNotFoundError(f"Cannot find {config.entry_point}")
        
        # Build command
        cmd = [sys.executable, str(entry_path)]
        
        # Add environment variables
        env = os.environ.copy()
        env.update(config.env_vars)
        
        logger.info(f"Starting {config.name} on port {config.default_port}")
        logger.info(f"  Command: {' '.join(cmd)}")
        logger.info(f"  Working directory: {self.base_dir}")
        
        process = subprocess.Popen(
            cmd,
            cwd=self.base_dir,
            env=env,
            stdout=subprocess.PIPE if not self.verbose else None,
            stderr=subprocess.PIPE if not self.verbose else None,
            text=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        )
        
        self.running_services[svc_type] = process
        self.service_ports[svc_type] = config.default_port
        
        if not background:
            # Wait for process to complete (only for single foreground service)
            try:
                process.wait()
            except KeyboardInterrupt:
                self.stop_service(svc_type)
        
        return process
    
    def _launch_frontend(self, config: ServiceConfig, background: bool = False) -> subprocess.Popen:
        """Launch the frontend service."""
        frontend_dir = self.base_dir / "front-end"
        
        if not frontend_dir.exists():
            logger.error(f"Frontend directory not found: {frontend_dir}")
            raise FileNotFoundError(f"Cannot find front-end directory")
        
        # Use Python's http.server for simple serving
        # Note: --directory flag was added in Python 3.7+, fallback for older versions
        port = config.default_port
        try:
            # Try with --directory flag (Python 3.7+)
            cmd = [sys.executable, "-m", "http.server", str(port), "--directory", str(frontend_dir)]
        except:
            # Fallback to changing directory
            cmd = [sys.executable, "-m", "http.server", str(port)]
        
        logger.info(f"Starting {config.name} on port {config.default_port}")
        logger.info(f"  Command: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            cwd=str(frontend_dir),
            stdout=subprocess.PIPE if not self.verbose else None,
            stderr=subprocess.PIPE if not self.verbose else None,
            text=True,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if sys.platform == 'win32' else 0
        )
        
        self.running_services[ServiceType.FRONTEND] = process
        self.service_ports[ServiceType.FRONTEND] = config.default_port
        
        return process
    
    def launch_service(self, svc_type: ServiceType, port: Optional[int] = None,
                       docker: bool = False, background: bool = False) -> subprocess.Popen:
        """Launch a single service.
        
        Args:
            svc_type: The service type to launch
            port: Override the default port
            docker: Run in Docker container
            background: Run in background
            
        Returns:
            The subprocess.Popen object for the launched service
        """
        config = self._get_service_config(svc_type, port)
        
        if docker:
            return self._launch_docker_service(config, background)
        else:
            if svc_type == ServiceType.FRONTEND:
                return self._launch_frontend(config, background)
            else:
                return self._launch_python_service(svc_type, config, background)
    
    def _launch_docker_service(self, config: ServiceConfig, background: bool) -> subprocess.Popen:
        """Launch a service in Docker."""
        port = config.default_port
        
        # Build docker command
        cmd = [
            "docker", "run",
            "--rm",
            "-p", f"{port}:{port}",
            "--name", f"rti-{config.service_type.value}"
        ]
        
        # Add Docker labels for auto-discovery
        for key, value in config.labels.items():
            cmd.extend(["-l", f"{key}={value}"])
        
        # Add environment variables
        for key, value in config.env_vars.items():
            cmd.extend(["-e", f"{key}={value}"])
        
        # Add network
        cmd.extend(["--network", "rti-network"])
        
        # Add volume for Docker socket (for BFF service discovery)
        if config.service_type == ServiceType.BFF:
            cmd.extend(["-v", "/var/run/docker.sock:/var/run/docker.sock"])
        
        # Add image
        cmd.append(config.docker_image or f"rti-demo-{config.service_type.value}")
        
        logger.info(f"Starting Docker container: {' '.join(cmd)}")
        
        process = subprocess.Popen(
            cmd,
            stdout=subprocess.PIPE if not self.verbose else None,
            stderr=subprocess.PIPE if not self.verbose else None,
            text=True
        )
        
        self.running_services[config.service_type] = process
        self.service_ports[config.service_type] = port
        
        if not background:
            try:
                process.wait()
            except KeyboardInterrupt:
                self.stop_service(config.service_type)
        
        return process
    
    def launch_services(self, services: List[ServiceType], port: Optional[int] = None,
                        docker: bool = False, background: bool = False) -> List[subprocess.Popen]:
        """Launch multiple services.
        
        Args:
            services: List of service types to launch
            port: Base port number (only applies to first service if multiple)
            docker: Run services in Docker
            background: Run services in background
            
        Returns:
            List of subprocess.Popen objects for launched services
        """
        processes = []
        
        for i, svc_type in enumerate(services):
            if svc_type == ServiceType.ALL:
                # Launch all services
                all_services = [s for s in ServiceType if s != ServiceType.ALL]
                processes.extend(self.launch_services(
                    all_services, port, docker, background
                ))
                continue
            
            # Calculate port if base port provided
            actual_port = port if port else None
            if port and i > 0:
                actual_port = port + i
            
            process = self.launch_service(svc_type, actual_port, docker, background)
            processes.append(process)
            
            # Small delay between service starts
            time.sleep(1)
        
        return processes
    
    def stop_service(self, svc_type: ServiceType) -> bool:
        """Stop a running service.
        
        Args:
            svc_type: The service type to stop
            
        Returns:
            True if service was stopped, False if not found
        """
        if svc_type not in self.running_services:
            logger.warning(f"Service {svc_type.value} is not running")
            return False
        
        process = self.running_services[svc_type]
        
        try:
            if sys.platform == 'win32':
                # Windows: terminate the process tree
                subprocess.run(
                    ['taskkill', '/F', '/T', '/PID', str(process.pid)],
                    capture_output=True
                )
            else:
                # Unix: send SIGTERM
                process.terminate()
                process.wait(timeout=5)
            
            del self.running_services[svc_type]
            del self.service_ports[svc_type]
            
            logger.info(f"Stopped {svc_type.value} service")
            return True
            
        except Exception as e:
            logger.error(f"Error stopping {svc_type.value}: {e}")
            return False
    
    def stop_all_services(self) -> int:
        """Stop all running services.
        
        Returns:
            Number of services stopped
        """
        count = 0
        for svc_type in list(self.running_services.keys()):
            if self.stop_service(svc_type):
                count += 1
        return count
    
    def get_status(self) -> Dict[str, Dict]:
        """Get status of all running services.
        
        Returns:
            Dictionary with service status information
        """
        status = {}
        
        for svc_type, process in self.running_services.items():
            port = self.service_ports.get(svc_type, 0)
            
            # Check if process is still running
            return_code = process.poll()
            is_running = return_code is None
            
            status[svc_type.value] = {
                'name': SERVICES[svc_type].name,
                'port': port,
                'running': is_running,
                'return_code': return_code,
                'pid': process.pid
            }
        
        return status
    
    def check_health(self, host: str = "localhost", timeout: int = 5) -> Dict[str, bool]:
        """Check health of running services.
        
        Args:
            host: Hostname to check
            timeout: Request timeout in seconds
            
        Returns:
            Dictionary with service health status
        """
        import requests
        
        health = {}
        
        for svc_type, port in self.service_ports.items():
            config = SERVICES[svc_type]
            url = f"http://{host}:{port}{config.health_check_path}"
            
            try:
                response = requests.get(url, timeout=timeout)
                healthy = response.status_code < 400
            except Exception:
                healthy = False
            
            health[svc_type.value] = healthy
        
        return health
    
    def load_config(self, config_path: str) -> Dict:
        """Load configuration from JSON file.
        
        Args:
            config_path: Path to configuration file
            
        Returns:
            Configuration dictionary
        """
        try:
            with open(config_path, 'r') as f:
                return json.load(f)
        except FileNotFoundError:
            logger.warning(f"Config file not found: {config_path}")
            return {}
        except json.JSONDecodeError as e:
            logger.error(f"Invalid JSON in config file: {e}")
            return {}
    
    def save_config(self, config: Dict, config_path: str = "launch_config.json") -> bool:
        """Save configuration to JSON file.
        
        Args:
            config: Configuration dictionary
            config_path: Path to save configuration
            
        Returns:
            True if saved successfully
        """
        try:
            with open(config_path, 'w') as f:
                json.dump(config, f, indent=2)
            return True
        except Exception as e:
            logger.error(f"Failed to save config: {e}")
            return False


def main():
    """Main entry point for the RTI demo launcher."""
    launcher = RTILauncher()
    
    # Parse command line arguments
    services, options = launcher.parse_args()
    
    # Set verbose mode
    launcher.verbose = options['verbose']
    if options['verbose']:
        logger.setLevel(logging.DEBUG)
        logger.debug("Verbose logging enabled")
    
    # Handle status request
    if options.get('status'):
        status = launcher.get_status()
        print("\nService Status:")
        print("-" * 40)
        for svc, info in status.items():
            status_text = "RUNNING" if info['running'] else "STOPPED"
            print(f"  {svc:15} (port {info['port']:5d}) - {status_text}")
        
        # Check health if services are running
        if status:
            health = launcher.check_health()
            print("\nHealth Status:")
            print("-" * 40)
            for svc, healthy in health.items():
                health_text = "HEALTHY" if healthy else "UNHEALTHY"
                print(f"  {svc:15} - {health_text}")
        
        sys.exit(0)
    
    # Handle stop request
    if options.get('stop'):
        count = launcher.stop_all_services()
        print(f"Stopped {count} service(s)")
        sys.exit(0)
    
    # Launch services
    if not services:
        print("No services specified. Use 'python launch.py --help' for usage.")
        sys.exit(1)
    
    try:
        # Auto-enable background mode for multiple services
        use_background = options.get('background', False) or len(services) > 1
        processes = launcher.launch_services(
            services,
            port=options.get('port'),
            docker=options.get('docker', False),
            background=use_background
        )
        
        # Print summary
        print("\n" + "=" * 60)
        print("RTI Demo Services Launched")
        print("=" * 60)
        
        for svc_type, process in launcher.running_services.items():
            port = launcher.service_ports[svc_type]
            config = SERVICES[svc_type]
            print(f"  {svc_type.value:15} - port {port:5d} - {config.description}")
        
        print("\nAccess URLs:")
        for svc_type, port in launcher.service_ports.items():
            config = SERVICES[svc_type]
            if svc_type == ServiceType.FRONTEND:
                print(f"  http://localhost:{port}")
            else:
                print(f"  http://localhost:{port}{config.health_check_path}")
        
        print("=" * 60)
        
        if not use_background and len(launcher.running_services) == 1:
            # Single service in foreground - already handled by launch_service
            pass
        elif not use_background:
            # Multiple services - wait for all
            for process in processes:
                process.wait()
        else:
            # Background mode
            print("\nServices running in background. Use 'python launch.py --status' to check.")
        
    except KeyboardInterrupt:
        print("\nShutting down services...")
        launcher.stop_all_services()
        print("All services stopped.")
        sys.exit(0)
    except Exception as e:
        logger.error(f"Failed to launch services: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()