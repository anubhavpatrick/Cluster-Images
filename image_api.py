"""
Flask API service for retrieving container images from the local container runtime.

This service provides a REST API endpoint to fetch container images using the crictl command-line tool.
Key features:
- Retrieves container images via crictl
- Filters out images based on a configurable ignore list
- Configurable logging with file rotation
- JSON configuration file support with sensible defaults
- Structured logging setup with customizable parameters

The API is designed to be run as a service and provides a clean interface for container image management.

Author:
    - Name: Anubhav Patrick
    - Email: anubhav.patrick@giindia.com
    - Date: 2025-06-05
"""

from flask import Flask, jsonify
import subprocess
import logging
from logging.handlers import RotatingFileHandler
import os
import csv
import json # Import json module

app = Flask(__name__)


# --- Default Configuration ---
DEFAULT_CONFIG = {
    "ignore_file_path": "images_to_ignore.txt",
    "log_file": "crictl_api.log",
    "log_max_bytes": 10 * 1024 * 1024,  # 10MB
    "log_backup_count": 3,
    "app_host": "0.0.0.0",
    "app_port": 5000,
    "app_debug": True, # Set to False in production
    "file_handler_log_level": "WARNING",  
    "app_log_level": "WARNING",
    "jsonify_prettyprint_regular": True 
}
CONFIG_FILE_PATH = 'config.json'


def load_app_config(defaults : dict, filepath : str) -> dict:
    """Loads configuration from a JSON file, merging with defaults.
    
    Args:
        defaults (dict): The default configuration values.
        filepath (str): The path to the configuration file.

    Returns:
        dict: The merged configuration.
    """
    config = defaults.copy()
    try:
        with open(filepath, 'r') as f:
            try:
                file_config = json.load(f)
                config.update(file_config) # update the config with the values from the file if they exist
                # Ensure numeric types for specific keys if they exist in file_config
                for key in ['log_max_bytes', 'log_backup_count', 'app_port']:
                    if key in file_config and not isinstance(config[key], int):
                        try:
                            # convert the value to an integer if it is a string
                            config[key] = int(config[key])
                        except ValueError:
                            app.logger.warning(f"Config value for '{key}' ('{config[key]}') is not a valid integer. Using default: {defaults[key]}")
                            config[key] = defaults[key]
                if 'app_debug' in file_config and not isinstance(config['app_debug'], bool):
                     app.logger.warning(f"Config value for 'app_debug' ('{config['app_debug']}') is not a valid boolean. Using default: {defaults['app_debug']}")
                     config['app_debug'] = defaults['app_debug']

                if 'file_handler_log_level' in file_config and not isinstance(config['file_handler_log_level'], str):
                    app.logger.warning(f"Config value for 'file_handler_log_level' ('{config['file_handler_log_level']}') is not a valid string. Using default: {defaults['file_handler_log_level']}")
                    config['file_handler_log_level'] = defaults['file_handler_log_level']
                
                if 'app_log_level' in file_config and not isinstance(config['app_log_level'], str):
                    app.logger.warning(f"Config value for 'app_log_level' ('{config['app_log_level']}') is not a valid string. Using default: {defaults['app_log_level']}")
                    config['app_log_level'] = defaults['app_log_level']

                if 'jsonify_prettyprint_regular' in file_config and not isinstance(config['jsonify_prettyprint_regular'], bool):
                    app.logger.warning(f"Config value for 'jsonify_prettyprint_regular' ('{config['jsonify_prettyprint_regular']}') is not a valid boolean. Using default: {defaults['jsonify_prettyprint_regular']}")
                    config['jsonify_prettyprint_regular'] = defaults['jsonify_prettyprint_regular']

            except json.JSONDecodeError as e:
                if app.logger: # Logger might not be initialized when this is first called at module level
                    app.logger.error(f"Error decoding JSON from config file {filepath}: {e}. Using default configuration.")
                else:
                    print(f"Error: Could not decode JSON from {filepath}. Using defaults.") # Fallback if logger not ready
        
        # Log after successful load and potential merge
        if app.logger:
            app.logger.info(f"Successfully loaded and merged configuration from {filepath}.")
        else:
            print(f"Successfully loaded and merged configuration from {filepath}.")

    except FileNotFoundError:
        if app.logger:
            app.logger.warning(f"Config file not found: {filepath}. Using default configuration.")
        else:
            print(f"Warning: Config file {filepath} not found. Using defaults.") # Fallback if logger not ready
    
    except Exception as e:
        if app.logger:
            app.logger.error(f"An unexpected error occurred while loading config file {filepath}: {e}. Using default configuration.")
        else:
            print(f"Error: An unexpected error occurred while loading {filepath}. Using defaults.") # Fallback if logger not ready
    
    return config


