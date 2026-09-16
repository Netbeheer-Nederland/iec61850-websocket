"""
IO Client File Server - Serves io_client files for dynamic loading by BFF endpoints.

This module provides REST API endpoints for serving io_client files that can be
used by the BFF (Backend for Frontend) to dynamically load IO functionality.

Endpoints:
- GET /api/io-plugin/files - List all available io_client files
- GET /api/io-plugin/files/{filename} - Download specific file content  
- GET /api/io-plugin/version - Get version information
- GET /api/io-plugin/health - Health check endpoint
"""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, List

from fastapi import APIRouter, HTTPException
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)


def create_io_client_router() -> APIRouter:
    """Create a FastAPI router for serving io_client files.
    
    This router provides endpoints for listing and downloading io_client files
    that can be used by BFF endpoints to dynamically load IO functionality.
    
    Returns:
        APIRouter instance with io-plugin file serving endpoints
    """
    router = APIRouter(
        prefix="/api/io-plugin",
        tags=["io-plugin-files"],
        responses={404: {"description": "Not found"}, 500: {"description": "Internal server error"}}
    )
    
    # Configuration for io_client files storage
    IO_CLIENT_FILES_DIR = os.getenv("IO_CLIENT_FILES_DIR", "/app/demo_IO/io_client")
    IO_CLIENT_VERSION = os.getenv("IO_CLIENT_VERSION", "1.0.0")
    
    def ensure_io_client_files_dir() -> bool:
        """Ensure the io_client files directory exists."""
        try:
            os.makedirs(IO_CLIENT_FILES_DIR, exist_ok=True)
            return True
        except Exception as e:
            logger.error(f"Failed to create io_client files directory: {e}")
            return False
    
    def get_io_client_file_path(filename: str) -> str:
        """Get the full path for an io_client file."""
        return os.path.join(IO_CLIENT_FILES_DIR, filename)
    
    def list_io_client_files() -> List[Dict[str, Any]]:
        """List all files in the io_client files directory."""
        if not ensure_io_client_files_dir():
            return []
        
        try:
            files = []
            for filename in os.listdir(IO_CLIENT_FILES_DIR):
                filepath = os.path.join(IO_CLIENT_FILES_DIR, filename)
                if os.path.isfile(filepath):
                    stat = os.stat(filepath)
                    files.append({
                        "name": filename,
                        "path": f"/api/io-plugin/files/{filename}",
                        "size": stat.st_size,
                        "modified": stat.st_mtime,
                        "download_url": f"/api/io-plugin/files/{filename}"
                    })
            return sorted(files, key=lambda x: x["name"])
        except Exception as e:
            logger.error(f"Error listing io_client files: {e}")
            return []
    
    @router.get(
        "/files",
        summary="List IO Client Files",
        description="Returns a list of all available io_client files that can be downloaded for dynamic loading.",
        response_description="List of available io_client files",
        responses={
            200: {"description": "List of files returned successfully"},
            500: {"description": "Error listing files"}
        },
        tags=["IO Client Files"]
    )
    async def api_list_io_client_files():
        """List all available io_client files."""
        try:
            ensure_io_client_files_dir()
            files = list_io_client_files()
            return {
                "ok": True,
                "files": files,
                "count": len(files),
                "directory": IO_CLIENT_FILES_DIR
            }
        except Exception as e:
            logger.error(f"Error in api_list_io_client_files: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get(
        "/files/{filename:path}",
        summary="Get IO Client File",
        description="Download a specific io_client file by filename. Used for dynamic loading of IO functionality.",
        response_description="File content",
        responses={
            200: {"description": "File content returned successfully"},
            404: {"description": "File not found"},
            500: {"description": "Error reading file"}
        },
        tags=["IO Client Files"]
    )
    async def api_get_io_client_file(filename: str):
        """Get the content of a specific io_client file."""
        try:
            file_path = get_io_client_file_path(filename)
            
            if not os.path.exists(file_path):
                logger.warning(f"IO client file not found: {filename}")
                raise HTTPException(
                    status_code=404, 
                    detail=f"IO client file '{filename}' not found"
                )
            
            if not os.path.isfile(file_path):
                raise HTTPException(
                    status_code=400,
                    detail=f"'{filename}' is not a file"
                )
            
            # Read and return file content
            with open(file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Set appropriate content type based on file extension
            content_type = "text/plain"
            if filename.endswith('.py'):
                content_type = "text/x-python"
            elif filename.endswith('.json'):
                content_type = "application/json"
            elif filename.endswith('.txt'):
                content_type = "text/plain"
            
            return JSONResponse(
                content={
                    "ok": True,
                    "filename": filename,
                    "content": content,
                    "size": len(content),
                    "content_type": content_type
                },
                media_type=content_type
            )
            
        except HTTPException:
            raise
        except Exception as e:
            logger.error(f"Error reading io_client file '{filename}': {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get(
        "/version",
        summary="Get IO Client Version",
        description="Returns version information for the io_client files and server.",
        response_description="Version information",
        responses={
            200: {"description": "Version information returned successfully"}
        },
        tags=["IO Client Files"]
    )
    async def api_get_io_client_version():
        """Get version information for io_client files."""
        try:
            ensure_io_client_files_dir()
            files = list_io_client_files()
            return {
                "ok": True,
                "version": IO_CLIENT_VERSION,
                "files_count": len(files),
                "files_available": [f["name"] for f in files],
                "api_version": "1.0.0"
            }
        except Exception as e:
            logger.error(f"Error in api_get_io_client_version: {e}")
            raise HTTPException(status_code=500, detail=str(e))
    
    @router.get(
        "/health",
        summary="IO Client Health Check",
        description="Health check endpoint for io_client file serving functionality.",
        response_description="Health status",
        responses={
            200: {"description": "Service is healthy"},
            500: {"description": "Service is unhealthy"}
        },
        tags=["Health"]
    )
    async def api_io_client_health():
        """Health check for io_client file serving."""
        try:
            ensure_io_client_files_dir()
            files = list_io_client_files()
            return {
                "status": "healthy",
                "service": "IO Client File Server",
                "files_directory": IO_CLIENT_FILES_DIR,
                "files_available": len(files) > 0,
                "files_count": len(files),
                "version": IO_CLIENT_VERSION
            }
        except Exception as e:
            logger.error(f"Error in io_client health check: {e}")
            return JSONResponse(
                content={
                    "status": "unhealthy",
                    "error": str(e)
                },
                status_code=500
            )
    
    return router