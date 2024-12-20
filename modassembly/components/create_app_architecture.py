import os
import shutil

def create_app_architecture(app_name: str):
    """
    Given the name of an app, copy db/repos/example/config.json into db/repos/app_name/config.json.
    """
    # Define the source and destination paths
    source_path = os.path.join('db', 'repos', 'example', 'config.json')
    destination_dir = os.path.join('db', 'repos', app_name)
    destination_path = os.path.join(destination_dir, 'config.json')

    # Ensure the destination directory exists
    os.makedirs(destination_dir, exist_ok=True)

    # Copy the config file from the source to the destination
    shutil.copyfile(source_path, destination_path)
