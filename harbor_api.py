"""
Core functionality for retrieving repository and artifact information from a Harbor registry.

This module provides functions to:
- Fetch repositories from Harbor v2.0 API
- Handle API pagination
- Process Harbor image data

Author:
    - Name: Anubhav Patrick
    - Email: anubhav.patrick@giindia.com
    - Date: 2025-06-06
"""

import requests
import logging

# Get module logger
logger = logging.getLogger(__name__)

def get_harbor_paginated_results(url, auth, params=None, verify_ssl=True):
    """
    Fetches all results from a paginated Harbor API endpoint.
    
    Args:
        url (str): The Harbor API endpoint URL
        auth: The authentication object (e.g. HTTPBasicAuth)
        params (dict, optional): Additional query parameters
        verify_ssl (bool): Whether to verify SSL certificates

    Returns:
        list: Combined results from all pages
    """
    if not verify_ssl:
        requests.packages.urllib3.disable_warnings(requests.packages.urllib3.exceptions.InsecureRequestWarning)

    results = []
    page = 1
    page_size = 100  # Harbor's maximum page size
    
    if params is None:
        params = {}
    
    while True:
        params['page'] = page
        params['page_size'] = page_size
        
        try:
            response = requests.get(url, auth=auth, params=params, verify=verify_ssl)
            response.raise_for_status()
            
            # Some Harbor API endpoints return a list directly, others wrap it in a JSON object
            page_data = response.json()
            if isinstance(page_data, list):
                current_page_results = page_data
            else:
                # If it's not a list, look for common Harbor response structures
                current_page_results = page_data.get('data', page_data)
                if not isinstance(current_page_results, list):
                    logger.error(f"Unexpected response format from {url}: {page_data}")
                    return None

            results.extend(current_page_results)
            logger.debug(f"Retrieved {len(current_page_results)} results from page {page}")
            
            # Check if we've received less than a full page
            if len(current_page_results) < page_size:
                break
                
            page += 1
            
        except requests.exceptions.RequestException as e:
            logger.error(f"Error fetching data from Harbor API {url}: {e}")
            return None
        except ValueError as e:
            logger.error(f"Error parsing JSON response from Harbor API {url}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error while fetching from Harbor API {url}: {e}")
            return None
    
    logger.info(f"Successfully retrieved {len(results)} total results from {url}")
    return results 