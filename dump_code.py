import os
import argparse
from pathlib import Path

def get_file_structure(root_dir):
    """Get the file structure of Python files in the given directory."""
    structure = []
    # Directories to exclude
    exclude_dirs = {'.venv', '__pycache__', '.git', 'venv', 'env', 'node_modules'}
    # Get the current script's filename
    current_script = os.path.basename(__file__)
    
    for path in Path(root_dir).rglob("*.py"):
        # Skip if any parent directory is in exclude_dirs
        if any(excluded in path.parts for excluded in exclude_dirs):
            continue
        # Skip the current script file
        if path.name == current_script:
            continue
        relative_path = path.relative_to(root_dir)
        structure.append(str(relative_path))
    return sorted(structure)

def dump_code(file_path):
    """Read and return the contents of a file."""
    try:
        with open(file_path, 'r', encoding='utf-8') as f:
            return f.read()
    except Exception as e:
        return f"Error reading file: {str(e)}"

def process_files(root_dir, output_file=None):
    """Process all Python files in the directory and its subdirectories."""
    # Get file structure first
    structure = get_file_structure(root_dir)
    
    # Print or write file structure
    if output_file:
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write("File Structure:\n")
            f.write("==============\n")
            for file_path in structure:
                f.write(f"{file_path}\n")
            f.write("\nFile Contents:\n")
            f.write("==============\n\n")
    else:
        print("File Structure:")
        print("==============")
        for file_path in structure:
            print(file_path)
        print("\nFile Contents:")
        print("==============\n")

    # Process each file
    for file_path in structure:
        full_path = os.path.join(root_dir, file_path)
        content = dump_code(full_path)
        
        if output_file:
            with open(output_file, 'a', encoding='utf-8') as f:
                f.write(f"Path: {file_path}\n")
                f.write(f"File: {os.path.basename(file_path)}\n")
                f.write("Code:\n")
                f.write(content)
                f.write("\n\n" + "="*50 + "\n\n")
        else:
            print(f"Path: {file_path}")
            print(f"File: {os.path.basename(file_path)}")
            print("Code:")
            print(content)
            print("\n" + "="*50 + "\n")

def main():
    parser = argparse.ArgumentParser(description='Dump Python code from files in a structured format.')
    parser.add_argument('--dir', type=str, help='Directory to process (default: current directory)')
    parser.add_argument('--output', type=str, help='Output file to write results (optional)')
    
    args = parser.parse_args()
    
    # Use current directory if no directory specified
    root_dir = args.dir if args.dir else os.getcwd()
    
    process_files(root_dir, args.output)

if __name__ == "__main__":
    main()


# process current directory
# uv run dump_code.py
# # specific directory
# uv run dump_code.py --dir /path/to/your/folder
# # save to file
# uv run dump_code.py --output output.txt
# uv run dump_code.py --dir /path/to/your/folder --output output.txt