# Load configuration at startup
# Note: app.logger is not fully configured yet when this line runs globally.
# Initial log messages from load_app_config might go to stderr if config file issues occur early.
APP_CONFIG = load_app_config(DEFAULT_CONFIG, CONFIG_FILE_PATH)


# --- Logging Setup ---
# Initialize a placeholder logger for early messages if needed, before full setup.
# This is primarily for load_app_config if it runs before setup_logging.
if not hasattr(app, 'logger') or not app.logger.handlers:
    # Basic config for early messages if logger isn't ready (e.g. during module import)
    logging.basicConfig(level=logging.INFO) # issues will be logged to the console
    # This temporary basicConfig will be overridden by setup_logging


def setup_logging(application, log_file_path, max_bytes, backup_count, file_handler_log_level, app_log_level):
    """
    Setup logging for the application.

    Args:
        application (Flask): The Flask application instance.
        log_file_path (str): The path to the log file.
        max_bytes (int): The maximum size of the log file in bytes.
        backup_count (int): The number of backup log files to keep.
        file_handler_log_level (str): The log level for the file handler.
        app_log_level (str): The log level for the application.

    Returns:
        None
    """
    # Remove default Flask handlers if any were added
    for handler in list(application.logger.handlers):
        if isinstance(handler, logging.StreamHandler) and logging.root.handlers and handler.stream == logging.root.handlers[0].stream: # Heuristic to find default stderr handler
            application.logger.removeHandler(handler)
    
    # Also clear root logger handlers if they were set by basicConfig, to avoid duplicate messages
    # This is a bit aggressive but ensures our RotatingFileHandler is the primary one.
    logging.getLogger().handlers = []

    file_handler = RotatingFileHandler(log_file_path, maxBytes=max_bytes, backupCount=backup_count)
    formatter = logging.Formatter(
        '%(asctime)s %(levelname)s: %(message)s '
        '[in %(pathname)s:%(lineno)d]'
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(file_handler_log_level)
    application.logger.addHandler(file_handler)
    application.logger.setLevel(app_log_level)
    application.logger.info(f"Rotating Log Handler configured. Logging to: {log_file_path}")


# Setup logging using configuration
# This will reconfigure the logger properly, overriding any basicConfig.
setup_logging(app, APP_CONFIG['log_file'], APP_CONFIG['log_max_bytes'], APP_CONFIG['log_backup_count'], APP_CONFIG['file_handler_log_level'], APP_CONFIG['app_log_level'])
# --- End Logging Setup ---


ignored_image_ids = set() # Initialize, will be populated by load_ignored_image_ids


def load_ignored_image_ids(filepath):
    """Loads image IDs from the CSV ignore file.
    
    Args:
        filepath (str): The path to the CSV ignore file.

    Returns:
        set: A set of image IDs to ignore.
    """
    ids_to_ignore = set()
    if not os.path.exists(filepath):
        app.logger.warning(f"Ignore file not found: {filepath} (as configured). No images will be ignored.")
        return ids_to_ignore

    try:
        with open(filepath, 'r', newline='') as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                app.logger.info(f"Ignore file {filepath} is empty.")
                return ids_to_ignore

            app.logger.info(f"Ignore file CSV header: {header}")

            try:
                image_id_col_index = header.index("IMAGE ID")
                app.logger.info(f"Found 'IMAGE ID' column at index {image_id_col_index} in ignore file.")
            except ValueError:
                app.logger.error(
                    f"Could not find 'IMAGE ID' column in the header of ignore file: {filepath}. "
                    f"Header: {header}. Cannot process ignore list."
                )
                return ids_to_ignore
            
            app.logger.info(f"Successfully parsed header from CSV ignore file: {filepath}")

            for i, row in enumerate(reader):# row will be a list []
                if not row: 
                    app.logger.debug(f"Skipping empty row in ignore file at line {i+2}")
                    continue
                
                try:
                    image_id_from_file = row[image_id_col_index].strip()
                    if image_id_from_file:
                        ids_to_ignore.add(image_id_from_file)
                        app.logger.debug(f"Added Image ID to ignore list: {image_id_from_file}")
                    else:
                        app.logger.warning(f"Empty Image ID found in ignore file CSV row {i+2}: {row}")
                except IndexError:
                    app.logger.warning(f"Malformed CSV row in ignore file (line {i+2}), not enough columns: {row}")
            
            app.logger.info(f"Loaded {len(ids_to_ignore)} image IDs from CSV ignore file: {filepath}")

    except Exception as e:
        app.logger.error(f"Error reading or parsing CSV ignore file {filepath}: {e}")
    
    return ids_to_ignore


# Load ignored images at startup using configured path
ignored_image_ids = load_ignored_image_ids(APP_CONFIG['ignore_file_path'])


def parse_crictl_images_output(output):
    """
    Parses the output of the crictl images command and returns a list of images.

    Args:
        output (str): The output of the crictl images command.

    Returns:
        list: A list of images.
    """
    images = []
    lines = output.strip().splitlines()
    app.logger.debug(f"Raw crictl output lines received (after splitlines): {lines}")

    if len(lines) < 2: # Need at least header + 1 data line
        app.logger.info("crictl output is empty or contains only a header. Raw output: <<<{output}>>>")
        return images

    header = lines[0]
    app.logger.debug(f"Header received for parsing: <<<{header}>>>")

    # Determine column start positions based on header text
    idx_tag_col = header.find("TAG")
    idx_image_id_col = header.find("IMAGE ID")
    idx_size_col = header.find("SIZE")
    app.logger.debug(f"Calculated column start indices - TAG: {idx_tag_col}, IMAGE ID: {idx_image_id_col}, SIZE: {idx_size_col}")

    # Ensure all critical headers are found and in logical order
    if not (idx_tag_col != -1 and
            idx_image_id_col != -1 and
            idx_size_col != -1 and
            idx_tag_col < idx_image_id_col < idx_size_col):
        app.logger.error(
            "Could not find all expected column headers ('TAG', 'IMAGE ID', 'SIZE') in the correct order "
            "in crictl output. Please check header format and column names. "
            f"Header: <<<{header}>>>, TAG@:{idx_tag_col}, IMAGE ID@:{idx_image_id_col}, SIZE@:{idx_size_col}"
        )
        return images # Return empty list if headers are not as expected

    for i, line_str in enumerate(lines[1:]): #skipping the header line
        line_str_stripped = line_str.strip()
        if not line_str_stripped:
            app.logger.debug(f"Skipping empty line at original data line index {i}")
            continue
        
        app.logger.debug(f"Processing data line {i}: <<<{line_str_stripped}>>>")

        # Extract fields based on the determined column start positions
        repo = line_str_stripped[:idx_tag_col].strip()
        tag = line_str_stripped[idx_tag_col:idx_image_id_col].strip()
        current_image_id = line_str_stripped[idx_image_id_col:idx_size_col].strip()
        size = line_str_stripped[idx_size_col:].strip()

        if not tag: # If the tag part is empty, represent as <none>
            tag = "<none>"

        # Check if this image ID should be ignored
        if current_image_id in ignored_image_ids:
            app.logger.info(f"Ignoring image as its ID '{current_image_id}' is in the ignore list: {repo}:{tag}")
            continue # Skip this image

        image_data = {
            "repository": repo,
            "tag": tag,
            "image_id": current_image_id,
            "size": size
        }
        app.logger.debug(f"Parsed data for line {i}: {image_data}")
        images.append(image_data)

    app.logger.info(f"Successfully parsed {len(images)} images from crictl output (after filtering).")
    return images


@app.route('/local-images', methods=['GET'])
def get_local_images():
    try:
        # It's common for crictl to require root privileges.
        # Ensure the service running this API has appropriate sudo permissions without a password prompt for this specific command,
        # or run the API service as a user that can execute crictl directly.
        # For security, it's better to configure sudoers for the specific command if running as non-root.
        process = subprocess.Popen(['sudo', 'crictl', 'images'], stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate(timeout=30) # Added timeout

        if process.returncode != 0: # 0 means success
            error_message = stderr.decode('utf-8').strip() # decode the error message from bytes to string
            app.logger.error(f"crictl command failed: {error_message}")
            return jsonify({"error": "Failed to execute crictl command", "details": error_message}), 500

        output = stdout.decode('utf-8') # decode the output from bytes to string
        images = parse_crictl_images_output(output)
        return jsonify(images)

    except FileNotFoundError:
        app.logger.error("crictl command not found. Ensure it is installed and in PATH.")
        return jsonify({"error": "crictl command not found. Ensure it is installed and in PATH for the user running this API."}), 500
    except subprocess.TimeoutExpired:
        app.logger.error("crictl command timed out.")
        return jsonify({"error": "crictl command timed out"}), 500
    except Exception as e:
        app.logger.error(f"An error occurred: {str(e)}")
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500


if __name__ == '__main__':
    # Make sure to run with sufficient privileges if 'sudo crictl' is used.
    # For production, use a proper WSGI server like Gunicorn or uWSGI.
    # Use configuration for host, port, and debug settings

    # Ensure JSON responses are pretty-printed when not an XHR request
    app.config['JSONIFY_PRETTYPRINT_REGULAR'] = APP_CONFIG['jsonify_prettyprint_regular']

    app.logger.info(f"Starting Flask app on {APP_CONFIG['app_host']}:{APP_CONFIG['app_port']} with debug_mode={APP_CONFIG['app_debug']}")
    app.run(
        host=APP_CONFIG['app_host'],
        port=APP_CONFIG['app_port'],
        debug=APP_CONFIG['app_debug']
    ) 