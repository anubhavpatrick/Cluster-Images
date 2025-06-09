"""
Core functionality for retrieving container images from the local container runtime.

This module provides functions to:
- Parse crictl command output
- Handle image ignore lists
- Process container image data

Author:
    - Name: Anubhav Patrick
    - Email: anubhav.patrick@giindia.com
    - Date: 2025-06-05
"""

import logging
import csv
import os

# Get module logger
logger = logging.getLogger(__name__) #get logger for this module 


def load_ignored_image_ids(filepath):
    """Loads image IDs from the CSV ignore file.
    
    Args:
        filepath (str): The path to the CSV ignore file.

    Returns:
        set: A set of image IDs to ignore.
    """
    ids_to_ignore = set()
    if not os.path.exists(filepath):
        logger.warning(f"Ignore file not found: {filepath} (as configured). No images will be ignored.")
        return ids_to_ignore

    try:
        with open(filepath, 'r', newline='') as f:
            reader = csv.reader(f)
            try:
                header = next(reader)
            except StopIteration:
                logger.info(f"Ignore file {filepath} is empty.")
                return ids_to_ignore

            logger.info(f"Ignore file CSV header: {header}")

            try:
                image_id_col_index = header.index("IMAGE ID")
                logger.info(f"Found 'IMAGE ID' column at index {image_id_col_index} in ignore file.")
            except ValueError:
                logger.error(
                    f"Could not find 'IMAGE ID' column in the header of ignore file: {filepath}. "
                    f"Header: {header}. Cannot process ignore list."
                )
                return ids_to_ignore
            
            logger.info(f"Successfully parsed header from CSV ignore file: {filepath}")

            for i, row in enumerate(reader):
                if not row: 
                    logger.debug(f"Skipping empty row in ignore file at line {i+2}")
                    continue
                
                try:
                    image_id_from_file = row[image_id_col_index].strip()
                    if image_id_from_file:
                        ids_to_ignore.add(image_id_from_file)
                        logger.debug(f"Added Image ID to ignore list: {image_id_from_file}")
                    else:
                        logger.warning(f"Empty Image ID found in ignore file CSV row {i+2}: {row}")
                except IndexError:
                    logger.warning(f"Malformed CSV row in ignore file (line {i+2}), not enough columns: {row}")
            
            logger.info(f"Loaded {len(ids_to_ignore)} image IDs from CSV ignore file: {filepath}")

    except Exception as e:
        logger.error(f"Error reading or parsing CSV ignore file {filepath}: {e}")
    
    return ids_to_ignore


def parse_crictl_images_output(output, ignored_image_ids=None):
    """
    Parses the output of the crictl images command and returns a list of images.

    Args:
        output (str): The output of the crictl images command.
        ignored_image_ids (set, optional): Set of image IDs to ignore.

    Returns:
        list: A list of images.
    """
    if ignored_image_ids is None:
        ignored_image_ids = set()

    images = []
    lines = output.strip().splitlines()
    logger.debug(f"Raw crictl output lines received (after splitlines): {lines}")

    if len(lines) < 2: # Need at least header + 1 data line
        logger.info("crictl output is empty or contains only a header. Raw output: <<<{output}>>>")
        return images

    header = lines[0]
    logger.debug(f"Header received for parsing: <<<{header}>>>")

    # Determine column start positions based on header text
    idx_tag_col = header.find("TAG")
    idx_image_id_col = header.find("IMAGE ID")
    idx_size_col = header.find("SIZE")
    logger.debug(f"Calculated column start indices - TAG: {idx_tag_col}, IMAGE ID: {idx_image_id_col}, SIZE: {idx_size_col}")

    # Ensure all critical headers are found and in logical order
    if not (idx_tag_col != -1 and
            idx_image_id_col != -1 and
            idx_size_col != -1 and
            idx_tag_col < idx_image_id_col < idx_size_col):
        logger.error(
            "Could not find all expected column headers ('TAG', 'IMAGE ID', 'SIZE') in the correct order "
            "in crictl output. Please check header format and column names. "
            f"Header: <<<{header}>>>, TAG@:{idx_tag_col}, IMAGE ID@:{idx_image_id_col}, SIZE@:{idx_size_col}"
        )
        return images # Return empty list if headers are not as expected

    for i, line_str in enumerate(lines[1:]): #skipping the header line
        line_str_stripped = line_str.strip()
        if not line_str_stripped:
            logger.debug(f"Skipping empty line at original data line index {i}")
            continue
        
        logger.debug(f"Processing data line {i}: <<<{line_str_stripped}>>>")

        # Extract fields based on the determined column start positions
        repo = line_str_stripped[:idx_tag_col].strip()
        tag = line_str_stripped[idx_tag_col:idx_image_id_col].strip()
        current_image_id = line_str_stripped[idx_image_id_col:idx_size_col].strip()
        size = line_str_stripped[idx_size_col:].strip()

        if not tag: # If the tag part is empty, represent as <none>
            tag = "<none>"

        # Check if this image ID should be ignored
        if current_image_id in ignored_image_ids:
            logger.info(f"Ignoring image as its ID '{current_image_id}' is in the ignore list: {repo}:{tag}")
            continue # Skip this image

        image_data = {
            "repository": repo,
            "tag": tag,
            "image_id": current_image_id,
            "size": size
        }
        logger.debug(f"Parsed data for line {i}: {image_data}")
        images.append(image_data)

    logger.info(f"Successfully parsed {len(images)} images from crictl output (after filtering).")
    return images 