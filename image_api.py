from flask import Flask, jsonify
import subprocess
import re

app = Flask(__name__)

def parse_crictl_images_output(output):
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

    for i, line_str in enumerate(lines[1:]):
        line_str_stripped = line_str.strip()
        if not line_str_stripped:
            app.logger.debug(f"Skipping empty line at original data line index {i}")
            continue
        
        app.logger.debug(f"Processing data line {i}: <<<{line_str_stripped}>>>")

        # Extract fields based on the determined column start positions
        repo = line_str_stripped[:idx_tag_col].strip()
        tag = line_str_stripped[idx_tag_col:idx_image_id_col].strip()
        image_id = line_str_stripped[idx_image_id_col:idx_size_col].strip()
        size = line_str_stripped[idx_size_col:].strip()

        if not tag: # If the tag part is empty, represent as <none>
            tag = "<none>"

        image_data = {
            "repository": repo,
            "tag": tag,
            "image_id": image_id,
            "size": size
        }
        app.logger.debug(f"Parsed data for line {i}: {image_data}")
        images.append(image_data)

    app.logger.info(f"Successfully parsed {len(images)} images from crictl output.")
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

        if process.returncode != 0:
            error_message = stderr.decode('utf-8').strip()
            app.logger.error(f"crictl command failed: {error_message}")
            return jsonify({"error": "Failed to execute crictl command", "details": error_message}), 500

        output = stdout.decode('utf-8')
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
    app.run(host='0.0.0.0', port=5000, debug=True) # debug=True is not for production 