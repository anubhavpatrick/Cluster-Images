from flask import Flask, jsonify, request
import requests
import os
from requests.auth import HTTPBasicAuth
from urllib.parse import quote_plus # For URL encoding repository names

app = Flask(__name__)

# Configuration from environment variables or defaults
HARBOR_URL = os.environ.get("HARBOR_URL", "https://k8s-gpu-worker-node:9443").rstrip('/')
HARBOR_USERNAME = os.environ.get("HARBOR_USERNAME", "testing")
HARBOR_PASSWORD = os.environ.get("HARBOR_PASSWORD", "Test@123")
# For local/internal Harbor instances that might use self-signed certificates
HARBOR_VERIFY_SSL = os.environ.get("HARBOR_VERIFY_SSL", "false").lower() == "true"

def get_harbor_paginated_results(url, auth, params=None):
    """
    Fetches all results from a paginated Harbor API endpoint.
    """
    results = []
    page = 1
    page_size = 50 # Harbor default is often 10, can be up to 100
    if params is None:
        params = {}
    
    while True:
        params['page'] = page
        params['page_size'] = page_size
        try:
            response = requests.get(url, auth=auth, params=params, verify=HARBOR_VERIFY_SSL)
            response.raise_for_status() # Raise an exception for HTTP errors (4xx or 5xx)
            current_page_data = response.json()
            if not current_page_data:
                break
            results.extend(current_page_data)
            
            # Check if this was the last page (Harbor uses Link header or x-total-count)
            # Simple check: if less items received than page_size, it's likely the last page
            if len(current_page_data) < page_size:
                break
            total_count_header = response.headers.get('x-total-count')
            if total_count_header and len(results) >= int(total_count_header):
                break
            page += 1
        except requests.exceptions.RequestException as e:
            app.logger.error(f"Error fetching paginated results from {url} (page {page}): {e}")
            raise # Re-raise the exception to be handled by the caller
        except ValueError as e: # JSON decoding error
            app.logger.error(f"JSON decoding error from {url}: {e} - Response: {response.text[:200]}")
            raise
    return results

