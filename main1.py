import os
import platform

def open_file_or_folder(path):
    """
    Opens a file or folder in the default application or file explorer (Windows only).
    """

    # OS check
    if platform.system() != "Windows":
        return "This function is only supported on Windows."

    if not path or not isinstance(path, str):
        return "Error: Invalid path input."

    try:
        # Normalize path
        path = os.path.abspath(path)

        # Validate existence
        if not os.path.exists(path):
            return f"Error: Path does not exist: {path}"

        # Open file or folder safely
        os.startfile(path)

        return f"Successfully opened: {path}"

    except OSError as e:
        return f"OS error while opening path: {e}"
    except Exception as e:
        return f"Unexpected error: {e}"


if __name__ == "__main__":
    example_path = r"C:\Users"
    print(open_file_or_folder(example_path))
