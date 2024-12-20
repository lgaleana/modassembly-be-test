import os

def create_app(app_name: str):
    """
    Given the name of an app, checks in db/repos if a folder with that name exists.
    If it does, raises an error. If it doesn't, creates a new app with the given name.
    """
    base_path = 'db/repos'
    app_path = os.path.join(base_path, app_name)

    if os.path.exists(app_path):
        raise FileExistsError(f"An app with the name '{app_name}' already exists.")
    
    os.makedirs(app_path)
    print(f"App '{app_name}' created successfully at {app_path}.")