@app.route('/harbor-images', methods=['GET'])
def get_harbor_images():
    app.logger.info(f"Starting /harbor-images request. Harbor URL: {HARBOR_URL}, User: {HARBOR_USERNAME}, SSL Verify: {HARBOR_VERIFY_SSL}")
    all_images_with_tags = []
    auth = HTTPBasicAuth(HARBOR_USERNAME, HARBOR_PASSWORD)

    if not HARBOR_VERIFY_SSL:
        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

    try:
        # 1. Get all projects
        projects_url = f"{HARBOR_URL}/api/v2.0/projects"
        app.logger.info(f"Fetching projects from {projects_url}")
        projects = get_harbor_paginated_results(projects_url, auth, params={"with_detail": "false"})
        app.logger.info(f"Found {len(projects)} projects.")

        for project in projects:
            project_name = project.get('name')
            project_id = project.get('project_id') # Harbor API uses project_id or name
            if not project_name:
                app.logger.warning(f"Project found without a name: {project}")
                continue
            
            app.logger.info(f"Fetching repositories for project: {project_name} (ID: {project_id})")
            
            # 2. For each project, get repositories
            # Repository names might contain slashes, so they need to be URL encoded when part of path.
            # However, the project_name for listing repositories is a path parameter itself.
            repositories_url = f"{HARBOR_URL}/api/v2.0/projects/{project_name}/repositories"
            
            repos_params = {'page_size': 50} # Adjust as needed
            repositories = get_harbor_paginated_results(repositories_url, auth, params=repos_params)
            app.logger.info(f"Found {len(repositories)} repositories in project {project_name}.")

            for repo in repositories:
                full_repo_name = repo.get('name')
                if not full_repo_name:
                    app.logger.warning(f"Repository found without a name in project {project_name}: {repo}")
                    continue

                repository_actual_name = None
                app.logger.debug(f"Processing full_repo_name: {repr(full_repo_name)} for project: {repr(project_name)}")

                # Alternative logic to derive repository_actual_name
                name_parts = full_repo_name.split('/', 1)
                if len(name_parts) == 2 and name_parts[0] == project_name:
                    repository_actual_name = name_parts[1]
                    app.logger.info(f"SUCCESS (split method): Original: '{full_repo_name}', Project: '{project_name}', Derived actual_repo_name: '{repository_actual_name}'")
                else:
                    app.logger.warning(
                        f"FAILURE (split method): Could not derive actual_repo_name as expected. "
                        f"full_repo_name: {repr(full_repo_name)}, split_parts: {name_parts}, project_name: {repr(project_name)}. "
                        f"Using full name '{full_repo_name}' as actual_repo_name, which may lead to 404."
                    )
                    # Fallback to using the full name if splitting didn't work as expected
                    repository_actual_name = full_repo_name

                if not repository_actual_name:
                    app.logger.error(f"Critical error: repository_actual_name is empty for full_repo_name: {repr(full_repo_name)}. Skipping repo.")
                    continue
                
                encoded_repo_actual_name = quote_plus(repository_actual_name)

                app.logger.info(f"Fetching artifacts for project '{project_name}', original_repo_name '{full_repo_name}', derived_and_encoded_for_api '{encoded_repo_actual_name}'")
                artifacts_url = f"{HARBOR_URL}/api/v2.0/projects/{project_name}/repositories/{encoded_repo_actual_name}/artifacts"
                artifact_params = {'with_tag': 'true', 'page_size': 50}
                
                try:
                    artifacts = get_harbor_paginated_results(artifacts_url, auth, params=artifact_params)
                    app.logger.debug(f"Found {len(artifacts)} artifacts in {full_repo_name}.")

                    for artifact in artifacts:
                        if artifact.get('tags'): # Check if 'tags' key exists and is not None
                            for tag_info in artifact['tags']:
                                if tag_info and tag_info.get('name'): # Check if tag_info is not None and has 'name'
                                    all_images_with_tags.append({
                                        "repository": f"{HARBOR_URL.replace('https://','').replace('http://','')}/{full_repo_name}", # Display full path
                                        "tag": tag_info['name'],
                                        # "digest": artifact.get('digest'), # Optional: include digest
                                        # "project": project_name # Optional: include project
                                    })
                                else:
                                    app.logger.warning(f"Artifact {artifact.get('digest')} in {full_repo_name} has a null or malformed tag: {tag_info}")
                        else: # Artifact might not have tags (e.g. just a manifest list or untagged)
                             all_images_with_tags.append({
                                "repository": f"{HARBOR_URL.replace('https://','').replace('http://','')}/{full_repo_name}",
                                "tag": "<none>", # Or artifact.get('digest') if you prefer showing digest for untagged
                                # "digest": artifact.get('digest'),
                                # "project": project_name
                            })


                except requests.exceptions.HTTPError as e_artifact:
                    # Specifically catch 404 for artifacts if a repository is empty, log and continue
                    if e_artifact.response.status_code == 404:
                        app.logger.info(f"No artifacts found (404) in repository: {full_repo_name}. Skipping.")
                    else:
                        app.logger.error(f"HTTP error fetching artifacts for {full_repo_name}: {e_artifact} - Response: {e_artifact.response.text[:200]}")
                        # Optionally continue to next repo or re-raise
                except Exception as e_artifact_generic:
                    app.logger.error(f"Generic error fetching artifacts for {full_repo_name}: {e_artifact_generic}")
        
        app.logger.info(f"Total images with tags collected: {len(all_images_with_tags)}")
        return jsonify(all_images_with_tags)

    except requests.exceptions.RequestException as e:
        app.logger.error(f"Failed to connect to Harbor or general request error: {str(e)}")
        return jsonify({"error": "Failed to connect to Harbor or general request error", "details": str(e)}), 500
    except Exception as e:
        app.logger.error(f"An unexpected error occurred: {str(e)}")
        return jsonify({"error": "An unexpected error occurred", "details": str(e)}), 500

if __name__ == '__main__':
    # For production, use a proper WSGI server like Gunicorn.
    # Example: gunicorn --bind 0.0.0.0:5001 harbor_image_api:app
    # Ensure HARBOR_URL, HARBOR_USERNAME, HARBOR_PASSWORD are set in the environment or correct in the script.
    app.run(host='0.0.0.0', port=5001, debug=True) # Use a different port than image_api 