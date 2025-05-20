import os
import sys

def create_directory(directory_path):
    """
    Create a directory if it doesn't exist.
    Works cross-platform on Windows, Linux, and macOS.

    Args:
        directory_path (str): The path to the directory to create
    """
    try:
        # Normalize the path for the current OS
        directory_path = os.path.normpath(directory_path)

        # Check if the directory already exists
        if not os.path.exists(directory_path):
            # Create the directory and any necessary parent directories
            os.makedirs(directory_path)
            print(f"Successfully created directory: {directory_path}")
        else:
            print(f"Directory already exists: {directory_path}")

        return True
    except Exception as e:
        print(f"Error creating directory {directory_path}: {str(e)}")
        return False

if __name__ == "__main__":
    # Check if a directory path was provided
    if len(sys.argv) < 2:
        print("Usage: python create_directory.py <directory_path>")
        sys.exit(1)

    # Get the directory path from the command line arguments
    dir_path = sys.argv[1]

    # Remove any surrounding quotes that might be causing issues on Windows
    if (dir_path.startswith('"') and dir_path.endswith('"')) or \
       (dir_path.startswith("'") and dir_path.endswith("'")):
        dir_path = dir_path[1:-1]

    # Create the directory
    success = create_directory(dir_path)

    # Exit with the appropriate status code
    sys.exit(0 if success else 1)
