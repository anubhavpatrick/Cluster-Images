# Flask Image API Service

This project provides a Flask-based API service to retrieve container images from the local container runtime using `crictl`.

## Features

-   Retrieves container images via `crictl`.
-   Filters out images based on a configurable ignore list (`images_to_ignore.txt`).
-   Configurable logging with file rotation.
-   JSON configuration file support (`config.json`).
-   Designed to be run as a system service in production.

## Prerequisites

-   Ubuntu 22.04 (or a similar Linux distribution)
-   Python 3.8+
-   `crictl` command-line tool installed and configured.
-   `sudo` access for running `crictl` and setting up the service.

## Setup Instructions

### 1. Clone the Repository (if applicable)

If your project is in a Git repository, clone it:
```bash
git clone <your-repository-url>
cd <your-project-directory-name> # e.g., cd Cluster-Images
```
If you just have the files, ensure they are in a dedicated project directory. For these instructions, we'll assume your project is in a directory named `Cluster-Images`.

### 2. Create and Activate a Virtual Environment

It's highly recommended to use a Python virtual environment to manage project dependencies.

```bash
# Ensure python3-venv is installed
sudo apt update
sudo apt install python3-venv -y

# Navigate to your project directory (e.g., Cluster-Images)
cd /path/to/your/Cluster-Images 

# Create a virtual environment named 'venv'
python3 -m venv venv

# Activate the virtual environment
source venv/bin/activate
```
After activation, your shell prompt should be prefixed with `(venv)`.

### 3. Install Dependencies

Install the required Python packages using `requirements.txt`:
```bash
pip install -r requirements.txt
```
If `requirements.txt` is not exhaustive, you might need to install packages like Flask and Gunicorn manually:
```bash
pip install Flask gunicorn
```

### 4. Configure the Application

The application uses a `config.json` file for its settings. A `DEFAULT_CONFIG` is defined in `images_api.py` which is used if `config.json` is missing or if certain keys are absent.

Create or review `config.json` in the project root:
```json
{
    "ignore_file_path": "images_to_ignore.txt",
    "log_file": "crictl_api.log",
    "log_max_bytes": 10485760,
    "log_backup_count": 3,
    "app_host": "0.0.0.0",
    "app_port": 5000,
    "app_debug": false,
    "file_handler_log_level": "WARNING",
    "app_log_level": "WARNING",
    "jsonify_prettyprint_regular": true
}
```
**Key Production Settings in `config.json`**:
-   `"app_debug": false`: **Crucial for production.**
-   `"app_log_level"` and `"file_handler_log_level"`: Set to `"WARNING"` or `"INFO"` for production.
-   `"jsonify_prettyprint_regular"`: Set to `true` for human-readable JSON, `false` for compact JSON.
-   Ensure `log_file` path is writable by the user running the application.

### 5. Configure Image Ignore List (Optional)

Create an `images_to_ignore.txt` file (or the path specified in `ignore_file_path` in `config.json`). This should be a CSV file. The first row must be a header, and one of the columns must be named `IMAGE ID`.

Example `images_to_ignore.txt`:
```csv
REPOSITORY,TAG,IMAGE ID,SIZE
some/repo,latest,abcdef123456,100MB
```
Any image whose ID matches an ID in this file will be excluded from the API results.


## Running the Application

### Development (using Flask's built-in server)

For development purposes, you can run the app directly (ensure `app_debug` is `true` in `config.json` or `DEFAULT_CONFIG` for development features):
```bash
# Ensure venv is active
source venv/bin/activate
# Navigate to project directory
cd /path/to/your/Cluster-Images
python images_api.py 
```
The app will typically run on `http://0.0.0.0:5000/`.

### Production (using Gunicorn)

For production, use a WSGI server like Gunicorn.

1.  **Ensure Gunicorn is installed in your venv**:
    ```bash
    # If not already in requirements.txt
    pip install gunicorn
    ```
2.  **Run Gunicorn from your project directory**:
    ```bash
    # Ensure venv is active
    source venv/bin/activate
    # Navigate to project directory
    cd /path/to/your/Cluster-Images

    # Run Gunicorn (replace 5675 with your desired port)
    gunicorn --workers 4 --bind 0.0.0.0:5675 images_api:app
    ```
    -   `--workers 4`: Adjust based on your CPU cores (e.g., `(2 * CPU_CORES) + 1`).
    -   `images_api:app`: Points to the `app` instance in your `images_api.py` file.

## Setting up as a `systemd` Service (Production)

To ensure the application runs on boot and is managed as a system service:

1.  **Copy the `image_api.service` service file to the following directory and provide execution permission**:
    ```bash
    sudo nano /etc/systemd/system/
    ```

2.  **Reload `systemd`, Enable, and Start the Service**:
    ```bash
    sudo systemctl daemon-reload
    sudo systemctl enable image_api.service
    sudo systemctl start image_api.service
    ```

3.  **Check Service Status and Logs**:
    ```bash
    sudo systemctl status image_api.service
    sudo journalctl -u image_api.service # To view logs
    sudo journalctl -f -u image_api.service # To follow logs
    ```

## API Endpoint

-   **GET `/local-images`**: Returns a JSON list of local container images, filtered by the ignore list.

## Troubleshooting

-   **`ModuleNotFoundError`**:
    -   Ensure you are running commands from the project's root directory (`Cluster-Images`).
    -   Verify the `WorkingDirectory` and `Environment="PYTHONPATH=..."` in the `systemd` service file are correct.
    -   Make sure the module name in the Gunicorn command (`images_api:app`) matches your Python filename (`images_api.py`).
-   **`systemd` service fails to start**:
    -   Check `sudo journalctl -u image_api.service` for detailed error messages from Gunicorn or your application.
    -   Verify all paths and permissions in the `.service` file.
    -   Ensure the `User` in the service file has permissions for `crictl` (via `sudoers`) if not running as `root`.
-   **Permission Denied for log file**: Ensure the directory for `crictl_api.log` is writable by the user running the application/service. 