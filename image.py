"""
Unified Flask API service for retrieving container images from both local containerd runtime and Harbor registry.

This service combines two image sources:
1. Local containerd images via crictl
2. Harbor registry images via Harbor API v2.0

Key features:
- Unified endpoint for both image sources
- Configurable logging with file rotation
- JSON configuration file support
- Structured logging setup

Author:
    - Name: Anubhav Patrick
    - Email: anubhav.patrick@giindia.com
    - Date: 2025-06-06
"""

from flask import Flask, jsonify
import logging
from logging.handlers import RotatingFileHandler
import json
import os

# Import the API modules
from image_api import parse_crictl_images_output, load_ignored_image_ids
from harbor_api import get_harbor_paginated_results
import subprocess
from requests.auth import HTTPBasicAuth

app = Flask(__name__)

# --- Default Configuration ---
DEFAULT_CONFIG = {
    "crictl_config": {
        "ignore_file_path": "images_to_ignore.txt"
    },
    "harbor_config": {
        "url": "",
        "user": "",
        "password": "",
        "project_name": "",
        "page_size": 100,
        "verify_ssl": True
    },
    "app_config": {
        "host": "0.0.0.0",
        "port": 5000,
        "debug": False,
        "jsonify_prettyprint_regular": True,
        "log_file": "image_api.log",
        "log_max_bytes": 10485760,  # 10MB
        "log_backup_count": 3,
        "log_level_app": "WARNING",
        "log_level_file_handler": "WARNING"
    }
}

CONFIG_FILE_PATH = 'config.json'

def setup_logging(config):
    """Setup unified logging for the entire application."""
    # Get the root logger
    root_logger = logging.getLogger()
    
    # Remove any existing handlers
    for handler in root_logger.handlers[:]:
        root_logger.removeHandler(handler)
    
    # Configure RotatingFileHandler
    file_handler = RotatingFileHandler(
        config['app_config']['log_file'],
        maxBytes=config['app_config']['log_max_bytes'],
        backupCount=config['app_config']['log_backup_count']
    )
    
    # Create a formatter that includes the logger name
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s [%(name)s]: %(message)s '
        '[in %(pathname)s:%(lineno)d]'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(config['app_config']['log_level_file_handler'])
    
    # Add handler to root logger
    root_logger.addHandler(file_handler)
    root_logger.setLevel(config['app_config']['log_level_app'])
    
    # Get the Flask app logger and remove its default handlers
    for handler in app.logger.handlers[:]:
        app.logger.removeHandler(handler)
    
    # Add our handler to Flask logger
    app.logger.addHandler(file_handler)
    app.logger.setLevel(config['app_config']['log_level_app'])
    
    # Create a logger for this module
    logger = logging.getLogger(__name__)
    logger.info('Unified logging configured for all components')

def load_config(defaults, filepath):
    """Load configuration from file with defaults."""
    config = defaults.copy()
    try:
        with open(filepath, 'r') as f:
            file_config = json.load(f)
            # Deep merge for nested configuration
            for section in ['crictl_config', 'harbor_config', 'app_config']:
                if section in file_config:
                    config[section].update(file_config[section])
        app.logger.info(f"Configuration loaded from {filepath}")
    except Exception as e:
        app.logger.warning(f"Error loading config from {filepath}: {e}. Using defaults.")
    return config

@app.route('/images', methods=['GET'])
def get_all_images():
    """
    Get images from both local containerd and Harbor registry.
    Returns a combined list of images with their source specified.
    """
    logger = logging.getLogger(__name__)
    result = {
        "containerd_images": [],
        "harbor_images": [],
        "errors": []
    }

    # Get local containerd images
    try:
        process = subprocess.Popen(
            ['sudo', 'crictl', 'images'],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE
        )
        stdout, stderr = process.communicate(timeout=30)

        if process.returncode == 0:
            output = stdout.decode('utf-8')
            ignored_ids = load_ignored_image_ids(app.config['APP_SETTINGS']['crictl_config']['ignore_file_path'])
            result["containerd_images"] = parse_crictl_images_output(output, ignored_ids)
        else:
            error = stderr.decode('utf-8').strip()
            logger.error(f"Failed to execute crictl command: {error}")
            result["errors"].append({
                "source": "containerd",
                "error": f"Failed to execute crictl command: {error}"
            })
    except Exception as e:
        logger.error(f"Error getting containerd images: {str(e)}")
        result["errors"].append({
            "source": "containerd",
            "error": str(e)
        })

    # Get Harbor images
    harbor_cfg = app.config['APP_SETTINGS']['harbor_config']
    if all([harbor_cfg['url'], harbor_cfg['user'], harbor_cfg['password']]):
        try:
            auth = HTTPBasicAuth(harbor_cfg['user'], harbor_cfg['password'])
            projects_url = f"{harbor_cfg['url'].rstrip('/')}/api/v2.0/projects"
            projects = get_harbor_paginated_results(
                projects_url,
                auth,
                params={"with_detail": "false"},
                verify_ssl=harbor_cfg['verify_ssl']
            )

            harbor_images = []
            for project in projects:
                project_name = project['name']
                repos_url = f"{harbor_cfg['url'].rstrip('/')}/api/v2.0/projects/{project_name}/repositories"
                repositories = get_harbor_paginated_results(
                    repos_url,
                    auth,
                    verify_ssl=harbor_cfg['verify_ssl']
                )

                for repo in repositories:
                    repo_name = repo['name']
                    artifacts_url = f"{harbor_cfg['url'].rstrip('/')}/api/v2.0/projects/{project_name}/repositories/{repo_name}/artifacts"
                    artifacts = get_harbor_paginated_results(
                        artifacts_url,
                        auth,
                        verify_ssl=harbor_cfg['verify_ssl']
                    )

                    for artifact in artifacts:
                        if 'tags' in artifact and artifact['tags']:
                            for tag in artifact['tags']:
                                harbor_images.append({
                                    "repository": repo_name,
                                    "tag": tag['name'],
                                    "digest": artifact['digest'],
                                    "size": artifact.get('size', 'unknown'),
                                    "project": project_name
                                })

            result["harbor_images"] = harbor_images
            logger.info(f"Successfully retrieved {len(harbor_images)} Harbor images")
        except Exception as e:
            logger.error(f"Error getting Harbor images: {str(e)}")
            result["errors"].append({
                "source": "harbor",
                "error": str(e)
            })
    else:
        logger.warning("Harbor configuration incomplete")
        result["errors"].append({
            "source": "harbor",
            "error": "Harbor configuration incomplete"
        })

    return jsonify(result)

def main():
    # Load configuration
    app.config['APP_SETTINGS'] = load_config(DEFAULT_CONFIG, CONFIG_FILE_PATH)
    
    # Setup unified logging
    setup_logging(app.config['APP_SETTINGS'])
    
    # Configure Flask app
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = app.config['APP_SETTINGS']['app_config']['jsonify_prettyprint_regular']
    
    # Start the server
    logger = logging.getLogger(__name__)
    logger.info(
        f"Starting Unified Image API on "
        f"{app.config['APP_SETTINGS']['app_config']['host']}:"
        f"{app.config['APP_SETTINGS']['app_config']['port']} "
        f"with debug={app.config['APP_SETTINGS']['app_config']['debug']}"
    )
    
    app.run(
        host=app.config['APP_SETTINGS']['app_config']['host'],
        port=app.config['APP_SETTINGS']['app_config']['port'],
        debug=app.config['APP_SETTINGS']['app_config']['debug']
    )

if __name__ == '__main__':
    main() 