# Image Service Backend

This server is a Flask application that provides an API endpoint to list container images from two sources:
1.  The local container runtime (`containerd`), accessed via `crictl`.
2.  A remote Harbor registry, accessed via the Harbor API.

## Dependencies

- Python 3.x
- `gunicorn`
- `Flask`
- `requests`
- `humanize`

## Setup

1.  **Navigate to the server directory:**
    ```bash
    cd server
    ```

2.  **Create a Python virtual environment:**
    ```bash
    python3 -m venv venv
    ```

3.  **Activate the virtual environment:**
    ```bash
    source venv/bin/activate
    ```

4.  **Install the required packages:**
    ```bash
    pip install -r requirements.txt
    ```

## Configuration

The server is configured via two files:

1.  `config.json`: This file contains the core configuration for the application.

    -   `harbor_config`: Holds the URL and credentials for your Harbor registry. **You must fill these in.**
    -   `app_config`: Contains settings for the Flask application itself, like host, port, and logging configuration.

    A default `config.json` is provided. You should review and update it with your specific environment details.

2.  `images_to_ignore.txt`: This is a CSV file used to specify container images that should be excluded from the `crictl` output. Add the `IMAGE ID` of any image you want to ignore into this file.

## Running the Server

### Development

For development purposes, you can run the server directly using Python:

```bash
# Make sure your virtual environment is activated
python3 -m app.image
```

### Production

For production, it is highly recommended to use `gunicorn` as specified in the provided `systemd` service file.

1.  **Permissions:** The application calls `sudo crictl images`. This means the user running the application must either be `root` or have passwordless `sudo` access specifically for the `crictl images` command.

    To grant passwordless access, add the following line to your sudoers file using `visudo`, replacing `your_user` with the user running the service:
    ```
    your_user ALL=(ALL) NOPASSWD: /usr/bin/crictl images
    ```

2.  **Using Gunicorn:** From within the `server` directory, run Gunicorn pointing to the application instance in `app/image.py`:
    ```bash
    # Make sure your virtual environment is activated
    gunicorn --workers 3 --bind 0.0.0.0:5375 app.image:app
    ```
    *Note: The port `5375` is used here to match the default in the `imgctl` client.*

3.  **Using systemd (Recommended):** The `image_api.service` file is a template for running the application as a systemd service.
    -   Edit the `User`, `Group`, and `WorkingDirectory` to match your environment.
    -   Copy the file to `/etc/systemd/system/image_api.service`.
    -   Reload and start the service:
        ```bash
        sudo systemctl daemon-reload
        sudo systemctl start image_api.service
        sudo systemctl enable image_api.service
        ```

## API Endpoint

-   **Endpoint:** `GET /images`
-   **Description:** Returns a JSON object containing two lists: `containerd_images` and `harbor_images`, along with any errors encountered.
-   **Example Response:**
    ```json
    {
      "containerd_images": [
        {
          "image_id": "a24bb4013296",
          "repository": "k8s.gcr.io/kube-proxy",
          "size": "117MB",
          "tag": "v1.23.5"
        }
      ],
      "harbor_images": [
        {
          "digest": "sha256:f6d...",
          "project": "my-project",
          "repository": "my-app",
          "size": "250MB",
          "tag": "latest"
        }
      ],
      "errors": []
    }
    ``` 